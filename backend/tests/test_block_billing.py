"""Block-hour agreements in the monthly run: consumption, overage, proration, void, ad-hoc.

Exact-cent cases from docs/BILLING.md ("Worked example: block hours") and docs/BILLING_PLAN.md D.
"""

from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.billing import allocate_block, block_included_minutes

PERIOD = "2026-07"  # 31 days, so the 15th-of-the-month example matches the docs (17 of 31)
START, END = date(2026, 7, 1), date(2026, 7, 31)


# ---- pure functions ----
def _a(block_minutes=600, start=date(2026, 1, 1), end=None):
    return SimpleNamespace(block_minutes=block_minutes, start_date=start, end_date=end)


@pytest.mark.parametrize(
    "agreement, increment, expected",
    [
        (_a(), 15, 600),  # full month: exactly block_minutes
        (_a(start=date(2026, 7, 15)), 15, 315),  # 600 x 17/31 = 329.03 -> down to 315
        (_a(start=date(2026, 7, 15)), 30, 300),  # same days, 30-minute increment
        (_a(end=date(2026, 7, 10)), 15, 180),  # 600 x 10/31 = 193.5 -> 180
        (_a(block_minutes=900, start=date(2026, 7, 1), end=date(2026, 7, 31)), 30, 900),
    ],
)
def test_block_included_minutes(agreement, increment, expected):
    assert block_included_minutes(agreement, START, END, increment) == expected


def test_allocate_block_empty():
    assert allocate_block([], 600) == {}


def test_allocate_block_exact_fit():
    assert allocate_block([(1, 300), (2, 300)], 600) == {1: 300, 2: 300}


def test_allocate_block_single_oversized_entry():
    assert allocate_block([(7, 720), (8, 60)], 600) == {7: 600, 8: 0}


def test_allocate_block_straddle_and_nothing_included():
    assert allocate_block([(1, 540), (2, 90), (3, 30)], 600) == {1: 540, 2: 60, 3: 0}
    assert allocate_block([(1, 60)], 0) == {1: 0}


# ---- helpers ----
def block(client, org, **kw):
    body = {
        "organization_id": org,
        "name": "Retainer",
        "type": "block",
        "unit_price_cents": 100000,
        "block_minutes": 600,
        "start_date": "2026-01-01",
        **kw,
    }
    r = client.post("/api/agreements", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def run(client, org_name="Acme"):
    r = client.post("/api/billing-runs", json={"period": PERIOD})
    assert r.status_code == 201, r.text
    inv = next(i for i in r.json()["invoices"] if i["organization_name"] == org_name)
    return client.get(f"/api/invoices/{inv['id']}").json()


def lines(inv):
    return [(ln["kind"], ln["quantity"], ln["amount_cents"]) for ln in inv["lines"]]


def entries(owner, ids):
    """id -> (block_minutes_covered, invoice_line_id)"""
    rows = owner.execute(
        text(
            "SELECT id, block_minutes_covered, invoice_line_id FROM time_entries "
            "WHERE id = ANY(:ids)"
        ),
        {"ids": list(ids)},
    ).all()
    return {r.id: (r.block_minutes_covered, r.invoice_line_id) for r in rows}


def line_id(inv, kind):
    return next(ln["id"] for ln in inv["lines"] if ln["kind"] == kind)


@pytest.fixture
def acme(make_org_with_ticket, biller, wt, company):
    org, ticket = make_org_with_ticket("Acme")
    return {"org": org["id"], "ticket": ticket["id"]}


def day(n):
    return f"2026-07-{n:02d}"


# ---- the monthly run ----
def test_plan_example_overage_bills_at_the_normal_rate(biller, acme, wt, log, owner):
    block(biller, acme["org"])
    ids = [
        log(acme["ticket"], wt["Remote"], m, work_date=day(i + 1))["id"]
        for i, m in enumerate([180, 180, 240, 150])  # 12.5 h
    ]
    inv = run(biller)
    assert lines(inv) == [("agreement", "1.0000", 100000), ("time", "2.5000", 37500)]
    assert inv["total_cents"] == 137500
    assert inv["lines"][0]["description"] == "Retainer: 10 h included, 10 h used"
    block_id, time_id = line_id(inv, "agreement"), line_id(inv, "time")
    assert entries(owner, ids) == {
        ids[0]: (180, block_id),
        ids[1]: (180, block_id),
        ids[2]: (240, block_id),  # 180 + 180 + 240 = 600: the block is used up exactly
        ids[3]: (0, time_id),
    }


def test_straddle_entry_is_split_by_minutes(biller, acme, wt, log, owner):
    block(biller, acme["org"])
    first = log(acme["ticket"], wt["Remote"], 540, work_date=day(2))["id"]
    straddle = log(acme["ticket"], wt["Remote"], 90, work_date=day(3))["id"]
    inv = run(biller)
    assert lines(inv) == [("agreement", "1.0000", 100000), ("time", "0.5000", 7500)]
    assert entries(owner, [first, straddle]) == {
        first: (540, line_id(inv, "agreement")),
        straddle: (60, line_id(inv, "time")),
    }


def test_under_use_bills_the_block_only_and_hours_expire(biller, acme, wt, log, owner):
    block(biller, acme["org"])
    ids = [log(acme["ticket"], wt["Remote"], 180, work_date=day(d))["id"] for d in (5, 6)]
    inv = run(biller)
    assert lines(inv) == [("agreement", "1.0000", 100000)]
    assert inv["lines"][0]["description"].endswith("6 h used")
    assert set(entries(owner, ids).values()) == {(180, line_id(inv, "agreement"))}


def test_zero_time_logged_still_bills_the_block(biller, acme):
    block(biller, acme["org"])
    inv = run(biller)
    assert lines(inv) == [("agreement", "1.0000", 100000)]
    assert inv["lines"][0]["description"] == "Retainer: 10 h included, 0 h used"


def test_exactly_the_included_hours_has_no_overage(biller, acme, wt, log, owner):
    block(biller, acme["org"])
    ids = [log(acme["ticket"], wt["Remote"], 300, work_date=day(d))["id"] for d in (1, 2)]
    inv = run(biller)
    assert lines(inv) == [("agreement", "1.0000", 100000)]
    assert inv["lines"][0]["description"].endswith("10 h used")
    assert set(entries(owner, ids).values()) == {(300, line_id(inv, "agreement"))}


def test_single_entry_larger_than_the_block(biller, acme, wt, log, owner):
    block(biller, acme["org"])
    big = log(acme["ticket"], wt["Remote"], 720, work_date=day(9))["id"]
    inv = run(biller)
    assert lines(inv) == [("agreement", "1.0000", 100000), ("time", "2.0000", 30000)]
    assert entries(owner, [big])[big] == (600, line_id(inv, "time"))


def test_not_covered_work_type_bills_fully_and_does_not_consume(admin, biller, acme, wt, log):
    ah = {w["name"]: w["id"] for w in admin.get("/api/work-types").json()}["After hours"]
    r = admin.patch(
        f"/api/billing/work-types/{ah}", json={"rate_cents": 25000, "block_covered": False}
    )
    assert r.status_code == 200, r.text
    block(biller, acme["org"])
    log(acme["ticket"], ah, 120, work_date=day(1))
    log(acme["ticket"], wt["Remote"], 60, work_date=day(2))
    inv = run(biller)
    assert lines(inv) == [("agreement", "1.0000", 100000), ("time", "2.0000", 50000)]
    assert inv["lines"][0]["description"].endswith("1 h used")
    assert "After hours" in inv["lines"][1]["description"]


def test_prior_month_unbilled_time_bills_normally(biller, acme, wt, log, owner):
    block(biller, acme["org"])
    june = log(acme["ticket"], wt["Remote"], 120, work_date="2026-06-30")["id"]
    july = log(acme["ticket"], wt["Remote"], 600, work_date=day(1))["id"]
    inv = run(biller)
    assert lines(inv) == [("agreement", "1.0000", 100000), ("time", "2.0000", 30000)]
    assert entries(owner, [june, july]) == {
        june: (0, line_id(inv, "time")),
        july: (600, line_id(inv, "agreement")),
    }


def test_mid_month_start_prorates_price_and_included_minutes(biller, acme, wt, log, owner):
    block(biller, acme["org"], start_date="2026-07-15")
    e = log(acme["ticket"], wt["Remote"], 360, work_date=day(20))["id"]
    inv = run(biller)
    # included 600 x 17/31 -> 315 min; 45 min overage = 0.75 h x 15,000 = 11,250
    assert lines(inv) == [
        ("agreement", "1.0000", 100000),
        ("proration", "1.0000", -45161),
        ("time", "0.7500", 11250),
    ]
    assert inv["total_cents"] == 54839 + 11250
    assert inv["lines"][0]["description"] == "Retainer: 5.25 h included, 5.25 h used"
    assert entries(owner, [e])[e] == (315, line_id(inv, "time"))


def test_block_ending_mid_month(biller, acme, wt, log, owner):
    block(biller, acme["org"], end_date="2026-07-10")
    e = log(acme["ticket"], wt["Remote"], 240, work_date=day(5))["id"]
    inv = run(biller)
    # included 600 x 10/31 = 193.5 -> 180; price credit 100,000 x 21/31 = 67,741.9 -> 67,742
    assert lines(inv) == [
        ("agreement", "1.0000", 100000),
        ("proration", "1.0000", -67742),
        ("time", "1.0000", 15000),
    ]
    assert inv["lines"][0]["description"] == "Retainer: 3 h included, 3 h used"
    assert entries(owner, [e])[e] == (180, line_id(inv, "time"))


def test_consumption_follows_work_date_not_ticket_order(admin, biller, acme, wt, log, owner):
    later_ticket = admin.post(
        "/api/tickets", json={"organization_id": acme["org"], "subject": "Second issue"}
    ).json()
    block(biller, acme["org"])
    a = log(acme["ticket"], wt["Remote"], 300, work_date=day(10))["id"]  # lower ticket and id
    b = log(later_ticket["id"], wt["Remote"], 480, work_date=day(5))["id"]
    inv = run(biller)
    assert lines(inv) == [("agreement", "1.0000", 100000), ("time", "3.0000", 45000)]
    assert entries(owner, [a, b]) == {
        b: (480, line_id(inv, "agreement")),
        a: (120, line_id(inv, "time")),
    }
    assert inv["lines"][1]["description"].startswith("Ticket #10001")


def test_taxable_overage_uses_the_org_rate_only_for_taxable_work_types(biller, acme, wt, log):
    biller.patch(f"/api/organizations/{acme['org']}/billing", json={"tax_rate_bp": 825})
    block(biller, acme["org"])
    log(acme["ticket"], wt["Remote"], 600, work_date=day(1))
    log(acme["ticket"], wt["Onsite"], 60, work_date=day(2))  # $200/h, taxable
    log(acme["ticket"], wt["Remote"], 60, work_date=day(3))
    inv = run(biller)
    got = sorted(
        (ln["kind"], ln["amount_cents"], ln["tax_cents"], ln["tax_rate_bp"]) for ln in inv["lines"]
    )
    assert got == [
        ("agreement", 100000, 0, 0),
        ("time", 15000, 0, 0),
        ("time", 20000, 1650, 825),
    ]
    assert inv["total_cents"] == 100000 + 15000 + 20000 + 1650


def _snapshot(inv):
    return [
        (ln["kind"], ln["description"], ln["quantity"], ln["amount_cents"], ln["tax_cents"])
        for ln in inv["lines"]
    ]


def test_void_releases_and_rerun_is_identical(biller, acme, wt, log, owner):
    block(biller, acme["org"])
    ids = [
        log(acme["ticket"], wt["Remote"], m, work_date=day(i + 1))["id"]
        for i, m in enumerate([540, 90, 60])
    ]
    inv = run(biller)
    before = _snapshot(inv)
    covered_before = {k: v[0] for k, v in entries(owner, ids).items()}
    assert covered_before == {ids[0]: 540, ids[1]: 60, ids[2]: 0}
    r = biller.post(f"/api/invoices/{inv['id']}/void", json={})
    assert r.status_code == 200, r.text
    assert set(entries(owner, ids).values()) == {(0, None)}
    r = biller.post(f"/api/billing-runs/{inv['billing_run_id']}/cancel")
    assert r.status_code == 200, r.text
    again = run(biller)
    assert again["id"] != inv["id"]
    assert _snapshot(again) == before
    assert {k: v[0] for k, v in entries(owner, ids).items()} == covered_before


def test_straddle_without_overage_rate_stays_unbilled_and_resets_on_void(
    admin, biller, acme, wt, log, owner
):
    ah = {w["name"]: w["id"] for w in admin.get("/api/work-types").json()}["After hours"]
    block(biller, acme["org"])  # After hours: covered by blocks, but no hourly rate
    first = log(acme["ticket"], wt["Remote"], 540, work_date=day(1))["id"]
    straddle = log(acme["ticket"], ah, 90, work_date=day(2))["id"]
    inv = run(biller)
    assert lines(inv) == [("agreement", "1.0000", 100000)]
    assert entries(owner, [first, straddle]) == {
        first: (540, line_id(inv, "agreement")),
        straddle: (60, None),
    }
    assert any("No hourly rate" in w and "30 min" in w for w in inv["warnings"])
    assert biller.post(f"/api/invoices/{inv['id']}/void", json={}).status_code == 200
    assert entries(owner, [first, straddle]) == {first: (0, None), straddle: (0, None)}


def test_ad_hoc_invoice_leaves_block_month_time_for_the_run(admin, biller, acme, wt, log, owner):
    ah = {w["name"]: w["id"] for w in admin.get("/api/work-types").json()}["After hours"]
    admin.patch(f"/api/billing/work-types/{ah}", json={"rate_cents": 25000, "block_covered": False})
    block(biller, acme["org"])
    covered = log(acme["ticket"], wt["Remote"], 60, work_date=day(2))["id"]
    premium = log(acme["ticket"], ah, 60, work_date=day(2))["id"]
    r = biller.post(
        "/api/invoices", json={"organization_id": acme["org"], "include_unbilled": True}
    )
    assert r.status_code == 201, r.text
    inv = biller.get(f"/api/invoices/{r.json()['id']}").json()
    assert lines(inv) == [("time", "1.0000", 25000)]
    assert any("left for the monthly billing run" in w for w in inv["warnings"])
    assert entries(owner, [covered, premium]) == {
        covered: (0, None),
        premium: (0, line_id(inv, "time")),
    }
    # the run then draws the held entry from the block
    run_inv = run(biller)
    assert lines(run_inv) == [("agreement", "1.0000", 100000)]
    assert entries(owner, [covered])[covered] == (60, line_id(run_inv, "agreement"))


def test_ad_hoc_invoice_bills_time_outside_block_months(biller, acme, wt, log):
    block(biller, acme["org"], start_date="2026-07-01")
    log(acme["ticket"], wt["Remote"], 60, work_date="2026-06-15")
    r = biller.post(
        "/api/invoices", json={"organization_id": acme["org"], "include_unbilled": True}
    )
    inv = biller.get(f"/api/invoices/{r.json()['id']}").json()
    assert lines(inv) == [("time", "1.0000", 15000)]
    assert inv["warnings"] == []


def test_two_clients_only_one_with_a_block(biller, acme, make_org_with_ticket, wt, log, owner):
    beta, t_beta = make_org_with_ticket("Beta")
    block(biller, acme["org"])
    log(acme["ticket"], wt["Remote"], 660, work_date=day(3))
    b = log(t_beta["id"], wt["Remote"], 120, work_date=day(3))["id"]
    alpha_inv = run(biller)
    assert lines(alpha_inv) == [("agreement", "1.0000", 100000), ("time", "1.0000", 15000)]
    beta_inv = next(
        i for i in biller.get("/api/invoices").json()["items"] if i["organization_id"] == beta["id"]
    )
    beta_inv = biller.get(f"/api/invoices/{beta_inv['id']}").json()
    assert lines(beta_inv) == [("time", "2.0000", 30000)]
    assert entries(owner, [b])[b] == (0, line_id(beta_inv, "time"))
