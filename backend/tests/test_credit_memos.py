"""Phase 3B: credit memos and refunds (docs/BILLING_PLAN.md). The plan's worked example is the
first test; the database guards are tested against the runtime role, bypassing the API."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.test_payment_db_guards import refuses
from tests.test_payments import final_invoice, pay


def invoice_with_tax(biller, org, cents=14197, taxable=True):
    """INV with one manual line; 14,197 c taxed at 8.25% -> tax 1,171, total 15,368."""
    biller.patch(f"/api/organizations/{org}/billing", json={"tax_rate_bp": 825})
    inv = biller.post("/api/invoices", json={"organization_id": org, "include_unbilled": False})
    inv = inv.json()
    biller.post(
        f"/api/invoices/{inv['id']}/lines",
        json={
            "description": "Overbilled",
            "quantity": "1",
            "unit_price_cents": cents,
            "taxable": taxable,
        },
    )
    r = biller.post(f"/api/invoices/{inv['id']}/finalize", json={})
    assert r.status_code == 200, r.text
    return r.json()


def memo(client, org, cents=10000, taxable=False, **kw):
    body = {
        "organization_id": org,
        "reason": "Billed in error",
        "lines": [{"description": "Correction", "unit_price_cents": cents, "taxable": taxable}],
        **kw,
    }
    return client.post("/api/credit-memos", json=body)


def invoice(client, invoice_id):
    return client.get(f"/api/invoices/{invoice_id}").json()


@pytest.fixture
def org(org_ctx):
    return org_ctx["org"]


# ---- the worked example ----
def test_plan_example_memo_of_a_line_plus_tax_clears_the_invoice(biller, org, company):
    inv = invoice_with_tax(biller, org)
    assert inv["total_cents"] == 15368
    r = memo(
        biller,
        org,
        14197,
        taxable=True,
        invoice_id=inv["id"],
        applications=[{"invoice_id": inv["id"], "amount_cents": 15368}],
    )
    assert r.status_code == 201, r.text
    m = r.json()
    assert (m["subtotal_cents"], m["tax_cents"], m["total_cents"]) == (14197, 1171, 15368)
    assert m["number"].startswith("CM-") and m["number"].endswith("-0001")
    assert (m["applied_cents"], m["unapplied_cents"]) == (15368, 0)
    after = invoice(biller, inv["id"])
    assert after["balance_cents"] == 0 and after["credited_cents"] == 15368
    assert after["paid_cents"] == 0 and after["total_cents"] == 15368  # never edited


def test_numbers_are_sequential_and_a_failed_issue_burns_none(biller, org, company):
    first = memo(biller, org).json()
    bad = memo(biller, org, applications=[{"invoice_id": 999999, "amount_cents": 1}])
    assert bad.status_code == 404 or bad.status_code == 409
    second = memo(biller, org).json()
    n1, n2 = (int(m["number"].rsplit("-", 1)[1]) for m in (first, second))
    assert n2 == n1 + 1


def test_memo_date_sets_the_number_year_and_cannot_be_future(biller, org, company):
    assert memo(biller, org, memo_date="2025-03-01").json()["number"] == "CM-2025-0001"
    assert memo(biller, org, memo_date="2999-01-01").status_code == 409


def test_lines_round_per_line_and_zero_lines_are_refused(biller, org, company):
    biller.patch(f"/api/organizations/{org}/billing", json={"tax_rate_bp": 825})
    r = biller.post(
        "/api/credit-memos",
        json={
            "organization_id": org,
            "reason": "Two lines",
            "lines": [
                {"description": "a", "quantity": "1.5", "unit_price_cents": 1001, "taxable": True},
                {"description": "b", "unit_price_cents": 333, "taxable": True},
            ],
        },
    )
    m = r.json()
    # 1.5 x 1001 = 1501.5 -> 1502, tax 123.9 -> 124; 333 -> tax 27.47 -> 27
    assert [(ln["amount_cents"], ln["tax_cents"]) for ln in m["lines"]] == [(1502, 124), (333, 27)]
    assert m["total_cents"] == 1502 + 124 + 333 + 27
    tiny = biller.post(
        "/api/credit-memos",
        json={
            "organization_id": org,
            "reason": "Rounds to nothing",
            "lines": [{"description": "x", "quantity": "0.0001", "unit_price_cents": 1}],
        },
    )
    assert tiny.status_code == 409


# ---- applying, client credit, voiding ----
def test_partial_apply_leaves_client_credit_that_can_be_applied_later(biller, org, company):
    inv = final_invoice(biller, org, 6000)
    m = memo(biller, org, 10000, applications=[{"invoice_id": inv["id"], "amount_cents": 6000}])
    m = m.json()
    assert m["unapplied_cents"] == 4000 and invoice(biller, inv["id"])["balance_cents"] == 0
    credit = {
        r["organization_id"]: r["credit_cents"]
        for r in biller.get("/api/receivables").json()["rows"]
    }
    assert credit[org] == 4000
    later = final_invoice(biller, org, 5000)
    r = biller.post(
        f"/api/credit-memos/{m['id']}/apply",
        json={"invoice_id": later["id"], "amount_cents": 4000},
    )
    assert r.status_code == 200 and r.json()["unapplied_cents"] == 0
    assert invoice(biller, later["id"])["balance_cents"] == 1000
    assert invoice(biller, later["id"])["payment_status"] == "partial"


def test_apply_rules(biller, make_org, org, company):
    inv = final_invoice(biller, org, 5000)
    m = memo(biller, org, 3000).json()

    def apply(i, a):
        return biller.post(
            f"/api/credit-memos/{m['id']}/apply", json={"invoice_id": i, "amount_cents": a}
        )

    assert apply(inv["id"], 3001).status_code == 409  # more than the memo
    other = make_org("Other Co")["id"]
    other_inv = final_invoice(biller, other, 5000)
    assert apply(other_inv["id"], 100).status_code == 409  # different client
    draft = biller.post("/api/invoices", json={"organization_id": org, "include_unbilled": False})
    assert apply(draft.json()["id"], 100).status_code == 409  # not finalized
    assert apply(inv["id"], 3000).status_code == 200
    assert apply(inv["id"], 1).status_code == 409  # memo used up
    small = memo(biller, org, 9000).json()
    r = biller.post(
        f"/api/credit-memos/{small['id']}/apply",
        json={"invoice_id": inv["id"], "amount_cents": 2001},
    )
    assert r.status_code == 409  # invoice balance is 2,000


def test_payments_writeoffs_and_memos_share_the_invoice_balance(biller, org, company):
    inv = final_invoice(biller, org, 10000)
    pay(biller, org, 4000, [{"invoice_id": inv["id"], "amount_cents": 4000}])
    memo(biller, org, 3000, applications=[{"invoice_id": inv["id"], "amount_cents": 3000}])
    now = invoice(biller, inv["id"])
    assert (now["paid_cents"], now["credited_cents"], now["balance_cents"]) == (4000, 3000, 3000)
    assert (
        biller.post(f"/api/invoices/{inv['id']}/write-off", json={"reason": "bad debt"}).status_code
        == 201
    )
    assert invoice(biller, inv["id"])["balance_cents"] == 0
    assert (
        pay(biller, org, 100, [{"invoice_id": inv["id"], "amount_cents": 100}]).status_code == 409
    )


def test_voiding_a_memo_undoes_its_applications(biller, org, company):
    inv = final_invoice(biller, org, 8000)
    m = memo(
        biller, org, 8000, applications=[{"invoice_id": inv["id"], "amount_cents": 8000}]
    ).json()
    assert biller.post(f"/api/credit-memos/{m['id']}/void", json={"reason": "x"}).status_code == 422
    r = biller.post(f"/api/credit-memos/{m['id']}/void", json={"reason": "Issued by mistake"})
    assert (
        r.status_code == 200 and r.json()["status"] == "void" and r.json()["unapplied_cents"] == 0
    )
    assert invoice(biller, inv["id"])["balance_cents"] == 8000
    assert (
        biller.post(f"/api/credit-memos/{m['id']}/void", json={"reason": "again"}).status_code
        == 409
    )
    again = biller.post(
        f"/api/credit-memos/{m['id']}/apply", json={"invoice_id": inv["id"], "amount_cents": 1}
    )
    assert again.status_code == 409
    assert {
        r["organization_id"]: r["credit_cents"]
        for r in biller.get("/api/receivables").json()["rows"]
    }.get(org, 0) == 0


def test_unapplying_returns_value_to_the_memo(biller, org, company):
    inv = final_invoice(biller, org, 8000)
    m = memo(
        biller, org, 5000, applications=[{"invoice_id": inv["id"], "amount_cents": 5000}]
    ).json()
    app_id = m["applications"][0]["id"]
    r = biller.post(
        f"/api/credit-memo-applications/{app_id}/void", json={"reason": "wrong invoice"}
    )
    assert r.status_code == 200
    assert invoice(biller, inv["id"])["balance_cents"] == 8000
    got = biller.get(f"/api/credit-memos/{m['id']}").json()
    assert (
        got["unapplied_cents"] == 5000 and got["applications"][0]["void_reason"] == "wrong invoice"
    )


def test_an_invoice_with_memo_applied_cannot_be_voided(biller, org, company):
    inv = final_invoice(biller, org, 8000)
    m = memo(
        biller, org, 1000, applications=[{"invoice_id": inv["id"], "amount_cents": 1000}]
    ).json()
    r = biller.post(f"/api/invoices/{inv['id']}/void", json={"reason": "wrong client"})
    assert r.status_code == 409 and "credit memos" in r.json()["detail"]
    biller.post(f"/api/credit-memos/{m['id']}/void", json={"reason": "undo first"})
    assert (
        biller.post(f"/api/invoices/{inv['id']}/void", json={"reason": "wrong client"}).status_code
        == 200
    )


def test_memo_listing_filters_and_statement_credit(biller, org, make_org, company):
    other = make_org("Other Co")["id"]
    a, b = memo(biller, org).json(), memo(biller, other).json()
    biller.post(f"/api/credit-memos/{b['id']}/void", json={"reason": "not needed"})
    assert [
        m["id"]
        for m in biller.get("/api/credit-memos", params={"organization_id": org}).json()["items"]
    ] == [a["id"]]
    assert [
        m["id"] for m in biller.get("/api/credit-memos", params={"status": "void"}).json()["items"]
    ] == [b["id"]]
    assert biller.get("/api/credit-memos/999999").status_code == 404


# ---- database guards (runtime role, API bypassed) ----
@pytest.fixture
def world(biller, org, company):
    inv = final_invoice(biller, org, 10000)
    m = memo(
        biller, org, 6000, applications=[{"invoice_id": inv["id"], "amount_cents": 4000}]
    ).json()
    return {
        "org": org,
        "invoice": inv["id"],
        "memo": m["id"],
        "application": m["applications"][0]["id"],
        "number": m["number"],
    }


def test_database_makes_memos_and_lines_immutable(world):
    refuses("UPDATE credit_memos SET total_cents = 1, subtotal_cents = 1", "cannot be edited")
    refuses(
        "UPDATE credit_memos SET reason = 'changed' WHERE id = :m",
        "cannot be edited",
        m=world["memo"],
    )
    refuses("DELETE FROM credit_memos", "cannot be deleted|permission denied")
    refuses("UPDATE credit_memo_lines SET unit_price_cents = 1", "immutable|permission denied")
    refuses("DELETE FROM credit_memo_lines", "immutable|permission denied")
    refuses("DELETE FROM credit_memo_applications", "cannot be deleted|permission denied")
    refuses("UPDATE credit_memo_applications SET amount_cents = 1", "only be voided")


def test_database_refuses_voiding_a_memo_that_is_still_applied(world):
    refuses(
        "UPDATE credit_memos SET status='void', voided_at=now(), void_reason='because' WHERE id=:m",
        "still applied",
        m=world["memo"],
    )


def test_database_caps_total_settlement_across_payments_writeoffs_and_memos(world, biller):
    pay(biller, world["org"], 5000, [{"invoice_id": world["invoice"], "amount_cents": 5000}])
    # invoice 10,000: 4,000 memo + 5,000 payment = 9,000 settled; 1,001 more is refused
    refuses(
        "INSERT INTO credit_memo_applications (memo_id, invoice_id, organization_id, amount_cents) "
        "VALUES (:m, :i, :o, 1001)",
        "settle more than the invoice balance|more than the invoice balance",
        m=world["memo"],
        i=world["invoice"],
        o=world["org"],
    )
    refuses(
        "INSERT INTO write_offs (invoice_id, organization_id, amount_cents, reason) "
        "VALUES (:i, :o, 1001, 'too much')",
        "more than the invoice balance",
        i=world["invoice"],
        o=world["org"],
    )


def test_database_refuses_applying_a_memo_across_clients_or_over_its_amount(
    world, make_org, biller
):
    other = make_org("Other Co")["id"]
    other_inv = final_invoice(biller, other, 5000)
    refuses(
        "INSERT INTO credit_memo_applications (memo_id, invoice_id, organization_id, amount_cents) "
        "VALUES (:m, :i, :o, 100)",
        "different clients",
        m=world["memo"],
        i=other_inv["id"],
        o=other,
    )
    refuses(
        "INSERT INTO credit_memo_applications (memo_id, invoice_id, organization_id, amount_cents) "
        "VALUES (:m, :i, :o, 2001)",
        "more than the credit memo amount",
        m=world["memo"],
        i=world["invoice"],
        o=world["org"],
    )


def test_database_numbers_are_unique(world, owner):
    n = owner.execute(
        text("SELECT count(DISTINCT number) = count(*) FROM credit_memos")
    ).scalar_one()
    assert n is True


# ---- refunds ----
def refund(client, payment_id, amount, **kw):
    return client.post(
        f"/api/payments/{payment_id}/refunds",
        json={"amount_cents": amount, "method": "check", "reason": "Client overpaid", **kw},
    )


def test_refund_comes_only_from_the_unapplied_part(biller, org, company):
    inv = final_invoice(biller, org, 4000)
    p = pay(biller, org, 10000, [{"invoice_id": inv["id"], "amount_cents": 4000}]).json()
    assert refund(biller, p["id"], 6001).status_code == 409  # 6,000 is unapplied
    r = refund(biller, p["id"], 2500, reference="chk 77")
    assert r.status_code == 201 and r.json()["amount_cents"] == 2500
    detail = biller.get(f"/api/payments/{p['id']}").json()
    assert (detail["applied_cents"], detail["refunded_cents"], detail["unapplied_cents"]) == (
        4000,
        2500,
        3500,
    )
    assert detail["refunds"][0]["reference"] == "chk 77"
    assert refund(biller, p["id"], 3501).status_code == 409
    assert refund(biller, p["id"], 3500).status_code == 201
    assert biller.get(f"/api/payments/{p['id']}").json()["unapplied_cents"] == 0


def test_applied_money_must_be_unapplied_before_it_can_be_refunded(biller, org, company):
    inv = final_invoice(biller, org, 5000)
    p = pay(biller, org, 5000, [{"invoice_id": inv["id"], "amount_cents": 5000}]).json()
    assert refund(biller, p["id"], 100).status_code == 409
    app_id = p["applications"][0]["id"]
    biller.post(f"/api/payment-applications/{app_id}/void", json={"reason": "refunding instead"})
    assert invoice(biller, inv["id"])["balance_cents"] == 5000  # the invoice is open again
    assert refund(biller, p["id"], 5000).status_code == 201
    # the refunded money can no longer be applied
    r = biller.post(
        f"/api/payments/{p['id']}/apply", json={"invoice_id": inv["id"], "amount_cents": 1}
    )
    assert r.status_code == 409


def test_refunds_reduce_client_credit_and_voiding_one_restores_it(biller, org, company):
    p = pay(biller, org, 7000).json()

    def credit():
        rows = biller.get("/api/receivables").json()["rows"]
        return {r["organization_id"]: r["credit_cents"] for r in rows}.get(org, 0)

    assert credit() == 7000
    r = refund(biller, p["id"], 3000).json()
    assert credit() == 4000
    assert biller.post(f"/api/refunds/{r['id']}/void", json={"reason": "x"}).status_code == 422
    v = biller.post(f"/api/refunds/{r['id']}/void", json={"reason": "check never sent"})
    assert v.status_code == 200 and v.json()["void_reason"] == "check never sent"
    assert credit() == 7000
    assert biller.post(f"/api/refunds/{r['id']}/void", json={"reason": "again"}).status_code == 409


def test_a_payment_with_a_live_refund_cannot_be_voided(biller, org, company):
    p = pay(biller, org, 3000).json()
    r = refund(biller, p["id"], 1000).json()
    v = biller.post(f"/api/payments/{p['id']}/void", json={"reason": "recorded twice"})
    assert v.status_code == 409 and "refunds" in v.json()["detail"]
    biller.post(f"/api/refunds/{r['id']}/void", json={"reason": "undo"})
    assert (
        biller.post(f"/api/payments/{p['id']}/void", json={"reason": "recorded twice"}).status_code
        == 200
    )
    assert refund(biller, p["id"], 10).status_code == 409  # a voided payment cannot be refunded


def test_refund_validation(biller, org, company):
    p = pay(biller, org, 3000).json()
    assert refund(biller, p["id"], 0).status_code == 422
    assert refund(biller, p["id"], 10, reason="x").status_code == 422
    assert refund(biller, p["id"], 10, refunded_on="2999-01-01").status_code == 409
    assert refund(biller, 999999, 10).status_code == 404
    assert biller.post("/api/refunds/999999/void", json={"reason": "nope"}).status_code == 404


def test_database_guards_refunds(biller, org, company):
    p = pay(biller, org, 3000).json()
    r = refund(biller, p["id"], 1000).json()
    refuses("DELETE FROM refunds", "cannot be deleted|permission denied")
    refuses("UPDATE refunds SET amount_cents = 1", "only be voided")
    refuses(
        "INSERT INTO refunds (payment_id, organization_id, amount_cents, refunded_on, method, reason) "
        "VALUES (:p, :o, 2001, current_date, 'check', 'too much')",
        "more than the unapplied",
        p=p["id"],
        o=org,
    )
    assert r["id"]


# ---- permissions, audit, isolation ----
def test_permissions(login, biller, org, company):
    tech, ro = login("tech"), login("read_only")
    m = memo(biller, org).json()
    p = pay(biller, org, 1000).json()
    for client in (tech, ro):
        assert client.get("/api/credit-memos").status_code == 200
        assert memo(client, org).status_code == 403
        assert (
            client.post(f"/api/credit-memos/{m['id']}/void", json={"reason": "no way"}).status_code
            == 403
        )
        assert refund(client, p["id"], 10).status_code == 403
        assert client.post("/api/refunds/1/void", json={"reason": "no way"}).status_code == 403
        assert (
            client.post(
                "/api/credit-memo-applications/1/void", json={"reason": "no way"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/credit-memos/{m['id']}/apply", json={"invoice_id": 1, "amount_cents": 1}
            ).status_code
            == 403
        )


def test_every_money_change_is_audited(admin, biller, org, company):
    inv = final_invoice(biller, org, 5000)
    m = memo(
        biller, org, 5000, applications=[{"invoice_id": inv["id"], "amount_cents": 1000}]
    ).json()
    biller.post(f"/api/credit-memos/{m['id']}/void", json={"reason": "audit me"})
    p = pay(biller, org, 2000).json()
    r = refund(biller, p["id"], 500).json()
    biller.post(f"/api/refunds/{r['id']}/void", json={"reason": "audit me too"})
    log = admin.get("/api/audit", params={"limit": 200}).json()
    actions = {e["action"] for e in (log["items"] if isinstance(log, dict) else log)}
    assert {
        "credit_memo.create",
        "credit_memo.apply",
        "credit_memo.void",
        "payment.refund",
        "payment.refund_void",
    } <= actions


def test_rls_scopes_memos_applications_and_refunds_to_the_client(biller, make_org, company):
    from app.db import new_session, set_org_scope

    a, b = make_org("Org A")["id"], make_org("Org B")["id"]
    inv = final_invoice(biller, a, 5000)
    memo(biller, a, 1000, applications=[{"invoice_id": inv["id"], "amount_cents": 500}])
    memo(biller, b, 1000)
    pay_a = pay(biller, a, 900).json()["id"]
    refund(biller, pay_a, 100)
    refund(biller, pay(biller, b, 900).json()["id"], 100)
    for table in ("credit_memos", "credit_memo_lines", "credit_memo_applications", "refunds"):
        with new_session() as db:
            assert db.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0  # no scope
            set_org_scope(db, str(a))
            orgs = {r[0] for r in db.execute(text(f"SELECT organization_id FROM {table}"))}
            assert orgs == {a}, table

    with new_session() as db:
        set_org_scope(db, str(b))
        with pytest.raises(DBAPIError, match="row-level security|not found"):
            db.execute(
                text(
                    "INSERT INTO refunds (payment_id, organization_id, amount_cents, "
                    "refunded_on, method, reason) "
                    "VALUES (:p, :a, 1, current_date, 'check', 'cross client')"
                ),
                {"p": pay_a, "a": a},
            )
        db.rollback()


def test_triggers_hold_even_for_the_table_owner(world, owner):
    for sql, message in (
        ("UPDATE credit_memo_lines SET unit_price_cents = 1", "immutable"),
        ("DELETE FROM credit_memo_lines", "immutable"),
        ("UPDATE credit_memos SET total_cents = 1, subtotal_cents = 1", "cannot be edited"),
        ("DELETE FROM credit_memos", "cannot be deleted"),
    ):
        with pytest.raises(Exception, match=message):
            owner.execute(text(sql))
