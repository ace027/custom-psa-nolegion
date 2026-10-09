from datetime import timedelta

import pytest

from tests.conftest import biz_today


def final_invoice(biller, org_id, cents=10000, invoice_date=None, terms=None):
    if terms is not None:
        biller.patch(f"/api/organizations/{org_id}/billing", json={"payment_terms_days": terms})
    inv = biller.post(
        "/api/invoices", json={"organization_id": org_id, "include_unbilled": False}
    ).json()
    biller.post(
        f"/api/invoices/{inv['id']}/lines",
        json={"description": "Consulting", "quantity": "1", "unit_price_cents": cents},
    )
    body = {"invoice_date": invoice_date.isoformat()} if invoice_date else {}
    r = biller.post(f"/api/invoices/{inv['id']}/finalize", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def pay(client, org_id, amount, applications=None, **kw):
    return client.post(
        "/api/payments",
        json={
            "organization_id": org_id,
            "amount_cents": amount,
            "method": "check",
            "reference": "1001",
            "applications": applications or [],
            **kw,
        },
    )


def inv(client, invoice_id):
    return client.get(f"/api/invoices/{invoice_id}").json()


@pytest.fixture
def org(org_ctx):
    return org_ctx["org"]


# ---- paying an invoice ----
def test_full_payment_marks_the_invoice_paid(admin, biller, org, company):
    i = final_invoice(biller, org, 32475)
    assert (i["payment_status"], i["balance_cents"], i["paid_cents"]) == ("unpaid", 32475, 0)
    r = pay(biller, org, 32475, [{"invoice_id": i["id"], "amount_cents": 32475}])
    assert r.status_code == 201, r.text
    p = r.json()
    assert (p["status"], p["applied_cents"], p["unapplied_cents"]) == ("active", 32475, 0)
    assert p["received_on"] == biz_today().isoformat() and p["method"] == "check"
    assert p["organization_name"] == "Acme Corp" and len(p["applications"]) == 1
    after = inv(biller, i["id"])
    assert (after["payment_status"], after["balance_cents"], after["paid_cents"]) == (
        "paid",
        0,
        32475,
    )
    assert after["payments"][0]["reference"] == "1001" and after["payments"][0]["method"] == "check"
    assert after["total_cents"] == 32475  # the frozen invoice itself never changes
    actions = [
        a["action"] for a in admin.get("/api/audit", params={"action": "payment."}).json()["items"]
    ]
    assert "payment.create" in actions and "payment.apply" in actions


def test_partial_payments_accumulate(biller, org, company):
    i = final_invoice(biller, org, 10000)
    pay(biller, org, 2500, [{"invoice_id": i["id"], "amount_cents": 2500}])
    a = inv(biller, i["id"])
    assert (a["payment_status"], a["balance_cents"]) == ("partial", 7500)
    pay(biller, org, 7000, [{"invoice_id": i["id"], "amount_cents": 7000}])
    b = inv(biller, i["id"])
    assert (b["payment_status"], b["balance_cents"], b["paid_cents"]) == ("partial", 500, 9500)
    pay(biller, org, 500, [{"invoice_id": i["id"], "amount_cents": 500}])
    assert inv(biller, i["id"])["payment_status"] == "paid"
    assert len(inv(biller, i["id"])["payments"]) == 3


def test_one_payment_can_pay_several_invoices(biller, org, company):
    a, b = final_invoice(biller, org, 6000), final_invoice(biller, org, 4000)
    r = pay(
        biller,
        org,
        10000,
        [
            {"invoice_id": a["id"], "amount_cents": 6000},
            {"invoice_id": b["id"], "amount_cents": 4000},
        ],
    ).json()
    assert r["applied_cents"] == 10000 and len(r["applications"]) == 2
    assert (
        inv(biller, a["id"])["payment_status"] == inv(biller, b["id"])["payment_status"] == "paid"
    )


def test_overpayment_becomes_credit_that_can_be_applied_later(biller, org, company):
    a, b = final_invoice(biller, org, 10000), final_invoice(biller, org, 3000)
    p = pay(biller, org, 15000, [{"invoice_id": a["id"], "amount_cents": 10000}]).json()
    assert (p["applied_cents"], p["unapplied_cents"]) == (10000, 5000)
    listed = biller.get("/api/payments", params={"organization_id": org}).json()["items"][0]
    assert listed["unapplied_cents"] == 5000
    r = biller.post(
        f"/api/payments/{p['id']}/apply", json={"invoice_id": b["id"], "amount_cents": 3000}
    )
    assert r.status_code == 200 and r.json()["unapplied_cents"] == 2000
    assert inv(biller, b["id"])["payment_status"] == "paid"
    assert biller.get(f"/api/payments/{p['id']}").json()["applications"][1]["invoice_id"] == b["id"]


def test_payment_with_no_applications_is_all_credit(biller, org, company):
    p = pay(biller, org, 5000).json()
    assert (p["applied_cents"], p["unapplied_cents"], p["applications"]) == (0, 5000, [])


# ---- validation ----
def test_cannot_apply_more_than_the_balance_or_the_payment(biller, org, company):
    i = final_invoice(biller, org, 10000)
    assert (
        pay(biller, org, 20000, [{"invoice_id": i["id"], "amount_cents": 10001}]).status_code == 409
    )
    assert (
        pay(biller, org, 5000, [{"invoice_id": i["id"], "amount_cents": 6000}]).status_code == 409
    )  # more than the payment
    pay(biller, org, 9000, [{"invoice_id": i["id"], "amount_cents": 9000}])
    r = pay(biller, org, 5000, [{"invoice_id": i["id"], "amount_cents": 2000}])
    assert r.status_code == 409 and "balance" in r.json()["detail"]
    assert len(biller.get("/api/payments").json()["items"]) == 1  # the failed one left nothing


def test_only_finalized_invoices_of_the_same_client_can_be_paid(biller, make_org, org, company):
    other = make_org("Other Co")
    draft = biller.post(
        "/api/invoices", json={"organization_id": org, "include_unbilled": False}
    ).json()
    biller.post(
        f"/api/invoices/{draft['id']}/lines", json={"description": "x", "unit_price_cents": 100}
    )
    voided = final_invoice(biller, org, 100)
    biller.post(f"/api/invoices/{voided['id']}/void", json={"reason": "mistake"})
    theirs = final_invoice(biller, other["id"], 100)
    for target in (draft["id"], voided["id"], theirs["id"]):
        assert (
            pay(biller, org, 100, [{"invoice_id": target, "amount_cents": 100}]).status_code == 409
        ), target
    assert pay(biller, org, 100, [{"invoice_id": 999, "amount_cents": 100}]).status_code == 404


def test_payment_input_validation(biller, org, company):
    assert pay(biller, org, 0).status_code == 422
    assert pay(biller, org, -5).status_code == 422
    assert pay(biller, 999, 100).status_code == 404
    assert (
        biller.post(
            "/api/payments", json={"organization_id": org, "amount_cents": 100, "method": "bitcoin"}
        ).status_code
        == 422
    )
    future = (biz_today() + timedelta(days=3)).isoformat()
    assert pay(biller, org, 100, received_on=future).status_code == 409
    i = final_invoice(biller, org, 500)
    dup = [{"invoice_id": i["id"], "amount_cents": 100}] * 2
    assert pay(biller, org, 500, dup).status_code == 409
    old = pay(biller, org, 100, received_on="2020-01-15").json()
    assert old["received_on"] == "2020-01-15"


def test_apply_endpoint_rules(biller, make_org, org, company):
    a, b = final_invoice(biller, org, 5000), final_invoice(biller, org, 5000)
    other = final_invoice(biller, make_org("Other Co")["id"], 5000)
    p = pay(biller, org, 6000, [{"invoice_id": a["id"], "amount_cents": 5000}]).json()  # 1000 left
    url = f"/api/payments/{p['id']}/apply"
    assert biller.post(url, json={"invoice_id": b["id"], "amount_cents": 1001}).status_code == 409
    assert (
        biller.post(url, json={"invoice_id": other["id"], "amount_cents": 100}).status_code == 409
    )  # different client
    assert (
        biller.post(url, json={"invoice_id": a["id"], "amount_cents": 100}).status_code == 409
    )  # already fully paid
    assert biller.post(url, json={"invoice_id": 999, "amount_cents": 1}).status_code == 404
    assert (
        biller.post(
            "/api/payments/999/apply", json={"invoice_id": a["id"], "amount_cents": 1}
        ).status_code
        == 404
    )
    assert biller.post(url, json={"invoice_id": b["id"], "amount_cents": 0}).status_code == 422
    assert biller.post(url, json={"invoice_id": b["id"], "amount_cents": 1000}).status_code == 200
    assert biller.get("/api/payments/999").status_code == 404


# ---- undoing things ----
def test_unapplying_returns_the_money_to_credit_and_reopens_the_invoice(
    admin, biller, org, company
):
    i = final_invoice(biller, org, 10000)
    p = pay(biller, org, 10000, [{"invoice_id": i["id"], "amount_cents": 10000}]).json()
    app_id = p["applications"][0]["id"]
    assert (
        biller.post(f"/api/payment-applications/{app_id}/void", json={"reason": "x"}).status_code
        == 422
    )  # a real reason is required
    r = biller.post(
        f"/api/payment-applications/{app_id}/void", json={"reason": "Applied to wrong invoice"}
    )
    assert r.status_code == 200 and r.json()["void_reason"] == "Applied to wrong invoice"
    assert inv(biller, i["id"])["payment_status"] == "unpaid"
    assert biller.get(f"/api/payments/{p['id']}").json()["unapplied_cents"] == 10000
    assert (
        biller.post(
            f"/api/payment-applications/{app_id}/void", json={"reason": "again please"}
        ).status_code
        == 409
    )
    assert (
        biller.post("/api/payment-applications/999/void", json={"reason": "nope nope"}).status_code
        == 404
    )
    shown = inv(biller, i["id"])["payments"][0]
    assert shown["voided_at"] and shown["void_reason"] == "Applied to wrong invoice"
    ev = admin.get("/api/audit", params={"action": "payment.unapply"}).json()["items"]
    assert ev and ev[0]["detail"]["reason"] == "Applied to wrong invoice"


def test_voiding_a_payment_reopens_what_it_paid(biller, org, company):
    a, b = final_invoice(biller, org, 6000), final_invoice(biller, org, 4000)
    p = pay(
        biller,
        org,
        12000,
        [
            {"invoice_id": a["id"], "amount_cents": 6000},
            {"invoice_id": b["id"], "amount_cents": 4000},
        ],
    ).json()
    assert biller.post(f"/api/payments/{p['id']}/void", json={"reason": ""}).status_code == 422
    v = biller.post(f"/api/payments/{p['id']}/void", json={"reason": "Check bounced"})
    assert v.status_code == 200
    body = v.json()
    assert (body["status"], body["unapplied_cents"], body["void_reason"]) == (
        "void",
        0,
        "Check bounced",
    )
    assert all(x["voided_at"] for x in body["applications"])
    assert inv(biller, a["id"])["balance_cents"] == 6000
    assert inv(biller, b["id"])["payment_status"] == "unpaid"
    assert (
        biller.post(f"/api/payments/{p['id']}/void", json={"reason": "again again"}).status_code
        == 409
    )
    assert (
        biller.post(
            f"/api/payments/{p['id']}/apply", json={"invoice_id": a["id"], "amount_cents": 1}
        ).status_code
        == 409
    )
    assert biller.post("/api/payments/999/void", json={"reason": "nothing here"}).status_code == 404
    assert biller.get("/api/payments", params={"status": "void"}).json()["total"] == 1
    assert biller.get("/api/payments", params={"status": "active"}).json()["total"] == 0


# ---- write-offs ----
def test_write_off_the_whole_balance(admin, biller, org, company):
    i = final_invoice(biller, org, 10000)
    assert (
        biller.post(f"/api/invoices/{i['id']}/write-off", json={"reason": "  "}).status_code == 422
    )
    r = biller.post(
        f"/api/invoices/{i['id']}/write-off", json={"reason": "Client went out of business"}
    )
    assert r.status_code == 201 and r.json()["amount_cents"] == 10000
    after = inv(biller, i["id"])
    assert (after["payment_status"], after["balance_cents"], after["written_off_cents"]) == (
        "written_off",
        0,
        10000,
    )
    assert after["paid_cents"] == 0 and after["write_offs"][0]["reason"].startswith("Client went")
    assert (
        biller.post(f"/api/invoices/{i['id']}/write-off", json={"reason": "again"}).status_code
        == 409
    )  # nothing left to write off
    ev = admin.get("/api/audit", params={"action": "invoice.write_off"}).json()["items"]
    assert ev[0]["detail"]["invoice"] == i["number"]


def test_partial_payment_then_write_off_the_rest(biller, org, company):
    i = final_invoice(biller, org, 10000)
    pay(biller, org, 9000, [{"invoice_id": i["id"], "amount_cents": 9000}])
    assert (
        biller.post(
            f"/api/invoices/{i['id']}/write-off", json={"amount_cents": 1001, "reason": "too much"}
        ).status_code
        == 409
    )
    wo = biller.post(
        f"/api/invoices/{i['id']}/write-off", json={"amount_cents": 400, "reason": "small balance"}
    ).json()
    a = inv(biller, i["id"])
    assert (a["payment_status"], a["balance_cents"]) == ("partial", 600)
    biller.post(f"/api/invoices/{i['id']}/write-off", json={"reason": "goodwill"})
    z = inv(biller, i["id"])
    assert (z["balance_cents"], z["paid_cents"], z["written_off_cents"]) == (0, 9000, 1000)
    # a write-off can be reversed, which reopens the balance
    assert (
        biller.post(
            f"/api/write-offs/{wo['id']}/void", json={"reason": "collected after all"}
        ).status_code
        == 200
    )
    assert inv(biller, i["id"])["balance_cents"] == 400
    assert (
        biller.post(f"/api/write-offs/{wo['id']}/void", json={"reason": "twice twice"}).status_code
        == 409
    )
    assert (
        biller.post("/api/write-offs/999/void", json={"reason": "no such one"}).status_code == 404
    )


def test_write_off_rules(biller, org, company):
    draft = biller.post(
        "/api/invoices", json={"organization_id": org, "include_unbilled": False}
    ).json()
    assert (
        biller.post(f"/api/invoices/{draft['id']}/write-off", json={"reason": "draft"}).status_code
        == 409
    )
    paid = final_invoice(biller, org, 100)
    pay(biller, org, 100, [{"invoice_id": paid["id"], "amount_cents": 100}])
    assert (
        biller.post(
            f"/api/invoices/{paid['id']}/write-off", json={"reason": "already paid"}
        ).status_code
        == 409
    )
    assert (
        biller.post("/api/invoices/999/write-off", json={"reason": "no such one"}).status_code
        == 404
    )


# ---- voiding an invoice that has money on it ----
def test_an_invoice_with_payments_or_write_offs_cannot_be_voided(biller, org, company):
    i = final_invoice(biller, org, 10000)
    p = pay(biller, org, 4000, [{"invoice_id": i["id"], "amount_cents": 4000}]).json()
    r = biller.post(f"/api/invoices/{i['id']}/void", json={"reason": "Wrong client"})
    assert r.status_code == 409 and "void those first" in r.json()["detail"]
    wo = biller.post(f"/api/invoices/{i['id']}/write-off", json={"reason": "uncollectible"}).json()
    biller.post(f"/api/payments/{p['id']}/void", json={"reason": "reversed payment"})
    assert (
        biller.post(f"/api/invoices/{i['id']}/void", json={"reason": "Wrong client"}).status_code
        == 409
    )  # still has the write-off
    biller.post(f"/api/write-offs/{wo['id']}/void", json={"reason": "reversed write-off"})
    assert (
        biller.post(f"/api/invoices/{i['id']}/void", json={"reason": "Wrong client"}).status_code
        == 200
    )


# ---- overdue, filters ----
def test_overdue_status_and_days_past_due(biller, org, company):
    today = biz_today()
    late = final_invoice(biller, org, 5000, invoice_date=today - timedelta(days=45), terms=30)
    fresh = final_invoice(biller, org, 5000, invoice_date=today, terms=30)
    a, b = inv(biller, late["id"]), inv(biller, fresh["id"])
    assert (a["is_overdue"], a["days_past_due"]) == (True, 15)
    assert (b["is_overdue"], b["days_past_due"]) == (False, 0)
    pay(biller, org, 5000, [{"invoice_id": late["id"], "amount_cents": 5000}])
    assert inv(biller, late["id"])["is_overdue"] is False  # paid invoices are never overdue


def test_invoice_list_payment_filters(biller, org, company):
    today = biz_today()
    unpaid = final_invoice(biller, org, 1000, invoice_date=today, terms=30)
    partial = final_invoice(biller, org, 2000, invoice_date=today, terms=30)
    paid = final_invoice(biller, org, 3000, invoice_date=today, terms=30)
    overdue = final_invoice(biller, org, 4000, invoice_date=today - timedelta(days=90), terms=30)
    biller.post("/api/invoices", json={"organization_id": org, "include_unbilled": False})  # draft
    pay(biller, org, 500, [{"invoice_id": partial["id"], "amount_cents": 500}])
    pay(biller, org, 3000, [{"invoice_id": paid["id"], "amount_cents": 3000}])

    def ids(f):
        r = biller.get("/api/invoices", params={"payment_status": f})
        assert r.status_code == 200
        return {i["id"] for i in r.json()["items"]}

    assert ids("open") == {unpaid["id"], partial["id"], overdue["id"]}
    assert ids("overdue") == {overdue["id"]}
    assert ids("paid") == {paid["id"]}
    assert ids("unpaid") == {unpaid["id"], overdue["id"]}
    assert biller.get("/api/invoices", params={"payment_status": "bogus"}).status_code == 422
    row = next(i for i in biller.get("/api/invoices").json()["items"] if i["id"] == partial["id"])
    assert (row["payment_status"], row["balance_cents"]) == ("partial", 1500)
    draft_row = next(
        i for i in biller.get("/api/invoices", params={"status": "draft"}).json()["items"]
    )
    assert draft_row["payment_status"] is None and draft_row["balance_cents"] is None


# ---- aging ----
@pytest.mark.parametrize(
    "days_past_due,bucket",
    [
        (-5, "current_cents"),
        (0, "current_cents"),
        (1, "d1_30_cents"),
        (30, "d1_30_cents"),
        (31, "d31_60_cents"),
        (60, "d31_60_cents"),
        (61, "d61_90_cents"),
        (90, "d61_90_cents"),
        (91, "d90_plus_cents"),
        (400, "d90_plus_cents"),
    ],
)
def test_aging_bucket_boundaries(biller, org, company, days_past_due, bucket):
    final_invoice(
        biller, org, 1000, invoice_date=biz_today() - timedelta(days=days_past_due), terms=0
    )
    row = biller.get("/api/receivables").json()["rows"][0]
    buckets = ("current_cents", "d1_30_cents", "d31_60_cents", "d61_90_cents", "d90_plus_cents")
    assert row[bucket] == 1000 and sum(row[b] for b in buckets) == 1000
    assert row["total_open_cents"] == 1000
    assert row["overdue_invoice_count"] == (1 if days_past_due > 0 else 0)


def test_receivables_report(biller, make_org, org, company):
    today = biz_today()
    beta = make_org("Beta Co")["id"]
    credit_only = make_org("Credit Only Co")["id"]
    a1 = final_invoice(
        biller, org, 10000, invoice_date=today - timedelta(days=45), terms=30
    )  # 15 late
    final_invoice(biller, org, 2000, invoice_date=today, terms=30)  # current
    b1 = final_invoice(
        biller, beta, 50000, invoice_date=today - timedelta(days=130), terms=30
    )  # 100 late
    paid = final_invoice(biller, beta, 999, invoice_date=today, terms=30)
    pay(biller, org, 4000, [{"invoice_id": a1["id"], "amount_cents": 4000}])  # Acme owes 6000+2000
    pay(
        biller, beta, 999, [{"invoice_id": paid["id"], "amount_cents": 999}]
    )  # fully paid: excluded
    biller.post(
        f"/api/invoices/{b1['id']}/write-off",
        json={"amount_cents": 10000, "reason": "partly uncollectible"},
    )
    pay(biller, credit_only, 7500)  # on-account credit, nothing owed
    pay(biller, org, 300)  # Acme also has $3.00 credit
    rep = biller.get("/api/receivables").json()
    rows = {r["organization_name"]: r for r in rep["rows"]}
    assert [r["organization_name"] for r in rep["rows"]] == [
        "Beta Co",
        "Acme Corp",
        "Credit Only Co",
    ]
    beta_row, acme = rows["Beta Co"], rows["Acme Corp"]
    assert (beta_row["total_open_cents"], beta_row["d90_plus_cents"]) == (40000, 40000)
    assert beta_row["oldest_days_past_due"] == 100 and beta_row["open_invoice_count"] == 1
    assert (acme["total_open_cents"], acme["d1_30_cents"], acme["current_cents"]) == (
        8000,
        6000,
        2000,
    )
    assert (acme["credit_cents"], acme["overdue_invoice_count"]) == (300, 1)
    assert (
        rows["Credit Only Co"]["total_open_cents"] == 0
        and rows["Credit Only Co"]["credit_cents"] == 7500
    )
    t = rep["totals"]
    assert (
        t["total_open_cents"] == 48000
        and t["credit_cents"] == 7800
        and t["open_invoice_count"] == 3
    )
    assert t["overdue_invoice_count"] == 2 and t["oldest_days_past_due"] == 100
    assert rep["as_of"] == today.isoformat()


def test_receivables_is_empty_with_nothing_owed(biller):
    r = biller.get("/api/receivables").json()
    assert r["rows"] == [] and r["totals"]["total_open_cents"] == 0


# ---- payments list ----
def test_payment_list_filters_and_paging(biller, make_org, org, company):
    other = make_org("Other Co")["id"]
    for amount in (100, 200, 300):
        pay(biller, org, amount)
    pay(biller, other, 999)
    assert biller.get("/api/payments").json()["total"] == 4
    mine = biller.get("/api/payments", params={"organization_id": org, "limit": 2}).json()
    assert mine["total"] == 3 and len(mine["items"]) == 2
    assert mine["items"][0]["amount_cents"] == 300  # newest first
