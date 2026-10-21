"""Project billing: fixed fee up front and capped T&M (docs/BILLING.md "Project billing").

Owner-approved money rules (PRF-002). Exact cents everywhere; Remote = 150.00/h untaxed,
Onsite = 200.00/h taxable (conftest `wt`).
"""

import pytest
from sqlalchemy import text

JUL, AUG, SEP = "2026-07", "2026-08", "2026-09"


# ---- helpers ----
def project(client, org, name="Rollout", approve=True, **billing):
    r = client.post("/api/projects", json={"organization_id": org, "name": name, **billing})
    assert r.status_code == 201, r.text
    p = r.json()
    if approve:
        r = client.post(f"/api/projects/{p['id']}/approve")
        assert r.status_code == 200, r.text
        p = r.json()
    return p


def tm(client, org, budget, **kw):
    return project(client, org, billing_mode="tm", budget_cents=budget, **kw)


def fixed(client, org, fee, **kw):
    return project(client, org, billing_mode="fixed_fee", fixed_fee_cents=fee, **kw)


def task_ticket(client, pid, title="Task"):
    r = client.post(f"/api/projects/{pid}/tasks", json={"title": title})
    assert r.status_code == 201, r.text
    return r.json()["ticket_id"]


def day(period, n):
    return f"{period}-{n:02d}"


def run(client, period, org_name="Acme Corp"):
    r = client.post("/api/billing-runs", json={"period": period})
    assert r.status_code == 201, r.text
    inv = next((i for i in r.json()["invoices"] if i["organization_name"] == org_name), None)
    if inv is None:
        return None
    return client.get(f"/api/invoices/{inv['id']}").json()


def lines(inv):
    return [
        (ln["kind"], ln["quantity"], ln["unit_price_cents"], ln["amount_cents"])
        for ln in inv["lines"]
    ]


def descriptions(inv):
    return [ln["description"] for ln in inv["lines"]]


def linked(owner, ids):
    """entry id -> (invoice_line_id, block_minutes_covered)"""
    rows = owner.execute(
        text(
            "SELECT id, invoice_line_id, block_minutes_covered FROM time_entries "
            "WHERE id = ANY(:ids)"
        ),
        {"ids": list(ids)},
    ).all()
    return {r.id: (r.invoice_line_id, r.block_minutes_covered) for r in rows}


def line_projects(owner, inv):
    rows = owner.execute(
        text("SELECT id, project_id FROM invoice_lines WHERE invoice_id = :i ORDER BY position"),
        {"i": inv["id"]},
    ).all()
    return [r.project_id for r in rows]


def budget(client, pid):
    return client.get(f"/api/projects/{pid}/budget").json()


def tax(client, org, bp):
    r = client.patch(f"/api/organizations/{org}/billing", json={"tax_rate_bp": bp})
    assert r.status_code == 200, r.text


@pytest.fixture
def ticket(admin, client_org):
    """A normal ticket of the client, outside any project."""
    r = admin.post("/api/tickets", json={"organization_id": client_org, "subject": "Printer"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---- T&M: the worked example ----
def test_worked_example_three_runs_bill_exactly_the_budget(
    admin, biller, client_org, wt, log, owner
):
    p = tm(admin, client_org, 100_000)
    a = task_ticket(admin, p["id"], "Design")
    e1 = log(a, wt["Remote"], 240, work_date=day(JUL, 10))["id"]

    inv1 = run(biller, JUL)
    assert lines(inv1) == [("time", "4.0000", 15000, 60000)]
    assert descriptions(inv1) == ["Ticket #10001: Design (Remote, hours)"]
    assert (inv1["subtotal_cents"], inv1["tax_cents"], inv1["total_cents"]) == (60000, 0, 60000)
    assert line_projects(owner, inv1) == [p["id"]]
    assert linked(owner, [e1]) == {e1: (inv1["lines"][0]["id"], 0)}
    assert (
        budget(biller, p["id"])["billed_cents"],
        budget(biller, p["id"])["remaining_cents"],
    ) == (
        60000,
        40000,
    )

    b = task_ticket(admin, p["id"], "Build")
    c = task_ticket(admin, p["id"], "Test")
    e2 = log(b, wt["Remote"], 120, work_date=day(AUG, 3))["id"]
    e3 = log(c, wt["Remote"], 120, work_date=day(AUG, 4))["id"]
    inv2 = run(biller, AUG)
    assert lines(inv2) == [("time", "2.0000", 15000, 30000), ("time", "1.0000", 10000, 10000)]
    assert descriptions(inv2) == [
        "Ticket #10002: Build (Remote, hours)",
        "Ticket #10003: Test (Remote, hours) (capped at the project budget)",
    ]
    assert inv2["total_cents"] == 40000
    assert line_projects(owner, inv2) == [p["id"], p["id"]]
    assert linked(owner, [e2, e3]) == {
        e2: (inv2["lines"][0]["id"], 0),
        e3: (inv2["lines"][1]["id"], 0),
    }
    assert budget(biller, p["id"])["remaining_cents"] == 0

    d = task_ticket(admin, p["id"], "Fix")
    e4 = log(d, wt["Remote"], 180, work_date=day(SEP, 1))["id"]
    inv3 = run(biller, SEP)
    assert inv3["status"] == "draft"
    assert lines(inv3) == [("project", "3.0000", 0, 0)]
    assert descriptions(inv3) == ["Project: Rollout: 3 h over budget, not billed"]
    assert (inv3["subtotal_cents"], inv3["tax_cents"], inv3["total_cents"]) == (0, 0, 0)
    assert line_projects(owner, inv3) == [p["id"]]
    assert linked(owner, [e4]) == {e4: (inv3["lines"][0]["id"], 0)}

    got = budget(biller, p["id"])
    assert (got["billed_cents"], got["remaining_cents"]) == (100_000, 0)
    assert inv1["total_cents"] + inv2["total_cents"] + inv3["total_cents"] == 100_000
    audits = owner.execute(
        text(
            "SELECT detail FROM audit_log WHERE action = 'project.run_billed' "
            "AND entity_id = :p ORDER BY id"
        ),
        {"p": p["id"]},
    ).all()
    assert [a.detail["billed_cents"] for a in audits] == [60000, 40000, 0]


def test_budget_lowered_below_billed_puts_new_time_over_budget(
    admin, biller, client_org, wt, log, owner
):
    p = tm(admin, client_org, 100_000)
    t = task_ticket(admin, p["id"])
    log(t, wt["Remote"], 240, work_date=day(JUL, 2))
    assert run(biller, JUL)["total_cents"] == 60000
    r = admin.patch(f"/api/projects/{p['id']}", json={"budget_cents": 50_000})
    assert r.status_code == 200, r.text
    assert budget(biller, p["id"])["remaining_cents"] == 0

    e1 = log(t, wt["Remote"], 60, work_date=day(AUG, 2))["id"]
    e2 = log(t, wt["Onsite"], 30, work_date=day(AUG, 3))["id"]
    inv = run(biller, AUG)
    assert lines(inv) == [("project", "1.5000", 0, 0)]
    assert descriptions(inv) == ["Project: Rollout: 1.5 h over budget, not billed"]
    assert inv["total_cents"] == 0
    only = inv["lines"][0]["id"]
    assert linked(owner, [e1, e2]) == {e1: (only, 0), e2: (only, 0)}
    assert budget(biller, p["id"])["billed_cents"] == 60000


def test_capped_line_is_taxed_on_the_capped_amount(admin, biller, client_org, wt, log, owner):
    tax(biller, client_org, 825)
    p = tm(admin, client_org, 30_000)
    t = task_ticket(admin, p["id"], "Cabling")
    e = log(t, wt["Onsite"], 120, work_date=day(JUL, 5))["id"]  # 400.00 at full price
    inv = run(biller, JUL)
    ln = inv["lines"][0]
    assert lines(inv) == [("time", "1.0000", 30000, 30000)]
    assert (
        ln["description"] == "Ticket #10001: Cabling (Onsite, hours) (capped at the project budget)"
    )
    assert (ln["tax_rate_bp"], ln["tax_cents"]) == (825, 2475)  # 30000 x 8.25% = 2475.0
    assert (inv["subtotal_cents"], inv["tax_cents"], inv["total_cents"]) == (30000, 2475, 32475)
    assert linked(owner, [e]) == {e: (ln["id"], 0)}
    assert budget(biller, p["id"])["billed_cents"] == 30000  # the cap is pre-tax


def test_groups_bill_in_ticket_then_work_type_order(admin, biller, client_org, wt, log, owner):
    tax(biller, client_org, 1000)
    p = tm(admin, client_org, 50_000)
    t = task_ticket(admin, p["id"], "Move")
    # Remote (lower work type id) is priced first: 150.00, then Onsite 400.00 is capped at 350.00
    on = log(t, wt["Onsite"], 120, work_date=day(JUL, 1))["id"]
    rem = log(t, wt["Remote"], 60, work_date=day(JUL, 2))["id"]
    inv = run(biller, JUL)
    assert wt["Remote"] < wt["Onsite"]
    assert lines(inv) == [("time", "1.0000", 15000, 15000), ("time", "1.0000", 35000, 35000)]
    assert [ln["tax_cents"] for ln in inv["lines"]] == [0, 3500]
    assert inv["total_cents"] == 53500
    assert linked(owner, [rem, on]) == {
        rem: (inv["lines"][0]["id"], 0),
        on: (inv["lines"][1]["id"], 0),
    }


def test_work_type_without_rate_is_left_unbilled_with_warning(
    admin, biller, client_org, wt, log, owner
):
    p = tm(admin, client_org, 100_000)
    t = task_ticket(admin, p["id"])
    billed = log(t, wt["Remote"], 60, work_date=day(JUL, 1))["id"]
    left = log(t, wt["After hours"], 60, work_date=day(JUL, 2))["id"]
    inv = run(biller, JUL)
    assert lines(inv) == [("time", "1.0000", 15000, 15000)]
    assert inv["warnings"] == [
        "Project Rollout: No hourly rate for work type 'After hours': 1 time entry (60 min) "
        "left unbilled"
    ]
    assert linked(owner, [billed, left]) == {billed: (inv["lines"][0]["id"], 0), left: (None, 0)}
    assert budget(biller, p["id"])["remaining_cents"] == 85000


# ---- states that bill nothing ----
def test_draft_and_cancelled_before_approval_bill_nothing(
    admin, biller, client_org, wt, log, owner, ticket
):
    draft = fixed(admin, client_org, 500_000, name="Draft", approve=False)
    gone = tm(admin, client_org, 100_000, name="Gone", approve=False)
    e1 = log(task_ticket(admin, draft["id"]), wt["Remote"], 60, work_date=day(JUL, 1))["id"]
    e2 = log(task_ticket(admin, gone["id"]), wt["Remote"], 60, work_date=day(JUL, 1))["id"]
    assert (
        admin.post(f"/api/projects/{gone['id']}/status", json={"status": "cancelled"}).status_code
        == 200
    )

    # with nothing else to bill the client is not on the run at all
    assert run(biller, JUL) is None

    normal = log(ticket, wt["Remote"], 60, work_date=day(AUG, 1))["id"]
    inv = run(biller, AUG)
    assert lines(inv) == [("time", "1.0000", 15000, 15000)]
    assert line_projects(owner, inv) == [None]
    assert linked(owner, [e1, e2, normal]) == {
        e1: (None, 0),
        e2: (None, 0),
        normal: (inv["lines"][0]["id"], 0),
    }
    r = biller.post(f"/api/projects/{draft['id']}/bill-fixed-fee")
    assert (
        r.status_code == 409 and r.json()["detail"] == "Approve the project before billing its fee"
    )
    assert biller.get(f"/api/projects/{draft['id']}").json()["fixed_fee_billed"] is False


def test_cancelled_after_approval_still_bills_its_time(admin, biller, client_org, wt, log, owner):
    p = tm(admin, client_org, 100_000)
    e = log(task_ticket(admin, p["id"]), wt["Remote"], 90, work_date=day(JUL, 1))["id"]
    assert (
        admin.post(f"/api/projects/{p['id']}/status", json={"status": "cancelled"}).status_code
        == 200
    )
    inv = run(biller, JUL)
    assert lines(inv) == [("time", "1.5000", 15000, 22500)]
    assert linked(owner, [e]) == {e: (inv["lines"][0]["id"], 0)}


# ---- fixed fee ----
def test_fixed_fee_bills_once_on_the_next_run_and_covers_time(
    admin, biller, client_org, wt, log, owner
):
    tax(biller, client_org, 825)
    p = fixed(admin, client_org, 500_000, taxable=True)
    t = task_ticket(admin, p["id"])
    e1 = log(t, wt["Remote"], 120, work_date=day(JUL, 7))["id"]
    e2 = log(t, wt["Onsite"], 30, work_date=day(JUL, 8))["id"]

    inv = run(biller, JUL)
    assert lines(inv) == [("project", "1.0000", 500000, 500000), ("project", "2.5000", 0, 0)]
    assert descriptions(inv) == [
        "Project: Rollout (fixed fee)",
        "Project: Rollout: 2.5 h covered by the fixed fee",
    ]
    assert [(ln["tax_rate_bp"], ln["tax_cents"]) for ln in inv["lines"]] == [(825, 41250), (0, 0)]
    assert (inv["subtotal_cents"], inv["tax_cents"], inv["total_cents"]) == (500000, 41250, 541250)
    assert line_projects(owner, inv) == [p["id"], p["id"]]
    covered = inv["lines"][1]["id"]
    assert linked(owner, [e1, e2]) == {e1: (covered, 0), e2: (covered, 0)}
    fee_line = owner.execute(
        text("SELECT fixed_fee_invoice_line_id FROM projects WHERE id = :p"), {"p": p["id"]}
    ).scalar_one()
    assert fee_line == inv["lines"][0]["id"]
    assert biller.get(f"/api/projects/{p['id']}").json()["fixed_fee_billed"] is True

    r = biller.post(f"/api/projects/{p['id']}/bill-fixed-fee")
    assert r.status_code == 409 and r.json()["detail"] == "The fixed fee is already billed"

    e3 = log(t, wt["Remote"], 60, work_date=day(AUG, 1))["id"]
    inv2 = run(biller, AUG)
    assert lines(inv2) == [("project", "1.0000", 0, 0)]
    assert descriptions(inv2) == ["Project: Rollout: 1 h covered by the fixed fee"]
    assert inv2["total_cents"] == 0
    assert linked(owner, [e3]) == {e3: (inv2["lines"][0]["id"], 0)}
    assert budget(biller, p["id"])["billed_cents"] == 500000


def test_untaxed_fee_and_no_time_gives_one_line(admin, biller, client_org, owner):
    tax(biller, client_org, 825)
    fixed(admin, client_org, 123_456)  # taxable defaults to false, like agreements
    inv = run(biller, JUL)
    assert lines(inv) == [("project", "1.0000", 123456, 123456)]
    assert (inv["tax_cents"], inv["total_cents"]) == (0, 123456)


def test_bill_fixed_fee_now_makes_a_one_off_draft(admin, biller, client_org, wt, log, owner, login):
    tax(biller, client_org, 825)
    p = fixed(admin, client_org, 250_000, taxable=True)
    assert (
        login("tech", "t@example.com").post(f"/api/projects/{p['id']}/bill-fixed-fee").status_code
        == 403
    )

    r = biller.post(f"/api/projects/{p['id']}/bill-fixed-fee")
    assert r.status_code == 201, r.text
    out = r.json()
    assert (out["status"], out["billing_run_id"], out["memo"]) == (
        "draft",
        None,
        "Project: Rollout (fixed fee)",
    )
    assert (out["subtotal_cents"], out["tax_cents"], out["total_cents"]) == (250000, 20625, 270625)
    inv = biller.get(f"/api/invoices/{out['id']}").json()
    assert lines(inv) == [("project", "1.0000", 250000, 250000)]
    assert descriptions(inv) == ["Project: Rollout (fixed fee)"]
    assert line_projects(owner, inv) == [p["id"]]
    audit = owner.execute(
        text("SELECT detail FROM audit_log WHERE action = 'project.fee_billed' AND entity_id = :p"),
        {"p": p["id"]},
    ).one()
    assert audit.detail["invoice_id"] == out["id"] and audit.detail["amount_cents"] == 250000

    again = biller.post(f"/api/projects/{p['id']}/bill-fixed-fee")
    assert again.status_code == 409 and again.json()["detail"] == "The fixed fee is already billed"

    # the run then only covers the time
    e = log(task_ticket(admin, p["id"]), wt["Remote"], 60, work_date=day(JUL, 3))["id"]
    run_inv = run(biller, JUL)
    assert lines(run_inv) == [("project", "1.0000", 0, 0)]
    assert linked(owner, [e]) == {e: (run_inv["lines"][0]["id"], 0)}


def test_bill_fixed_fee_errors(admin, biller, client_org):
    p = tm(admin, client_org, 10_000)
    r = biller.post(f"/api/projects/{p['id']}/bill-fixed-fee")
    assert (
        r.status_code == 409 and r.json()["detail"] == "Only a fixed-fee project has a fee to bill"
    )
    assert biller.post("/api/projects/9999/bill-fixed-fee").status_code == 404


def test_voiding_the_fee_invoice_releases_fee_and_time_and_rerun_bills_again(
    admin, biller, client_org, wt, log, owner
):
    p = fixed(admin, client_org, 500_000)
    e = log(task_ticket(admin, p["id"]), wt["Remote"], 60, work_date=day(JUL, 3))["id"]
    inv = run(biller, JUL)
    assert lines(inv) == [("project", "1.0000", 500000, 500000), ("project", "1.0000", 0, 0)]

    r = biller.post(f"/api/invoices/{inv['id']}/void", json={})
    assert r.status_code == 200, r.text
    assert biller.get(f"/api/projects/{p['id']}").json()["fixed_fee_billed"] is False
    assert linked(owner, [e]) == {e: (None, 0)}
    assert budget(biller, p["id"])["billed_cents"] == 0

    assert biller.post(f"/api/billing-runs/{inv['billing_run_id']}/cancel").status_code == 200
    again = run(biller, JUL)
    assert again["id"] != inv["id"]
    assert lines(again) == [("project", "1.0000", 500000, 500000), ("project", "1.0000", 0, 0)]
    assert again["total_cents"] == 500000
    assert linked(owner, [e]) == {e: (again["lines"][1]["id"], 0)}
    assert biller.get(f"/api/projects/{p['id']}").json()["fixed_fee_billed"] is True


def test_voiding_or_deleting_the_one_off_fee_lets_it_bill_again(admin, biller, client_org, company):
    p = fixed(admin, client_org, 70_000)
    first = biller.post(f"/api/projects/{p['id']}/bill-fixed-fee").json()
    assert biller.post(f"/api/invoices/{first['id']}/void", json={}).status_code == 200
    assert biller.get(f"/api/projects/{p['id']}").json()["fixed_fee_billed"] is False

    second = biller.post(f"/api/projects/{p['id']}/bill-fixed-fee")
    assert second.status_code == 201 and second.json()["total_cents"] == 70000
    line = biller.get(f"/api/invoices/{second.json()['id']}").json()["lines"][0]
    assert biller.delete(f"/api/invoice-lines/{line['id']}").status_code == 204
    assert biller.get(f"/api/projects/{p['id']}").json()["fixed_fee_billed"] is False
    assert biller.post(f"/api/projects/{p['id']}/bill-fixed-fee").status_code == 201


def test_voiding_a_tm_invoice_restores_the_budget(admin, biller, client_org, wt, log, owner):
    p = tm(admin, client_org, 20_000)
    t = task_ticket(admin, p["id"])
    e = log(t, wt["Remote"], 120, work_date=day(JUL, 3))["id"]  # 300.00 -> capped at 200.00
    inv = run(biller, JUL)
    assert lines(inv) == [("time", "1.0000", 20000, 20000)]
    assert biller.post(f"/api/invoices/{inv['id']}/void", json={}).status_code == 200
    assert linked(owner, [e]) == {e: (None, 0)}
    assert budget(biller, p["id"])["remaining_cents"] == 20000
    assert biller.post(f"/api/billing-runs/{inv['billing_run_id']}/cancel").status_code == 200
    again = run(biller, JUL)
    assert lines(again) == [("time", "1.0000", 20000, 20000)]
    assert linked(owner, [e]) == {e: (again["lines"][0]["id"], 0)}


# ---- interaction with normal billing ----
def test_project_time_never_draws_down_block_hours(
    admin, biller, client_org, wt, log, owner, ticket
):
    r = biller.post(
        "/api/agreements",
        json={
            "organization_id": client_org,
            "name": "Retainer",
            "type": "block",
            "unit_price_cents": 100000,
            "block_minutes": 600,
            "start_date": "2026-01-01",
        },
    )
    assert r.status_code == 201, r.text
    p = tm(admin, client_org, 100_000)
    pe = log(task_ticket(admin, p["id"], "Upgrade"), wt["Remote"], 120, work_date=day(JUL, 2))["id"]
    ne = log(ticket, wt["Remote"], 60, work_date=day(JUL, 3))["id"]
    inv = run(biller, JUL)
    assert lines(inv) == [("agreement", "1.0000", 100000, 100000), ("time", "2.0000", 15000, 30000)]
    assert descriptions(inv) == [
        "Retainer: 10 h included, 1 h used",
        "Ticket #10002: Upgrade (Remote, hours)",
    ]
    assert inv["total_cents"] == 130000
    assert line_projects(owner, inv) == [None, p["id"]]
    assert linked(owner, [pe, ne]) == {
        pe: (inv["lines"][1]["id"], 0),
        ne: (inv["lines"][0]["id"], 60),
    }


def test_expenses_and_charges_on_project_tickets_bill_normally_outside_the_cap(
    admin, biller, client_org, wt, log, owner
):
    p = tm(admin, client_org, 15_000)
    t = task_ticket(admin, p["id"])
    e = log(t, wt["Remote"], 60, work_date=day(JUL, 2))["id"]
    r = biller.post(
        "/api/product-charges",
        json={
            "organization_id": client_org,
            "ticket_id": t,
            "description": "Cable",
            "unit_price_cents": 900,
            "quantity": "2",
            "charged_on": day(JUL, 2),
        },
    )
    assert r.status_code == 201, r.text
    travel = next(
        c["id"] for c in admin.get("/api/expense-categories").json() if c["name"] == "Travel"
    )
    r = admin.post(
        "/api/expenses",
        json={
            "description": "Parking",
            "amount_cents": 1000,
            "category_id": travel,
            "billable": True,
            "ticket_id": t,
            "expense_date": day(JUL, 2),
        },
    )
    assert r.status_code == 201, r.text
    inv = run(biller, JUL)
    assert lines(inv) == [
        ("product", "2.0000", 900, 1800),
        ("product", "1.0000", 1000, 1000),
        ("time", "1.0000", 15000, 15000),
    ]
    assert line_projects(owner, inv) == [None, None, p["id"]]
    assert inv["total_cents"] == 17800
    assert linked(owner, [e]) == {e: (inv["lines"][2]["id"], 0)}
    got = budget(biller, p["id"])
    assert (got["billed_cents"], got["remaining_cents"]) == (15000, 0)


def test_one_off_invoice_never_pulls_project_time(
    admin, biller, client_org, wt, log, owner, ticket
):
    p = tm(admin, client_org, 100_000)
    pe = log(task_ticket(admin, p["id"]), wt["Remote"], 60)["id"]
    ne = log(ticket, wt["Remote"], 60)["id"]
    r = biller.post("/api/invoices", json={"organization_id": client_org, "include_unbilled": True})
    assert r.status_code == 201, r.text
    inv = biller.get(f"/api/invoices/{r.json()['id']}").json()
    assert lines(inv) == [("time", "1.0000", 15000, 15000)]
    assert line_projects(owner, inv) == [None]
    assert linked(owner, [pe, ne]) == {pe: (None, 0), ne: (inv["lines"][0]["id"], 0)}
    r = biller.post(f"/api/invoices/{inv['id']}/add-unbilled")
    assert r.status_code == 200, r.text
    assert linked(owner, [pe]) == {pe: (None, 0)}


# ---- serialization and the revenue report ----
def test_project_lines_serialize_and_count_in_the_revenue_report(
    admin, biller, client_org, wt, log, ticket
):
    fixed(admin, client_org, 123_456, name="Fee")
    p = tm(admin, client_org, 100_000, name="Hours")
    log(task_ticket(admin, p["id"]), wt["Remote"], 60, work_date=day(JUL, 2))
    log(ticket, wt["Remote"], 30, work_date=day(JUL, 3))

    inv = run(biller, JUL)
    r = biller.get(f"/api/invoices/{inv['id']}")
    assert r.status_code == 200, r.text
    assert sorted(lines(r.json())) == [
        ("project", "1.0000", 123456, 123456),
        ("time", "0.5000", 15000, 7500),
        ("time", "1.0000", 15000, 15000),
    ]
    assert inv["total_cents"] == 145956

    run_id = inv["billing_run_id"]
    assert biller.post(f"/api/billing-runs/{run_id}/review").status_code == 200
    assert biller.post(f"/api/billing-runs/{run_id}/finalize").status_code == 200
    r = admin.get("/api/reports/revenue", params={"from": "2026-01-01", "to": "2026-12-31"})
    assert r.status_code == 200, r.text
    row = r.json()["clients"][0]
    assert (row["project_cents"], row["time_cents"]) == (123456, 22500)
    assert (row["subtotal_cents"], row["total_cents"]) == (145956, 145956)
    assert r.json()["totals"]["project_cents"] == 123456
