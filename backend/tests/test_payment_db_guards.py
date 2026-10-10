"""The payment rules hold even if the API is bypassed: these talk to PostgreSQL directly as the
runtime role. They also prove concurrent requests cannot overpay an invoice."""

import threading

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import new_session, set_org_scope
from tests.test_payments import final_invoice, pay


def run_sql(sql: str, **params):
    with new_session() as db:
        set_org_scope(db, "all")
        try:
            db.execute(text(sql), params)
            db.commit()
        finally:
            db.rollback()


def refuses(sql: str, message: str, **params):
    with pytest.raises(DBAPIError, match=message):
        run_sql(sql, **params)


@pytest.fixture
def world(biller, org_ctx, company):
    org = org_ctx["org"]
    invoice = final_invoice(biller, org, 10000)
    payment = pay(biller, org, 6000, [{"invoice_id": invoice["id"], "amount_cents": 4000}]).json()
    return {
        "org": org,
        "invoice": invoice["id"],
        "payment": payment["id"],
        "application": payment["applications"][0]["id"],
    }


APPLY = (
    "INSERT INTO payment_applications (payment_id, invoice_id, organization_id, amount_cents) "
    "VALUES (:p, :i, :o, :a)"
)


def test_database_refuses_to_over_apply(world):
    w = world
    # invoice has 6000 left; payment has 2000 left
    refuses(
        APPLY, "more than the payment amount", p=w["payment"], i=w["invoice"], o=w["org"], a=2001
    )
    run_sql(
        APPLY, p=w["payment"], i=w["invoice"], o=w["org"], a=2000
    )  # exactly the remainder is fine


def test_database_refuses_more_than_the_invoice_balance(biller, world, org_ctx):
    w = world
    big = pay(biller, w["org"], 50000).json()  # plenty of credit
    refuses(APPLY, "more than the invoice balance", p=big["id"], i=w["invoice"], o=w["org"], a=6001)
    run_sql(APPLY, p=big["id"], i=w["invoice"], o=w["org"], a=6000)


def test_database_refuses_bad_targets(biller, world, make_org):
    w = world
    draft = biller.post(
        "/api/invoices", json={"organization_id": w["org"], "include_unbilled": False}
    ).json()["id"]
    refuses(APPLY, "finalized invoice", p=w["payment"], i=draft, o=w["org"], a=1)
    other_org = make_org("Other")["id"]
    theirs = final_invoice(biller, other_org, 500)["id"]
    refuses(APPLY, "different clients", p=w["payment"], i=theirs, o=other_org, a=1)
    refuses(APPLY, "different clients", p=w["payment"], i=w["invoice"], o=other_org, a=1)
    biller.post(f"/api/payments/{w['payment']}/void", json={"reason": "bounced"})
    refuses(APPLY, "voided payment", p=w["payment"], i=w["invoice"], o=w["org"], a=1)


def test_payments_are_immutable_except_for_voiding(world):
    w = world
    refuses(
        "UPDATE payments SET amount_cents = 1 WHERE id = :p", "cannot be edited", p=w["payment"]
    )
    refuses("UPDATE payments SET reference = 'x' WHERE id = :p", "cannot be edited", p=w["payment"])
    refuses(
        "UPDATE payments SET status = 'void', voided_at = now(), void_reason = 'x', "
        "amount_cents = 1 WHERE id = :p",
        "cannot be edited",
        p=w["payment"],
    )
    with pytest.raises(DBAPIError):
        run_sql("DELETE FROM payments WHERE id = :p", p=w["payment"])
    run_sql(
        "UPDATE payments SET status = 'void', voided_at = now(), void_reason = 'test' "
        "WHERE id = :p",
        p=w["payment"],
    )  # a clean void is allowed


def test_a_void_payment_and_void_application_are_frozen(biller, world):
    w = world
    biller.post(f"/api/payments/{w['payment']}/void", json={"reason": "bounced"})
    refuses("UPDATE payments SET status = 'active' WHERE id = :p", "immutable", p=w["payment"])
    refuses(
        "UPDATE payment_applications SET amount_cents = 1 WHERE id = :a",
        "immutable",
        a=w["application"],
    )


def test_applications_can_only_be_voided_never_edited_or_deleted(world):
    w = world
    refuses(
        "UPDATE payment_applications SET amount_cents = 1 WHERE id = :a",
        "can only be voided",
        a=w["application"],
    )
    refuses(
        "UPDATE payment_applications SET invoice_id = invoice_id + 1 WHERE id = :a",
        "can only be voided",
        a=w["application"],
    )
    with pytest.raises(DBAPIError):
        run_sql("DELETE FROM payment_applications WHERE id = :a", a=w["application"])
    with pytest.raises(DBAPIError, match="void_reason|ck_applications_void"):
        run_sql(
            "UPDATE payment_applications SET voided_at = now() WHERE id = :a", a=w["application"]
        )
    run_sql(
        "UPDATE payment_applications SET voided_at = now(), void_reason = 'test' WHERE id = :a",
        a=w["application"],
    )


def test_write_off_guards(biller, world):
    w = world
    ins = (
        "INSERT INTO write_offs (invoice_id, organization_id, amount_cents, reason) "
        "VALUES (:i, :o, :a, :r)"
    )
    refuses(ins, "more than the invoice balance", i=w["invoice"], o=w["org"], a=6001, r="too much")
    refuses(ins, "ck_write_offs_reason", i=w["invoice"], o=w["org"], a=1, r="  ")
    run_sql(ins, i=w["invoice"], o=w["org"], a=6000, r="uncollectible")
    wo = biller.post(f"/api/invoices/{w['invoice']}/write-off", json={"reason": "nothing left"})
    assert wo.status_code == 409
    refuses("UPDATE write_offs SET amount_cents = 1", "can only be voided")
    with pytest.raises(DBAPIError):
        run_sql("DELETE FROM write_offs")


def test_database_refuses_to_void_an_invoice_with_payments(world):
    refuses(
        "UPDATE invoices SET status = 'void', voided_at = now(), void_reason = 'x' WHERE id = :i",
        "void those first",
        i=world["invoice"],
    )


def test_runtime_role_can_never_delete_payment_records(world):
    for table in ("payments", "payment_applications", "write_offs"):
        with pytest.raises(DBAPIError, match="permission denied|cannot be deleted"):
            run_sql(f"DELETE FROM {table}")


# ---- concurrency ----
def test_concurrent_payments_cannot_overpay_an_invoice(biller, login, org_ctx, company):
    """Ten simultaneous attempts to pay $30.00 against a $100.00 invoice: exactly three win."""
    org = org_ctx["org"]
    invoice = final_invoice(biller, org, 10000)
    clients = [login("billing", f"biller{i}@example.com") for i in range(10)]
    credit = [pay(biller, org, 3000).json()["id"] for _ in range(10)]  # ten $30 payments on account
    results, gate = [], threading.Barrier(10)

    def attempt(client, payment_id):
        gate.wait()
        r = client.post(
            f"/api/payments/{payment_id}/apply",
            json={"invoice_id": invoice["id"], "amount_cents": 3000},
        )
        results.append(r.status_code)

    threads = [
        threading.Thread(target=attempt, args=(c, p)) for c, p in zip(clients, credit, strict=True)
    ]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == [200, 200, 200] + [409] * 7, results
    final = biller.get(f"/api/invoices/{invoice['id']}").json()
    assert final["paid_cents"] == 9000 and final["balance_cents"] == 1000
    assert final["paid_cents"] <= final["total_cents"]


def test_concurrent_write_off_and_payment_cannot_exceed_the_balance(
    biller, login, org_ctx, company
):
    org = org_ctx["org"]
    invoice = final_invoice(biller, org, 10000)
    p = pay(biller, org, 10000).json()
    a, b = login("billing", "a@example.com"), login("billing", "b@example.com")
    out, gate = {}, threading.Barrier(2)

    def do_pay():
        gate.wait()
        out["pay"] = a.post(
            f"/api/payments/{p['id']}/apply",
            json={"invoice_id": invoice["id"], "amount_cents": 10000},
        ).status_code

    def do_wo():
        gate.wait()
        out["wo"] = b.post(
            f"/api/invoices/{invoice['id']}/write-off",
            json={"reason": "uncollectible", "amount_cents": 10000},
        ).status_code

    ts = [threading.Thread(target=do_pay), threading.Thread(target=do_wo)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(out.values()) in ([200, 409], [201, 409]), out
    final = biller.get(f"/api/invoices/{invoice['id']}").json()
    assert final["balance_cents"] == 0 and final["paid_cents"] + final["written_off_cents"] == 10000
