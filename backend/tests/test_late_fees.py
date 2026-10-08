"""Late fees: opt-in, person-approved, never compounding (docs/BILLING_PLAN.md slice C)."""

from datetime import timedelta

import pytest
from sqlalchemy import text

from tests.conftest import biz_today
from tests.test_payment_db_guards import refuses
from tests.test_payments import final_invoice, pay


@pytest.fixture
def rule(admin):
    def _set(bp=150, flat=0, grace=15, cap=1):
        r = admin.patch(
            "/api/settings",
            json={
                "late_fee_percent_bp": bp,
                "late_fee_flat_cents": flat,
                "late_fee_grace_days": grace,
                "late_fee_max_per_invoice": cap,
            },
        )
        assert r.status_code == 200, r.text

    return _set


def overdue(biller, org, cents=100000, days=40, terms=30):
    """A final invoice that is `days` past due."""
    d = biz_today() - timedelta(days=days + terms)
    return final_invoice(biller, org, cents, invoice_date=d, terms=terms)


def opt_in(admin, org, on=True):
    r = admin.patch(f"/api/organizations/{org}/billing", json={"late_fees_enabled": on})
    assert r.status_code == 200, r.text


def preview(client, **kw):
    r = client.get("/api/late-fees/preview", params=kw)
    assert r.status_code == 200, r.text
    return r.json()


def test_worked_example_percent_and_flat(admin, biller, org_ctx, company, rule):
    org = org_ctx["org"]
    rule(bp=150, flat=1000)
    opt_in(admin, org)
    i = overdue(biller, org, 100000)
    p = preview(biller)
    assert p["configured"] and len(p["rows"]) == 1
    row = p["rows"][0]
    # $1,000.00 x 1.5% = $15.00, plus $10.00 flat
    assert (row["base_cents"], row["percent_fee_cents"], row["flat_fee_cents"]) == (
        100000,
        1500,
        1000,
    )
    assert row["fee_cents"] == 2500 and row["days_overdue"] == 40
    r = admin.post("/api/late-fees/apply", json={"invoice_ids": [i["id"]]})
    assert r.status_code == 201, r.text
    assert r.json()[0]["fee_cents"] == 2500
    charges = admin.get("/api/product-charges", params={"organization_id": org}).json()
    items = charges["items"] if isinstance(charges, dict) else charges
    assert len(items) == 1 and items[0]["unit_price_cents"] == 2500
    assert items[0]["taxable"] is False and i["number"] in items[0]["description"]


def test_half_up_rounding(admin, biller, org_ctx, company, rule):
    org = org_ctx["org"]
    rule(bp=150)
    opt_in(admin, org)
    overdue(biller, org, 3370)  # 33.70 x 1.5% = 0.5055 -> 51 (half-up)
    assert preview(biller)["rows"][0]["fee_cents"] == 51


def test_off_by_default_and_unconfigured(admin, biller, org_ctx, company, rule):
    org = org_ctx["org"]
    overdue(biller, org)
    assert preview(biller) == {
        "configured": False,
        "percent_bp": 0,
        "flat_cents": 0,
        "grace_days": 15,
        "max_per_invoice": 1,
        "rows": [],
    }
    rule()
    assert preview(biller)["rows"] == []  # rule set but the client has not opted in
    opt_in(admin, org)
    assert len(preview(biller)["rows"]) == 1
    opt_in(admin, org, False)
    assert preview(biller)["rows"] == []


def test_grace_period_boundary(admin, biller, org_ctx, company, rule):
    org = org_ctx["org"]
    rule(grace=15)
    opt_in(admin, org)
    overdue(biller, org, days=15)
    assert preview(biller)["rows"] == []
    admin.patch("/api/settings", json={"late_fee_grace_days": 14})
    assert len(preview(biller)["rows"]) == 1


def test_fee_uses_remaining_balance_and_paid_invoices_skip(admin, biller, org_ctx, company, rule):
    org = org_ctx["org"]
    rule(bp=100)
    opt_in(admin, org)
    i = overdue(biller, org, 100000)
    assert (
        pay(biller, org, 40000, [{"invoice_id": i["id"], "amount_cents": 40000}]).status_code == 201
    )
    row = preview(biller)["rows"][0]
    assert (row["balance_cents"], row["base_cents"], row["fee_cents"]) == (60000, 60000, 600)
    assert (
        pay(biller, org, 60000, [{"invoice_id": i["id"], "amount_cents": 60000}]).status_code == 201
    )
    assert preview(biller)["rows"] == []


def test_cap_and_voiding_frees_the_slot(admin, biller, org_ctx, company, rule):
    org = org_ctx["org"]
    rule(bp=100, cap=1)
    opt_in(admin, org)
    i = overdue(biller, org, 100000)
    applied = admin.post("/api/late-fees/apply", json={"invoice_ids": [i["id"]]}).json()
    assert preview(biller)["rows"] == []
    r = admin.post("/api/late-fees/apply", json={"invoice_ids": [i["id"]]})
    assert r.status_code == 409
    admin.post(f"/api/product-charges/{applied[0]['charge_id']}/void")
    assert len(preview(biller)["rows"]) == 1
    # cap of 2 allows a second fee while the first stands
    admin.patch("/api/settings", json={"late_fee_max_per_invoice": 2})
    admin.post("/api/late-fees/apply", json={"invoice_ids": [i["id"]]})
    assert preview(biller)["rows"][0]["fees_so_far"] == 1
    assert len(preview(biller)["rows"]) == 1


def test_fees_never_compound(admin, biller, org_ctx, company, rule):
    org = org_ctx["org"]
    rule(bp=100, cap=5)
    opt_in(admin, org)
    i = overdue(biller, org, 100000)
    admin.post("/api/late-fees/apply", json={"invoice_ids": [i["id"]]})
    # the $10 fee is billed on a new invoice that also goes overdue; its base excludes the fee
    d = biz_today() - timedelta(days=80)
    nxt = biller.post(
        "/api/invoices", json={"organization_id": org, "include_unbilled": True}
    ).json()
    assert nxt["total_cents"] == 1000
    fin = biller.post(f"/api/invoices/{nxt['id']}/finalize", json={"invoice_date": d.isoformat()})
    assert fin.status_code == 200, fin.text
    rows = {r["invoice_id"]: r for r in preview(biller)["rows"]}
    assert nxt["id"] not in rows  # only fee lines: nothing to base a fee on
    assert i["id"] in rows


def test_client_amounts_are_not_trusted_and_ineligible_rejected(
    admin, biller, org_ctx, company, rule
):
    org = org_ctx["org"]
    rule()
    fresh = final_invoice(biller, org, 5000)
    opt_in(admin, org)
    r = admin.post("/api/late-fees/apply", json={"invoice_ids": [fresh["id"]]})
    assert r.status_code == 409
    assert admin.post("/api/late-fees/apply", json={"invoice_ids": []}).status_code == 422


def test_isolation_between_clients_and_permissions(
    admin, biller, login, make_org, org_ctx, company, rule, owner
):
    rule()
    a = org_ctx["org"]
    b = make_org("Other Co")["id"]
    for o in (a, b):
        opt_in(admin, o)
        overdue(biller, o)
    assert {r["organization_id"] for r in preview(biller)["rows"]} == {a, b}
    assert {r["organization_id"] for r in preview(biller, organization_id=b)["rows"]} == {b}
    tech = login("tech")
    assert tech.get("/api/late-fees/preview").status_code == 200
    assert tech.post("/api/late-fees/apply", json={"invoice_ids": [1]}).status_code == 403
    flags = owner.execute(
        text(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname = 'late_fee_applications'"
        )
    ).fetchall()
    assert [tuple(f) for f in flags] == [(True, True)]


def test_audit_and_db_immutability(admin, biller, org_ctx, company, rule):
    org = org_ctx["org"]
    rule()
    opt_in(admin, org)
    i = overdue(biller, org)
    app = admin.post("/api/late-fees/apply", json={"invoice_ids": [i["id"]]}).json()[0]
    assert (
        admin.get("/api/late-fees/applied", params={"organization_id": org}).json()[0]["id"]
        == app["id"]
    )
    log = admin.get("/api/audit", params={"limit": 200})
    assert log.status_code == 200 and "late_fee.apply" in log.text
    refuses("UPDATE late_fee_applications SET fee_cents = 1", "immutable|permission denied")
