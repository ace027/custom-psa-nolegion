"""Phase 3A: calendar-day proration (docs/BILLING_PLAN.md) and NinjaOne device counts."""

import pytest
from sqlalchemy import text

PERIOD = "2026-07"  # 31 days, so the plan's worked example is exact


def agreement(client, org, **kw):
    body = {
        "organization_id": org,
        "name": "Managed Users",
        "type": "per_user",
        "unit_price_cents": 15000,
        "quantity": 10,
        "start_date": "2020-01-01",
        **kw,
    }
    r = client.post("/api/agreements", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def run_lines(client, org_name="Acme"):
    r = client.post("/api/billing-runs", json={"period": PERIOD})
    assert r.status_code == 201, r.text
    inv = next(i for i in r.json()["invoices"] if i["organization_name"] == org_name)
    return client.get(f"/api/invoices/{inv['id']}").json()


@pytest.fixture
def org(make_org, biller):
    o = make_org("Acme")
    return o["id"]


def test_mid_month_start_gets_a_separate_negative_line(biller, org):
    agreement(biller, org, start_date="2026-07-15")
    inv = run_lines(biller)
    kinds = [(ln["kind"], ln["amount_cents"]) for ln in inv["lines"]]
    # 150,000 x 14/31 = 67,741.935... -> 67,742
    assert kinds == [("agreement", 150000), ("proration", -67742)]
    assert inv["total_cents"] == 82258
    assert "14 of 31 days" in inv["lines"][1]["description"]


def test_tax_follows_the_agreement_on_both_lines(biller, org):
    biller.patch(f"/api/organizations/{org}/billing", json={"tax_rate_bp": 825})
    agreement(biller, org, start_date="2026-07-15", taxable=True)
    inv = run_lines(biller)
    assert [ln["tax_cents"] for ln in inv["lines"]] == [12375, -5589]  # -5,588.715 rounds away
    assert inv["tax_cents"] == 6786 and inv["total_cents"] == 82258 + 6786


def test_start_on_the_first_and_end_on_the_last_day_have_no_credit(biller, org):
    agreement(biller, org, start_date="2026-07-01", end_date="2026-07-31")
    inv = run_lines(biller)
    assert [ln["kind"] for ln in inv["lines"]] == ["agreement"]


def test_start_and_end_inside_the_month_is_one_credit_for_the_outside_days(biller, org):
    agreement(biller, org, start_date="2026-07-11", end_date="2026-07-20")  # 10 days active
    inv = run_lines(biller)
    # 21 days outside: 150,000 x 21/31 = 101,612.9 -> 101,613
    assert [ln["amount_cents"] for ln in inv["lines"]] == [150000, -101613]


def test_ending_mid_month_credits_the_rest(biller, org):
    agreement(biller, org, end_date="2026-07-10")  # 21 days not covered
    inv = run_lines(biller)
    assert inv["lines"][1]["amount_cents"] == -101613


def test_flat_agreements_prorate_too(biller, org):
    agreement(
        biller, org, type="flat", quantity=1, unit_price_cents=100000, start_date="2026-07-16"
    )
    inv = run_lines(biller)  # 15 days not covered: 100,000 x 15/31 = 48,387.09 -> 48,387
    assert [ln["amount_cents"] for ln in inv["lines"]] == [100000, -48387]


def test_voiding_the_invoice_frees_both_lines(biller, org, owner):
    agreement(biller, org, start_date="2026-07-15")
    inv = run_lines(biller)
    biller.post(f"/api/invoices/{inv['id']}/void", json={})
    rows = owner.execute(
        text("SELECT kind, voided FROM invoice_lines WHERE invoice_id = :i ORDER BY id"),
        {"i": inv["id"]},
    ).all()
    assert rows == [("agreement", True), ("proration", True)]


def test_revenue_report_nets_the_credit_into_agreement_revenue(admin, biller, org, company):
    agreement(biller, org, start_date="2026-07-15")
    inv = run_lines(biller)
    run_id = inv["billing_run_id"]
    assert biller.post(f"/api/billing-runs/{run_id}/review").status_code == 200
    assert biller.post(f"/api/billing-runs/{run_id}/finalize").status_code == 200
    r = admin.get("/api/reports/revenue")
    assert r.status_code == 200, r.text
    row = r.json()["clients"][0]
    assert row["agreement_cents"] == 82258 and row["subtotal_cents"] == 82258


# ---- device counts ----
def _asset(owner, org, name, retired=False, source="ninjaone"):
    aid = owner.execute(
        text(
            "INSERT INTO assets (organization_id, kind, name, retired_at) "
            "VALUES (:o, 'computer', :n, CASE WHEN :r THEN now() END) RETURNING id"
        ),
        {"o": org, "n": name, "r": retired},
    ).scalar_one()
    iid = owner.execute(
        text("SELECT id FROM integrations WHERE kind = :k LIMIT 1"), {"k": source}
    ).scalar_one_or_none()
    if iid is None:
        iid = owner.execute(
            text(
                "INSERT INTO integrations (kind, name, base_url) VALUES (:k, :k, 'https://x') "
                "RETURNING id"
            ),
            {"k": source},
        ).scalar_one()
    owner.execute(
        text(
            "INSERT INTO asset_sources (asset_id, organization_id, integration_id, external_id, "
            "data, data_hash) VALUES (:a, :o, :i, :e, '{}'::jsonb, 'h')"
        ),
        {"a": aid, "o": org, "i": iid, "e": name},
    )


def test_device_count_is_a_suggestion_and_changes_nothing(biller, org, owner):
    a = agreement(biller, org, type="per_device", quantity=2, unit_price_cents=2500)
    _asset(owner, org, "PC-1")
    _asset(owner, org, "PC-2")
    _asset(owner, org, "PC-3")
    _asset(owner, org, "PC-OLD", retired=True)  # retired: not counted
    _asset(owner, org, "HUDU-ONLY", source="hudu")  # not reported by NinjaOne: not counted
    r = biller.get(f"/api/agreements/{a['id']}/device-count")
    assert r.json() == {"ninjaone_devices": 3, "agreement_quantity": 2, "differs": True}
    assert biller.get(f"/api/agreements/{a['id']}").json()["quantity"] == 2
    assert biller.get(f"/api/agreements/{a['id']}/quantity-log").json()[0]["new_quantity"] == 2
    # the one-click update is the ordinary PATCH, which logs the change with a reason
    biller.patch(f"/api/agreements/{a['id']}", json={"quantity": 3, "reason": "NinjaOne count"})
    log = biller.get(f"/api/agreements/{a['id']}/quantity-log").json()
    assert log[0]["new_quantity"] == 3 and log[0]["old_quantity"] == 2


def test_device_count_only_for_per_device(biller, org):
    flat = agreement(biller, org, type="flat", quantity=1)
    assert biller.get(f"/api/agreements/{flat['id']}/device-count").status_code == 409
    assert biller.get("/api/agreements/999999/device-count").status_code == 404
