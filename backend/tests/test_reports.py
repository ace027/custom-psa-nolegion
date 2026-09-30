import csv
import io
from datetime import timedelta

import pytest

from tests.conftest import biz_today
from tests.test_billing_runs import agreement, period, start_run
from tests.test_payments import final_invoice, pay


def rows(resp):
    assert resp.status_code == 200, resp.text
    return list(csv.reader(io.StringIO(resp.text)))


def month_of(d):
    return d.replace(day=1)


# ---- revenue ----
def test_revenue_by_client_month_and_kind(admin, biller, make_org, company):
    a, b = make_org("Alpha Co")["id"], make_org("Beta Co")["id"]
    today = biz_today()
    final_invoice(biller, a, 10000, invoice_date=today)
    final_invoice(biller, a, 5000, invoice_date=today)
    final_invoice(biller, b, 2500, invoice_date=today)
    d = biller.get("/api/reports/revenue").json()
    assert [c["organization_name"] for c in d["clients"]] == ["Alpha Co", "Beta Co"]
    alpha = d["clients"][0]
    assert (alpha["invoices"], alpha["manual_cents"], alpha["total_cents"]) == (2, 15000, 15000)
    assert d["totals"]["total_cents"] == 17500 and d["totals"]["invoices"] == 3
    assert len(d["months"]) == 12 and d["months"][-1]["month"] == month_of(today).isoformat()
    assert d["months"][-1]["total_cents"] == 17500 and d["months"][0]["total_cents"] == 0


def test_revenue_excludes_drafts_voids_and_out_of_range(biller, make_org, company):
    org = make_org("Alpha Co")["id"]
    today = biz_today()
    keep = final_invoice(biller, org, 1000, invoice_date=today)
    gone = final_invoice(biller, org, 2000, invoice_date=today)
    biller.post(f"/api/invoices/{gone['id']}/void", json={"reason": "mistake"})
    biller.post("/api/invoices", json={"organization_id": org, "include_unbilled": False})
    old = final_invoice(biller, org, 4000, invoice_date=today - timedelta(days=800))
    d = biller.get("/api/reports/revenue").json()
    assert d["totals"]["total_cents"] == keep["total_cents"] == 1000
    wide = biller.get(
        "/api/reports/revenue", params={"from": (today - timedelta(days=2000)).isoformat()}
    )
    assert wide.status_code == 409  # more than 60 months is refused
    ok = biller.get(
        "/api/reports/revenue",
        params={"from": (today - timedelta(days=810)).isoformat(), "to": today.isoformat()},
    ).json()
    assert ok["totals"]["total_cents"] == 1000 + old["total_cents"]


def test_revenue_splits_by_line_kind_and_counts_tax(admin, biller, make_org, company):
    org = make_org("Alpha Co")["id"]
    biller.patch(f"/api/organizations/{org}/billing", json={"tax_rate_bp": 1000})
    biller.post(
        "/api/product-charges",
        json={
            "organization_id": org,
            "description": "Hub",
            "unit_price_cents": 2500,
            "taxable": True,
        },
    )
    inv = biller.post("/api/invoices", json={"organization_id": org}).json()
    biller.post(f"/api/invoices/{inv['id']}/finalize", json={})
    t = biller.get("/api/reports/revenue").json()["totals"]
    assert (t["product_cents"], t["tax_cents"], t["subtotal_cents"], t["total_cents"]) == (
        2500,
        250,
        2500,
        2750,
    )


def test_invalid_ranges_are_refused(biller):
    assert (
        biller.get(
            "/api/reports/revenue", params={"from": "2026-05-01", "to": "2026-01-01"}
        ).status_code
        == 409
    )
    assert biller.get("/api/reports/recurring", params={"months": 0}).status_code == 409
    assert biller.get("/api/reports/recurring", params={"months": 37}).status_code == 409


# ---- unbilled ----
def test_unbilled_time_and_charges_priced_at_current_rates(
    admin, biller, make_org_with_ticket, log, wt, company
):
    org, t = make_org_with_ticket("Alpha Co")
    log(t["id"], wt["Remote"], 60)  # 1h @ $150
    log(t["id"], wt["Onsite"], 30)  # 0.5h @ $200
    log(t["id"], wt["Remote"], 30, billable=False)
    biller.post(
        "/api/product-charges",
        json={"organization_id": org["id"], "description": "Hub", "unit_price_cents": 2500},
    )
    d = biller.get("/api/reports/unbilled").json()
    [r] = d["rows"]
    assert (r["time_entries"], r["billable_minutes"], r["time_value_cents"]) == (2, 90, 25000)
    assert (r["charges"], r["charges_cents"], r["total_cents"]) == (1, 2500, 27500)
    assert r["unpriced_minutes"] == 0 and d["totals"]["total_cents"] == 27500


def test_client_rate_override_and_missing_rate_are_handled(
    admin, biller, make_org_with_ticket, log, wt, company
):
    org, t = make_org_with_ticket("Alpha Co")
    biller.put(
        f"/api/organizations/{org['id']}/billing/rates/{wt['Remote']}", json={"rate_cents": 10000}
    )
    log(t["id"], wt["Remote"], 60)
    other = next(w for n, w in wt.items() if n not in ("Remote", "Onsite"))
    log(t["id"], other, 60)  # no rate anywhere
    [r] = biller.get("/api/reports/unbilled").json()["rows"]
    assert r["time_value_cents"] == 10000 and r["unpriced_minutes"] == 60


def test_invoiced_time_leaves_the_unbilled_report(
    admin, biller, make_org_with_ticket, log, wt, company
):
    org, t = make_org_with_ticket("Alpha Co")
    log(t["id"], wt["Remote"], 60)
    assert len(biller.get("/api/reports/unbilled").json()["rows"]) == 1
    inv = biller.post("/api/invoices", json={"organization_id": org["id"]}).json()
    assert biller.get("/api/reports/unbilled").json()["rows"] == []
    biller.post(f"/api/invoices/{inv['id']}/finalize", json={})
    assert biller.get("/api/reports/unbilled").json()["totals"]["total_cents"] == 0


# ---- recurring ----
def test_recurring_contracted_vs_invoiced(admin, biller, make_org, company):
    org = make_org("Alpha Co")["id"]
    agreement(biller, org)  # 25 x $12.00 = $300.00 from 2020
    agreement(biller, org, name="Flat", type="flat", unit_price_cents=50000, quantity=1)
    agreement(biller, org, name="Ended", end_date="2020-12-31")
    d = biller.get("/api/reports/recurring", params={"months": 3}).json()
    assert len(d["months"]) == 3
    last = d["months"][-1]
    assert (
        last["contracted_cents"],
        last["agreements"],
        last["clients"],
        last["invoiced_cents"],
    ) == (
        80000,
        2,
        1,
        0,
    )
    run = start_run(biller, period())
    biller.post(f"/api/billing-runs/{run['id']}/review")
    assert biller.post(f"/api/billing-runs/{run['id']}/finalize").status_code == 200
    last = biller.get("/api/reports/recurring", params={"months": 3}).json()["months"][-1]
    assert last["invoiced_cents"] == 80000


def test_agreement_starting_next_month_is_not_contracted_yet(biller, make_org):
    org = make_org("Alpha Co")["id"]
    nxt = (month_of(biz_today()) + timedelta(days=32)).replace(day=1)
    agreement(biller, org, start_date=nxt.isoformat())
    assert (
        biller.get("/api/reports/recurring", params={"months": 1}).json()["months"][0]["agreements"]
        == 0
    )


# ---- CSV ----
def test_invoices_csv_for_the_accountant(admin, biller, make_org, company):
    org = make_org("Alpha Co")["id"]
    today = biz_today()
    a = final_invoice(biller, org, 12345, invoice_date=today, terms=30)
    b = final_invoice(biller, org, 1000, invoice_date=today)
    pay(biller, org, 5000, [{"invoice_id": a["id"], "amount_cents": 5000}])
    biller.post(f"/api/invoices/{b['id']}/void", json={"reason": "wrong, sorry"})
    r = biller.get("/api/reports/invoices.csv")
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    header, first, second = rows(r)
    assert header[:3] == ["number", "client", "status"]
    row = dict(zip(header, first, strict=True))
    assert (row["number"], row["client"], row["status"]) == (a["number"], "Alpha Co", "final")
    assert (row["total"], row["paid"], row["balance"], row["payment_status"]) == (
        "123.45",
        "50.00",
        "73.45",
        "partial",
    )
    void = dict(zip(header, second, strict=True))
    assert (
        void["status"] == "void" and void["balance"] == "" and void["void_reason"] == "wrong, sorry"
    )


def test_csv_neutralises_spreadsheet_formulas(biller, make_org, company):
    org = make_org('=HYPERLINK("http://evil.example","x")')["id"]
    final_invoice(biller, org, 100, invoice_date=biz_today())
    _, first = rows(biller.get("/api/reports/invoices.csv"))
    assert first[1].startswith("'=")


def test_other_csvs_are_dollars_not_cents(admin, biller, make_org_with_ticket, log, wt, company):
    org, t = make_org_with_ticket("Alpha Co")
    log(t["id"], wt["Remote"], 60)
    final_invoice(biller, org["id"], 100050, invoice_date=biz_today())
    rev = rows(biller.get("/api/reports/revenue.csv"))
    assert rev[0][0] == "client" and rev[1][0] == "Alpha Co" and rev[1][-1] == "1000.50"
    un = rows(biller.get("/api/reports/unbilled.csv"))
    assert un[1][:4] == ["Alpha Co", "1", "1.00", "150.00"]
    rec = rows(biller.get("/api/reports/recurring.csv", params={"months": 2}))
    assert len(rec) == 3 and rec[0] == ["month", "contracted", "agreements", "clients", "invoiced"]


# ---- permissions, audit, isolation ----
ROLES = ["admin", "tech", "billing", "read_only"]
PATHS = [
    "/api/reports/revenue",
    "/api/reports/revenue.csv",
    "/api/reports/unbilled",
    "/api/reports/unbilled.csv",
    "/api/reports/recurring",
    "/api/reports/recurring.csv",
    "/api/reports/invoices.csv",
]


@pytest.mark.parametrize("role", ROLES)
def test_report_role_matrix(role, login):
    client = login(role)
    for path in PATHS:
        r = client.get(path)
        if role in ("admin", "billing"):
            assert r.status_code == 200, (role, path, r.status_code, r.text)
        else:
            assert r.status_code == 403, (role, path, r.status_code)


def test_unauthenticated_report_requests_get_401(anon):
    for path in PATHS:
        assert anon.get(path).status_code == 401, path


def test_csv_exports_are_audited_but_json_views_are_not(admin, biller, company):
    biller.get("/api/reports/revenue")
    assert admin.get("/api/audit", params={"action": "report.export"}).json()["total"] == 0
    biller.get("/api/reports/invoices.csv")
    biller.get("/api/reports/revenue.csv")
    items = admin.get("/api/audit", params={"action": "report.export"}).json()["items"]
    assert {i["detail"]["report"] for i in items} == {"invoices", "revenue"}
    assert all(i["actor_id"] == biller.user["id"] for i in items)
