"""Automation time (owner decision 2026-10-30): never invoiced, never drawn from a block, and
reported on its own in utilisation, outside utilisation % and labour cost. Exact cents.

Remote = 150.00/h untaxed (conftest `wt`). Automation entries go in through the API.
"""

import csv
import io

from sqlalchemy import text

from app import report_metrics as rm

JUL = "2026-07"
MAR_LO, MAR_HI = "2026-03-01", "2026-03-31"


def auto(admin, ticket, wt, minutes, work_date, **kw):
    r = admin.post(
        f"/api/v1/tickets/{ticket}/time",
        json={
            "work_type_id": wt,
            "minutes": minutes,
            "work_date": work_date,
            "entry_type": "automation",
            **kw,
        },
    )
    assert r.status_code == 201, r.text
    e = r.json()
    assert e["entry_type"] == "automation" and e["billable"] is False
    return e


def run(client, org_name):
    r = client.post("/api/v1/billing-runs", json={"period": JUL})
    assert r.status_code == 201, r.text
    inv = next((i for i in r.json()["invoices"] if i["organization_name"] == org_name), None)
    return None if inv is None else client.get(f"/api/v1/invoices/{inv['id']}").json()


def lines(inv):
    return [(ln["kind"], ln["quantity"], ln["amount_cents"]) for ln in inv["lines"]]


def linked(owner, ids):
    rows = owner.execute(
        text(
            "SELECT id, invoice_line_id, block_minutes_covered FROM time_entries WHERE id = ANY(:i)"
        ),
        {"i": list(ids)},
    ).all()
    return {r.id: (r.invoice_line_id, r.block_minutes_covered) for r in rows}


def test_billing_run_invoices_only_labour_minutes(
    admin, biller, make_org_with_ticket, wt, log, owner
):
    org, t = make_org_with_ticket("Acme")
    lab = log(t["id"], wt["Remote"], 120, work_date="2026-07-02")["id"]
    a = auto(admin, t["id"], wt["Remote"], 300, "2026-07-03")["id"]
    inv = run(biller, "Acme")
    assert lines(inv) == [("time", "2.0000", 30000)]  # 2 h x 150.00; the 5 h of automation is out
    assert inv["total_cents"] == 30000
    assert linked(owner, [lab, a])[a] == (None, 0)
    assert linked(owner, [lab, a])[lab][0] == inv["lines"][0]["id"]


def test_a_client_with_only_automation_time_gets_no_invoice(
    admin, biller, make_org_with_ticket, wt
):
    org, t = make_org_with_ticket("Auto Only")
    auto(admin, t["id"], wt["Remote"], 240, "2026-07-03")
    assert run(biller, "Auto Only") is None


def test_block_agreement_draws_down_only_labour(
    admin, biller, make_org_with_ticket, wt, log, owner
):
    org, t = make_org_with_ticket("Acme")
    r = biller.post(
        "/api/v1/agreements",
        json={
            "organization_id": org["id"],
            "name": "Retainer",
            "type": "block",
            "unit_price_cents": 100000,
            "block_minutes": 600,
            "start_date": "2026-01-01",
        },
    )
    assert r.status_code == 201, r.text
    lab = log(t["id"], wt["Remote"], 300, work_date="2026-07-01")["id"]
    a = auto(admin, t["id"], wt["Remote"], 400, "2026-07-02")["id"]
    inv = run(biller, "Acme")
    # 5 h of labour inside the 10 h block; the 400 automation minutes would have used it up
    assert lines(inv) == [("agreement", "1.0000", 100000)]
    assert inv["lines"][0]["description"] == "Retainer: 10 h included, 5 h used"
    got = linked(owner, [lab, a])
    assert got[a] == (None, 0)
    assert got[lab] == (inv["lines"][0]["id"], 300)


def test_tm_project_bills_only_labour(admin, biller, client_org, wt, log, owner):
    r = admin.post(
        "/api/v1/projects",
        json={
            "organization_id": client_org,
            "name": "Rollout",
            "billing_mode": "tm",
            "budget_cents": 100000,
        },
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert admin.post(f"/api/v1/projects/{pid}/approve").status_code == 200
    tid = admin.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Build"}).json()["ticket_id"]
    lab = log(tid, wt["Remote"], 240, work_date="2026-07-10")["id"]
    a = auto(admin, tid, wt["Remote"], 600, "2026-07-11")["id"]
    inv = run(biller, "Acme Corp")
    assert [ln["amount_cents"] for ln in inv["lines"]] == [60000]  # 4 h x 150.00
    assert inv["total_cents"] == 60000
    assert linked(owner, [a])[a] == (None, 0)
    assert linked(owner, [lab])[lab][0] == inv["lines"][0]["id"]
    b = biller.get(f"/api/v1/projects/{pid}/budget").json()
    assert (b["actual_minutes"], b["billable_minutes"]) == (240, 240)
    assert b["billed_cents"] == 60000


def _set_cost_rate(owner, user_id, cents):
    owner.execute(
        text("UPDATE users SET cost_rate_cents = :c WHERE id = :u"), dict(c=cents, u=user_id)
    )


def test_utilisation_and_profitability_keep_automation_separate(
    admin, biller, owner, make_org_with_ticket, wt, log
):
    org, t = make_org_with_ticket("Main Co")
    uid = admin.user["id"]
    _set_cost_rate(owner, uid, 9000)
    log(t["id"], wt["Remote"], 60, work_date="2026-03-03")
    log(t["id"], wt["Remote"], 30, work_date="2026-03-04", billable=False)
    auto(admin, t["id"], wt["Remote"], 200, "2026-03-05")
    auto(admin, t["id"], wt["Remote"], 45, "2026-03-06")
    voided = auto(admin, t["id"], wt["Remote"], 999, "2026-03-06")["id"]
    assert admin.post(f"/api/v1/time-entries/{voided}/void").status_code == 200
    params = {"from": MAR_LO, "to": MAR_HI}

    d = biller.get("/api/v1/reports/utilisation", params=params).json()
    row = next(r for r in d["rows"] if r["user_id"] == uid)
    assert row["automation_minutes"] == 200 + 45  # voided entry excluded
    assert (row["logged_minutes"], row["billable_minutes"]) == (90, 60)  # labour only
    assert row["utilisation_bp"] == rm.bp(90, row["capacity_minutes"])
    assert d["totals"]["automation_minutes"] == sum(r["automation_minutes"] for r in d["rows"])
    assert d["totals"]["logged_minutes"] == sum(r["logged_minutes"] for r in d["rows"])

    p = biller.get("/api/v1/reports/profitability", params=params).json()
    main = next(r for r in p["rows"] if r["organization_name"] == "Main Co")
    assert main["labour_cost_cents"] == 9000 + 4500  # 60 + 30 minutes at 90.00/h only
    assert main["minutes_without_cost_rate"] == 0

    resp = biller.get("/api/v1/reports/utilisation.csv", params=params)
    assert resp.status_code == 200
    table = list(csv.reader(io.StringIO(resp.text)))
    assert table[0][-1] == "automation_minutes"
    mine = next(r for r in table[1:] if r[0] == row["name"])
    assert mine[-1] == "245"
    assert table[-1][0] == "Total"


def test_a_tech_without_a_cost_rate_still_reports_automation_minutes(
    admin, biller, owner, make_org_with_ticket, wt
):
    org, t = make_org_with_ticket("Rateless Co")
    uid = admin.user["id"]
    _set_cost_rate(owner, uid, None)
    auto(admin, t["id"], wt["Remote"], 50, "2026-03-10")
    params = {"from": MAR_LO, "to": MAR_HI}
    d = biller.get("/api/v1/reports/utilisation", params=params).json()
    row = next(r for r in d["rows"] if r["user_id"] == uid)
    assert row["automation_minutes"] == 50 and row["logged_minutes"] == 0
    assert row["utilisation_bp"] in (0, None)  # unchanged: zero labour
    p = biller.get("/api/v1/reports/profitability", params=params).json()
    assert all(r["minutes_without_cost_rate"] == 0 for r in p["rows"])
    assert all(
        r["labour_cost_cents"] == 0 for r in p["rows"] if r["organization_name"] == "Rateless Co"
    )
