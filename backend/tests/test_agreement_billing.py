"""Billing by agreement (phase 17): all-inclusive flat agreements and block rollover.

Exact-cent cases from docs/BILLING.md ("All-inclusive agreements", "Block rollover").
Remote time is $150/h (the `wt` fixture); blocks are $1,000.00 for 10 h a month.
"""

import pytest
from sqlalchemy import text


# ---- helpers ----
def agreement(client, org, type="block", **kw):
    body = {
        "organization_id": org,
        "name": "Retainer" if type == "block" else "Flat plan",
        "type": type,
        "unit_price_cents": 100000,
        "start_date": "2026-07-01",
        **({"block_minutes": 600} if type == "block" else {}),
        **kw,
    }
    r = client.post("/api/v1/agreements", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def run(client, period, org_id):
    """-> (run id, the client's invoice on it)."""
    r = client.post("/api/v1/billing-runs", json={"period": period})
    assert r.status_code == 201, r.text
    inv = next(i for i in r.json()["invoices"] if i["organization_id"] == org_id)
    return r.json()["id"], client.get(f"/api/v1/invoices/{inv['id']}").json()


def finalize(client, run_id):
    assert client.post(f"/api/v1/billing-runs/{run_id}/review").status_code == 200
    r = client.post(f"/api/v1/billing-runs/{run_id}/finalize")
    assert r.status_code == 200, r.text


def lines(inv):
    return [(ln["kind"], ln["quantity"], ln["amount_cents"]) for ln in inv["lines"]]


def block_text(inv):
    return next(ln["description"] for ln in inv["lines"] if ln["kind"] == "agreement")


def entry(owner, entry_id):
    """-> (block_minutes_covered, invoice_line_id)"""
    r = owner.execute(
        text("SELECT block_minutes_covered, invoice_line_id FROM time_entries WHERE id = :i"),
        {"i": entry_id},
    ).one()
    return r.block_minutes_covered, r.invoice_line_id


@pytest.fixture
def acme(make_org_with_ticket, biller, wt, company):
    org, ticket = make_org_with_ticket("Acme")
    return {"org": org["id"], "ticket": ticket["id"]}


# ---- all-inclusive flat ----
def test_all_inclusive_flat_bills_only_the_fee(biller, acme, wt, log, owner):
    flat = agreement(biller, acme["org"], "flat", all_inclusive=True)
    covered = log(
        acme["ticket"], wt["Remote"], 120, work_date="2026-07-03", agreement_id=flat["id"]
    )
    loose = log(acme["ticket"], wt["Remote"], 60, work_date="2026-07-04", agreement_id=None)
    # an ad-hoc invoice never picks up all-inclusive time either
    r = biller.post(
        "/api/v1/invoices", json={"organization_id": acme["org"], "include_unbilled": True}
    )
    adhoc = biller.get(f"/api/v1/invoices/{r.json()['id']}").json()
    assert lines(adhoc) == [("time", "1.0000", 15000)]  # only the unattached hour
    assert entry(owner, covered["id"]) == (0, None)
    _, inv = run(biller, "2026-07", acme["org"])
    assert lines(inv) == [("agreement", "1.0000", 100000)]
    assert inv["total_cents"] == 100000
    assert entry(owner, covered["id"]) == (0, None)  # recorded and costed, never billed
    assert entry(owner, loose["id"])[1] == adhoc["lines"][0]["id"]


def test_non_inclusive_flat_bills_time_as_today(biller, acme, wt, log, owner):
    flat = agreement(biller, acme["org"], "flat")
    e = log(acme["ticket"], wt["Remote"], 120, work_date="2026-07-03", agreement_id=flat["id"])
    _, inv = run(biller, "2026-07", acme["org"])
    assert lines(inv) == [("agreement", "1.0000", 100000), ("time", "2.0000", 30000)]
    assert inv["total_cents"] == 130000
    assert entry(owner, e["id"]) == (0, inv["lines"][1]["id"])


# ---- block consumption by attachment ----
def test_time_on_another_agreement_does_not_consume_the_block(biller, acme, wt, log, owner):
    agreement(biller, acme["org"])
    flat = agreement(biller, acme["org"], "flat", unit_price_cents=20000)
    e = log(acme["ticket"], wt["Remote"], 120, work_date="2026-07-03", agreement_id=flat["id"])
    _, inv = run(biller, "2026-07", acme["org"])
    assert lines(inv) == [
        ("agreement", "1.0000", 100000),
        ("agreement", "1.0000", 20000),
        ("time", "2.0000", 30000),
    ]
    assert block_text(inv) == "Retainer: 10 h included, 0 h used"
    assert entry(owner, e["id"]) == (0, inv["lines"][2]["id"])


def test_unattached_and_attached_time_consume_the_block(biller, acme, wt, log, owner):
    blk = agreement(biller, acme["org"])
    loose = log(acme["ticket"], wt["Remote"], 300, work_date="2026-07-02", agreement_id=None)
    tied = log(acme["ticket"], wt["Remote"], 420, work_date="2026-07-03", agreement_id=blk["id"])
    _, inv = run(biller, "2026-07", acme["org"])
    assert lines(inv) == [("agreement", "1.0000", 100000), ("time", "2.0000", 30000)]
    assert block_text(inv) == "Retainer: 10 h included, 10 h used"
    assert entry(owner, loose["id"]) == (300, inv["lines"][0]["id"])
    assert entry(owner, tied["id"]) == (300, inv["lines"][1]["id"])


# ---- rollover ----
def test_expire_is_the_default_and_matches_today(biller, acme, wt, log):
    a = agreement(biller, acme["org"])
    assert a["rollover"] == "expire"
    log(acme["ticket"], wt["Remote"], 360, work_date="2026-07-02")
    run_id, _ = run(biller, "2026-07", acme["org"])
    finalize(biller, run_id)
    _, aug = run(biller, "2026-08", acme["org"])
    assert lines(aug) == [("agreement", "1.0000", 100000)]
    assert block_text(aug) == "Retainer: 10 h included, 0 h used"


def test_roll_without_cap_across_three_months(biller, acme, wt, log, owner):
    agreement(biller, acme["org"], rollover="roll")
    log(acme["ticket"], wt["Remote"], 360, work_date="2026-07-02")  # 4 h unused
    run_id, jul = run(biller, "2026-07", acme["org"])
    assert block_text(jul) == "Retainer: 10 h included, 6 h used"
    finalize(biller, run_id)
    run_id, aug = run(biller, "2026-08", acme["org"])  # nothing used: 14 h roll on
    assert block_text(aug) == "Retainer: 14 h included (incl. 4 h carried over), 0 h used"
    assert lines(aug) == [("agreement", "1.0000", 100000)]
    finalize(biller, run_id)
    first = log(acme["ticket"], wt["Remote"], 750, work_date="2026-09-02")
    split = log(acme["ticket"], wt["Remote"], 750, work_date="2026-09-03")
    _, sep = run(biller, "2026-09", acme["org"])  # 240 + 600 carried + 600 = 1440 min
    assert block_text(sep) == "Retainer: 24 h included (incl. 14 h carried over), 24 h used"
    assert lines(sep) == [("agreement", "1.0000", 100000), ("time", "1.0000", 15000)]
    assert sep["total_cents"] == 115000
    assert entry(owner, first["id"]) == (750, sep["lines"][0]["id"])
    assert entry(owner, split["id"]) == (690, sep["lines"][1]["id"])


def test_roll_with_cap(biller, acme, wt, log):
    agreement(biller, acme["org"], rollover="roll", rollover_cap_minutes=120)
    run_id, _ = run(biller, "2026-07", acme["org"])  # 600 unused, capped at 120
    finalize(biller, run_id)
    log(acme["ticket"], wt["Remote"], 660, work_date="2026-08-03")
    run_id, aug = run(biller, "2026-08", acme["org"])
    assert block_text(aug) == "Retainer: 12 h included (incl. 2 h carried over), 11 h used"
    assert lines(aug) == [("agreement", "1.0000", 100000)]
    finalize(biller, run_id)
    log(acme["ticket"], wt["Remote"], 720, work_date="2026-09-03")
    _, sep = run(biller, "2026-09", acme["org"])  # min(120, 120 + 600 - 660) = 60 carried
    assert block_text(sep) == "Retainer: 11 h included (incl. 1 h carried over), 11 h used"
    assert lines(sep) == [("agreement", "1.0000", 100000), ("time", "1.0000", 15000)]


def test_month_without_a_finalized_run_used_nothing(biller, acme, wt, log):
    agreement(biller, acme["org"], rollover="roll")
    log(acme["ticket"], wt["Remote"], 600, work_date="2026-07-02")
    run(biller, "2026-07", acme["org"])  # left as a draft: its draw-down does not count
    _, aug = run(biller, "2026-08", acme["org"])
    assert block_text(aug) == "Retainer: 20 h included (incl. 10 h carried over), 0 h used"


def test_mid_month_start_carries_the_prorated_minutes(biller, acme):
    agreement(biller, acme["org"], rollover="roll", start_date="2026-07-15")
    run_id, jul = run(biller, "2026-07", acme["org"])  # 600 x 17/31 -> 315 min
    assert block_text(jul) == "Retainer: 5.25 h included, 0 h used"
    finalize(biller, run_id)
    _, aug = run(biller, "2026-08", acme["org"])
    assert block_text(aug) == "Retainer: 15.25 h included (incl. 5.25 h carried over), 0 h used"


def test_voiding_month_one_changes_month_two_carry_in(biller, acme, wt, log, owner):
    agreement(biller, acme["org"], rollover="roll")
    e = log(acme["ticket"], wt["Remote"], 600, work_date="2026-07-02")
    run_id, jul = run(biller, "2026-07", acme["org"])
    finalize(biller, run_id)
    aug_run, aug = run(biller, "2026-08", acme["org"])
    assert block_text(aug) == "Retainer: 10 h included, 0 h used"  # July used it all
    assert biller.post(f"/api/v1/billing-runs/{aug_run}/cancel").status_code == 200
    r = biller.post(f"/api/v1/invoices/{jul['id']}/void", json={"reason": "Wrong client"})
    assert r.status_code == 200, r.text
    _, aug = run(biller, "2026-08", acme["org"])
    assert block_text(aug) == "Retainer: 20 h included (incl. 10 h carried over), 0 h used"
    # July's released hours are prior-month time: billed at the normal rate, as today
    assert lines(aug) == [("agreement", "1.0000", 100000), ("time", "10.0000", 150000)]
    assert entry(owner, e["id"]) == (0, aug["lines"][1]["id"])


def test_agreement_change_mid_period(biller, acme, wt, log, owner):
    blk = agreement(biller, acme["org"], end_date="2026-07-15")
    flat = agreement(
        biller,
        acme["org"],
        "flat",
        unit_price_cents=50000,
        all_inclusive=True,
        start_date="2026-07-16",
    )
    on_block = log(
        acme["ticket"], wt["Remote"], 120, work_date="2026-07-10", agreement_id=blk["id"]
    )
    loose = log(acme["ticket"], wt["Remote"], 60, work_date="2026-07-20", agreement_id=None)
    on_flat = log(
        acme["ticket"], wt["Remote"], 240, work_date="2026-07-20", agreement_id=flat["id"]
    )
    _, inv = run(biller, "2026-07", acme["org"])
    # block: 600 x 15/31 -> 285 min; credit 100,000 x 16/31 = 51,612.9 -> 51,613
    # flat: credit 50,000 x 15/31 = 24,193.5 -> 24,194; the flat-attached 4 h are never billed
    assert lines(inv) == [
        ("agreement", "1.0000", 100000),
        ("proration", "1.0000", -51613),
        ("agreement", "1.0000", 50000),
        ("proration", "1.0000", -24194),
    ]
    assert inv["total_cents"] == 100000 - 51613 + 50000 - 24194
    assert block_text(inv) == "Retainer: 4.75 h included, 3 h used"
    block_line = inv["lines"][0]["id"]
    assert entry(owner, on_block["id"]) == (120, block_line)
    assert entry(owner, loose["id"]) == (60, block_line)
    assert entry(owner, on_flat["id"]) == (0, None)
