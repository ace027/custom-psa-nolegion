"""Parity phase 2C: expenses, mileage, receipts, billing to clients, locks and payroll CSV."""

import csv
import io
from datetime import timedelta

import pytest
from sqlalchemy import text

from app.db import new_session, set_org_scope
from tests.conftest import biz_today
from tests.test_timekeeping import audit_actions

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32


def monday(back=0):
    d = biz_today() - timedelta(days=biz_today().weekday())
    return d - timedelta(weeks=back)


@pytest.fixture
def travel(admin):
    return next(
        c["id"] for c in admin.get("/api/expense-categories").json() if c["name"] == "Travel"
    )


@pytest.fixture
def tech(login):
    return login("tech")


@pytest.fixture
def rate(admin):
    assert admin.patch("/api/settings", json={"mileage_rate_cents": 67}).status_code == 200


def exp(c, **kw):
    body = {"description": "Dock", "amount_cents": 1000, **kw}
    return c.post("/api/expenses", json=body)


# ---- categories and settings ------------------------------------------------------------------
def test_categories_and_mileage_rate_setting(admin, tech):
    names = {c["name"] for c in admin.get("/api/expense-categories").json()}
    assert {"Travel", "Meals", "Parts and supplies"} <= names
    assert admin.post("/api/expense-categories", json={"name": "Tolls"}).status_code == 201
    assert admin.get("/api/settings").json()["mileage_rate_cents"] == 0
    assert admin.patch("/api/settings", json={"mileage_rate_cents": -1}).status_code == 422
    assert (
        admin.patch("/api/settings", json={"mileage_rate_cents": 70}).json()["mileage_rate_cents"]
        == 70
    )
    assert tech.patch("/api/settings", json={"mileage_rate_cents": 1}).status_code == 403


# ---- entering expenses ------------------------------------------------------------------------
def test_expense_basics_and_validation(admin, tech, travel, org_ctx):
    r = exp(tech, category_id=travel, reimbursable=True)
    assert r.status_code == 201, r.text
    e = r.json()
    assert e["user_id"] == tech.user["id"] and e["expense_date"] == biz_today().isoformat()
    assert (
        e["amount_cents"] == 1000
        and e["client_price_cents"] == 0
        and e["category_name"] == "Travel"
    )
    assert exp(tech).status_code == 409  # category required
    assert exp(tech, category_id=travel, amount_cents=0).status_code == 422
    assert exp(tech, category_id=travel, miles="3").status_code == 409  # miles only for mileage
    assert (
        exp(tech, category_id=travel, billable=True).status_code == 409
    )  # billable needs a client
    assert exp(tech, category_id=travel, markup_bp=500).status_code == 409  # markup needs billable
    assert exp(tech, category_id=travel, organization_id=999).status_code == 409
    assert exp(tech, category_id=travel, user_id=admin.user["id"]).status_code == 403
    assert (
        exp(admin, category_id=travel, user_id=tech.user["id"]).json()["user_id"] == tech.user["id"]
    )


def test_billable_expense_price_includes_markup(tech, travel, org_ctx):
    e = exp(
        tech,
        category_id=travel,
        amount_cents=12345,
        billable=True,
        markup_bp=1500,
        organization_id=org_ctx["org"],
    ).json()
    assert e["client_price_cents"] == 14197  # 12,345 + round(1,851.75)


def test_ticket_implies_client_and_must_match(admin, tech, travel, org_ctx, make_ticket, make_org):
    t = make_ticket()
    e = exp(tech, category_id=travel, ticket_id=t["id"]).json()
    assert e["organization_id"] == org_ctx["org"] and e["ticket_id"] == t["id"]
    other = make_org("Other")["id"]
    assert (
        exp(tech, category_id=travel, ticket_id=t["id"], organization_id=other).status_code == 409
    )


# ---- mileage ----------------------------------------------------------------------------------
def test_mileage_needs_the_rate_then_rounds_half_up(tech, admin, rate):
    def ok(miles):
        return tech.post(
            "/api/expenses", json={"kind": "mileage", "description": "Site visit", "miles": miles}
        )

    cases = {"37.5": 2513, "12.35": 827, "0.5": 34}
    for miles, cents in cases.items():
        r = ok(miles)
        assert r.status_code == 201, r.text
        assert r.json()["amount_cents"] == cents and r.json()["mileage_rate_cents"] == 67
    assert (
        tech.post(
            "/api/expenses",
            json={"kind": "mileage", "description": "x", "miles": "5", "amount_cents": 100},
        ).status_code
        == 409
    )
    assert (
        tech.post("/api/expenses", json={"kind": "mileage", "description": "x"}).status_code == 409
    )
    assert (
        tech.post(
            "/api/expenses", json={"kind": "mileage", "description": "x", "miles": "1.234"}
        ).status_code
        == 422
    )


def test_mileage_refused_until_rate_is_set(tech):
    r = tech.post("/api/expenses", json={"kind": "mileage", "description": "x", "miles": "5"})
    assert r.status_code == 409 and "mileage rate" in r.json()["detail"]


def test_changing_the_rate_does_not_rewrite_old_trips(tech, admin, rate):
    e = tech.post(
        "/api/expenses", json={"kind": "mileage", "description": "x", "miles": "10"}
    ).json()
    admin.patch("/api/settings", json={"mileage_rate_cents": 100})
    assert tech.get(f"/api/expenses/{e['id']}").json()["amount_cents"] == 670
    edited = tech.patch(f"/api/expenses/{e['id']}", json={"miles": "20"}).json()
    assert edited["amount_cents"] == 1340 and edited["mileage_rate_cents"] == 67  # old rate kept
    assert tech.patch(f"/api/expenses/{e['id']}", json={"amount_cents": 5}).status_code == 409


# ---- edit, void, permissions ------------------------------------------------------------------
def test_edit_void_and_who_may(admin, tech, travel, login, owner):
    e = exp(tech, category_id=travel).json()
    r = tech.patch(f"/api/expenses/{e['id']}", json={"amount_cents": 2500, "description": "Hub"})
    assert r.status_code == 200 and r.json()["amount_cents"] == 2500
    other = login("tech", "other@example.com")
    assert other.patch(f"/api/expenses/{e['id']}", json={"amount_cents": 1}).status_code == 403
    assert other.get(f"/api/expenses/{e['id']}").status_code == 403
    assert login("read_only").get(f"/api/expenses/{e['id']}").status_code == 403
    assert admin.get(f"/api/expenses/{e['id']}").status_code == 200
    assert tech.post(f"/api/expenses/{e['id']}/void").json()["voided_at"]
    assert tech.patch(f"/api/expenses/{e['id']}", json={"amount_cents": 1}).status_code == 409
    assert tech.post(f"/api/expenses/{e['id']}/void").status_code == 409
    assert tech.get("/api/expenses").json() == []
    assert len(tech.get("/api/expenses", params={"include_voided": True}).json()) == 1
    assert {"expense.create", "expense.update", "expense.void"} <= set(audit_actions(owner))
    assert tech.get("/api/expenses/99999").status_code == 404


def test_listing_scopes_and_filters(admin, tech, travel, org_ctx):
    exp(tech, category_id=travel)
    exp(tech, category_id=travel, organization_id=org_ctx["org"], expense_date="2020-01-01")
    assert len(tech.get("/api/expenses").json()) == 2
    assert len(tech.get("/api/expenses", params={"from": "2021-01-01"}).json()) == 1
    assert len(tech.get("/api/expenses", params={"organization_id": org_ctx["org"]}).json()) == 1
    assert admin.get("/api/expenses").json() == []
    assert len(admin.get("/api/expenses", params={"user_id": tech.user["id"]}).json()) == 2
    assert tech.get("/api/expenses", params={"user_id": admin.user["id"]}).status_code == 403


def test_clear_client_and_billable_off_drops_markup(tech, travel, org_ctx):
    e = exp(
        tech, category_id=travel, billable=True, markup_bp=1000, organization_id=org_ctx["org"]
    ).json()
    r = tech.patch(f"/api/expenses/{e['id']}", json={"billable": False})
    assert r.json()["billable"] is False and r.json()["markup_bp"] == 0
    r = tech.patch(f"/api/expenses/{e['id']}", json={"clear_client": True})
    assert r.json()["organization_id"] is None
    assert tech.patch(f"/api/expenses/{e['id']}", json={"billable": True}).status_code == 409


# ---- receipts ---------------------------------------------------------------------------------
def test_receipts_upload_download_and_limits(tech, admin, travel, login, tmp_path, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "attachments_dir", str(tmp_path))
    e = exp(tech, category_id=travel).json()
    up = lambda body, ctype="image/png", name="r.png", c=tech: c.post(  # noqa: E731
        f"/api/expenses/{e['id']}/receipts",
        params={"filename": name},
        content=body,
        headers={"Content-Type": ctype},
    )
    r = up(PNG)
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert r.json()["filename"] == "r.png" and r.json()["size_bytes"] == len(PNG)
    assert tech.get(f"/api/expenses/{e['id']}").json()["receipts"][0]["id"] == rid
    d = tech.get(f"/api/expense-receipts/{rid}/download")
    assert d.status_code == 200 and d.content == PNG
    assert (
        "attachment" in d.headers["content-disposition"]
        and d.headers["x-content-type-options"] == "nosniff"
    )
    assert admin.get(f"/api/expense-receipts/{rid}/download").status_code == 200
    assert (
        login("tech", "o@example.com").get(f"/api/expense-receipts/{rid}/download").status_code
        == 403
    )
    assert up(b"%PDF-1.4 x", "application/pdf", "a.pdf").status_code == 201
    assert up(b"not a png", "image/png").status_code == 409  # content must match the type
    assert up(b"GIF89a", "image/gif").status_code == 409
    assert up(b"", "image/png").status_code == 409
    assert up(b"\x89PNG\r\n\x1a\n" + b"0" * (10 * 1024 * 1024), "image/png").status_code == 409
    assert up(PNG, name="../../etc/passwd.png").json()["filename"] == "../../etc/passwd.png"
    assert tech.get("/api/expense-receipts/99999/download").status_code == 404
    tech.post(f"/api/expenses/{e['id']}/void")
    assert up(PNG).status_code == 409


# ---- timesheet lock and payroll CSV -----------------------------------------------------------
def test_submitted_week_locks_expenses(tech, travel, cat_internal=None):
    e = exp(tech, category_id=travel, expense_date=monday().isoformat()).json()
    assert (
        tech.post("/api/timesheet/submit", json={"week_start": monday().isoformat()}).status_code
        == 200
    )
    assert exp(tech, category_id=travel, expense_date=monday().isoformat()).status_code == 409
    assert tech.patch(f"/api/expenses/{e['id']}", json={"amount_cents": 1}).status_code == 409
    assert tech.post(f"/api/expenses/{e['id']}/void").status_code == 409
    assert exp(tech, category_id=travel, expense_date=monday(1).isoformat()).status_code == 201


def test_reimbursement_csv_is_cost_only_and_approved_only(admin, tech, travel, org_ctx, rate):
    start = monday().isoformat()
    exp(
        tech,
        category_id=travel,
        amount_cents=12345,
        description="=cmd",
        reimbursable=True,
        billable=True,
        markup_bp=1500,
        organization_id=org_ctx["org"],
        expense_date=start,
    )
    exp(tech, category_id=travel, amount_cents=999, reimbursable=False, expense_date=start)
    tech.post(
        "/api/expenses",
        json={
            "kind": "mileage",
            "description": "Trip",
            "miles": "10",
            "reimbursable": True,
            "expense_date": start,
        },
    )
    p = {"from": start, "to": (monday() + timedelta(days=6)).isoformat()}
    body = {"user_id": tech.user["id"], "week_start": start}
    assert admin.get("/api/timesheets/expenses.csv", params=p).text.count("\r\n") == 1
    tech.post("/api/timesheet/submit", json={"week_start": start})
    assert admin.get("/api/timesheets/expenses.csv", params=p).text.count("\r\n") == 1
    admin.post("/api/timesheet/approve", json=body)
    r = admin.get("/api/timesheets/expenses.csv", params=p)
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0][-1] == "Reimburse" and len(rows) == 3  # the non-reimbursable one is out
    by_cat = {x[3]: x for x in rows[1:]}
    assert by_cat["Travel"][6] == "123.45"  # cost, not the marked-up price
    assert by_cat["Travel"][4] == "'=cmd"  # formula neutralised
    assert by_cat["Mileage"][5] == "10.00" and by_cat["Mileage"][6] == "6.70"
    assert tech.get("/api/timesheets/expenses.csv", params=p).status_code == 403
    assert (
        admin.get(
            "/api/timesheets/expenses.csv", params={"from": "2026-02-02", "to": "2026-01-01"}
        ).status_code
        == 409
    )


def test_expense_only_week_can_be_submitted(tech, travel):
    exp(tech, category_id=travel, expense_date=monday().isoformat())
    assert (
        tech.post("/api/timesheet/submit", json={"week_start": monday().isoformat()}).status_code
        == 200
    )


# ---- billing ----------------------------------------------------------------------------------
def lines_of(c, invoice_id):
    return c.get(f"/api/invoices/{invoice_id}").json()["lines"]


@pytest.fixture
def taxed(admin, org_ctx):
    assert (
        admin.patch(
            f"/api/organizations/{org_ctx['org']}/billing", json={"tax_rate_bp": 825}
        ).status_code
        == 200
    )


def test_billable_expense_is_invoiced_at_marked_up_price_with_tax(
    tech, biller, travel, org_ctx, taxed, company
):
    exp(
        tech,
        category_id=travel,
        description="Dock",
        amount_cents=12345,
        taxable=True,
        billable=True,
        markup_bp=1500,
        organization_id=org_ctx["org"],
        reimbursable=True,
    )
    inv = biller.post("/api/invoices", json={"organization_id": org_ctx["org"]}).json()
    [line] = lines_of(biller, inv["id"])
    assert (
        line["kind"] == "product"
        and "Dock" in line["description"]
        and "Travel" in line["description"]
    )
    assert (line["quantity"], line["unit_price_cents"]) in (
        (1, 14197),
        ("1.0000", 14197),
        ("1", 14197),
    )
    assert (line["amount_cents"], line["tax_cents"]) == (14197, 1171)
    inv = biller.get(f"/api/invoices/{inv['id']}").json()
    assert (inv["subtotal_cents"], inv["tax_cents"], inv["total_cents"]) == (14197, 1171, 15368)
    # the person is still reimbursed the cost; the expense is now locked
    e = tech.get("/api/expenses").json()[0]
    assert e["invoiced"] and e["amount_cents"] == 12345
    assert tech.patch(f"/api/expenses/{e['id']}", json={"amount_cents": 1}).status_code == 409
    assert tech.post(f"/api/expenses/{e['id']}/void").status_code == 409
    # not pulled onto a second invoice
    inv2 = biller.post("/api/invoices", json={"organization_id": org_ctx["org"]}).json()
    assert lines_of(biller, inv2["id"]) == []


def test_mileage_billed_at_cost_untaxed(tech, biller, org_ctx, rate, taxed, company):
    tech.post(
        "/api/expenses",
        json={
            "kind": "mileage",
            "description": "Site visit",
            "miles": "37.5",
            "billable": True,
            "organization_id": org_ctx["org"],
        },
    )
    inv = biller.post("/api/invoices", json={"organization_id": org_ctx["org"]}).json()
    [line] = lines_of(biller, inv["id"])
    assert line["amount_cents"] == 2513 and line["tax_cents"] == 0
    assert (
        line["description"].startswith("Mileage: Site visit") and "37.50 mi" in line["description"]
    )


def test_deleting_a_draft_line_or_voiding_the_invoice_releases_the_expense(
    tech, biller, travel, org_ctx, company
):
    exp(tech, category_id=travel, billable=True, organization_id=org_ctx["org"])
    inv = biller.post("/api/invoices", json={"organization_id": org_ctx["org"]}).json()
    [line] = lines_of(biller, inv["id"])
    assert tech.get("/api/expenses").json()[0]["invoiced"]
    assert biller.delete(f"/api/invoice-lines/{line['id']}").status_code in (200, 204)
    assert not tech.get("/api/expenses").json()[0]["invoiced"]
    inv_b = biller.post(f"/api/invoices/{inv['id']}/add-unbilled").json()
    assert len(lines_of(biller, inv_b["id"])) == 1
    assert biller.post(f"/api/invoices/{inv['id']}/finalize", json={}).status_code == 200
    assert tech.get("/api/expenses").json()[0]["invoiced"]
    assert (
        biller.post(f"/api/invoices/{inv['id']}/void", json={"reason": "wrong"}).status_code == 200
    )
    assert not tech.get("/api/expenses").json()[0]["invoiced"]  # free to bill again
    inv3 = biller.post("/api/invoices", json={"organization_id": org_ctx["org"]}).json()
    assert len(lines_of(biller, inv3["id"])) == 1


def test_unapproved_expenses_are_still_billed_and_non_billable_never(
    tech, biller, travel, org_ctx, company
):
    exp(
        tech,
        category_id=travel,
        description="Billed",
        billable=True,
        organization_id=org_ctx["org"],
    )
    exp(
        tech,
        category_id=travel,
        description="Ours",
        reimbursable=True,
        organization_id=org_ctx["org"],
    )
    exp(tech, category_id=travel, description="Gone", billable=True, organization_id=org_ctx["org"])
    gone = next(x for x in tech.get("/api/expenses").json() if x["description"] == "Gone")
    tech.post(f"/api/expenses/{gone['id']}/void")
    inv = biller.post("/api/invoices", json={"organization_id": org_ctx["org"]}).json()
    assert [x["description"] for x in lines_of(biller, inv["id"])] == [
        f"Travel: Billed ({biz_today().isoformat()})"
    ]


def test_future_dated_expense_waits_for_its_date(tech, biller, travel, org_ctx, company):
    exp(
        tech,
        category_id=travel,
        billable=True,
        organization_id=org_ctx["org"],
        expense_date=(biz_today() + timedelta(days=30)).isoformat(),
    )
    inv = biller.post("/api/invoices", json={"organization_id": org_ctx["org"]}).json()
    assert lines_of(biller, inv["id"]) == []


def test_unbilled_report_counts_expenses_at_billed_price(tech, biller, travel, org_ctx):
    exp(
        tech,
        category_id=travel,
        amount_cents=12345,
        billable=True,
        markup_bp=1500,
        organization_id=org_ctx["org"],
    )
    r = biller.get("/api/reports/unbilled").json()
    [row] = r["rows"]
    assert (row["expenses"], row["expenses_cents"], row["total_cents"]) == (1, 14197, 14197)
    assert r["totals"]["expenses_cents"] == 14197
    csv_text = biller.get("/api/reports/unbilled.csv").text
    assert "expenses_value" in csv_text and "141.97" in csv_text


def test_billing_run_includes_expenses(tech, biller, travel, org_ctx, company):
    exp(tech, category_id=travel, billable=True, amount_cents=5000, organization_id=org_ctx["org"])
    period = biz_today().strftime("%Y-%m")
    run = biller.post("/api/billing-runs", json={"period": period})
    assert run.status_code == 201, run.text
    invs = biller.get("/api/invoices", params={"billing_run_id": run.json()["id"]}).json()
    assert sum(i["total_cents"] for i in invs["items"]) == 5000


# ---- database rules and row-level security ----------------------------------------------------
def test_database_refuses_inconsistent_expenses(owner, tech, travel, org_ctx):
    e = exp(tech, category_id=travel).json()
    for sql in (
        "UPDATE expenses SET billable = true WHERE id = :i",  # no client
        "UPDATE expenses SET amount_cents = 0 WHERE id = :i",
        "UPDATE expenses SET kind = 'mileage' WHERE id = :i",  # no miles/rate
        "UPDATE expenses SET markup_bp = -1 WHERE id = :i",
        "UPDATE expenses SET ticket_id = 1 WHERE id = :i",  # ticket without a client
    ):
        with pytest.raises(Exception, match="violates"):
            owner.execute(text(sql), {"i": e["id"]})


def test_expenses_are_scoped_by_row_level_security(tech, travel, org_ctx, make_org):
    other = make_org("Second")["id"]
    exp(tech, category_id=travel, organization_id=org_ctx["org"])
    exp(tech, category_id=travel, organization_id=other)
    with new_session() as db:
        assert db.execute(text("SELECT count(*) FROM expenses")).scalar_one() == 0
        set_org_scope(db, str(org_ctx["org"]))
        orgs = {r[0] for r in db.execute(text("SELECT organization_id FROM expenses"))}
        assert orgs == {org_ctx["org"]}
