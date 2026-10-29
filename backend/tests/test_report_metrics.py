"""SLA, utilisation, aging and profitability metrics, and their reconciliation to the sources.

Data is arranged with owner SQL where exact timestamps matter; the reports are read through the
API as billing (report:read)."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import text

from app import report_metrics as rm
from tests.test_payments import final_invoice, pay


# ---- pure helpers ----
def test_percentile_is_nearest_rank():
    assert rm.percentile([], 50) is None
    assert rm.percentile([7], 90) == 7
    assert rm.percentile([10, 30, 90], 50) == 30  # ceil(1.5) = rank 2
    assert rm.percentile([10, 30, 90], 90) == 90  # ceil(2.7) = rank 3
    assert rm.percentile(list(range(1, 11)), 50) == 5  # ceil(5.0) = rank 5
    assert rm.percentile(list(range(1, 11)), 90) == 9


def test_basis_points_round_half_up_and_null_on_zero_denominator():
    assert rm.bp(1, 3) == 3333
    assert rm.bp(2, 3) == 6667
    assert rm.bp(1, 8) == 1250
    assert rm.bp(1, 16) == 625  # 625.0
    assert rm.bp(1, 32) == 313  # 312.5 rounds up
    assert rm.bp(5, 0) is None
    assert rm.bp(0, 0) is None
    assert rm.pct(8750) == "87.50%" and rm.pct(None) == "" and rm.pct(-1250) == "(12.50%)"


# ---- SLA ----
@pytest.fixture
def utc_always_open(owner):
    """UTC, open 24 hours every day: business minutes are plain elapsed minutes."""
    owner.execute(
        text(
            "UPDATE settings SET timezone = 'UTC', business_days = '{0,1,2,3,4,5,6}', "
            "business_start_minute = 0, business_end_minute = 1440"
        )
    )


def now_utc():
    return datetime.now(UTC).replace(microsecond=0)


def ids(owner, table):
    return {r.name: r.id for r in owner.execute(text(f"SELECT id, name FROM {table}"))}


def add_ticket(owner, org, priority, created, assignee=None, **cols):
    prio = ids(owner, "priorities")[priority]
    queue = owner.execute(text("SELECT id FROM queues ORDER BY id LIMIT 1")).scalar_one()
    fields = {
        "organization_id": org,
        "queue_id": queue,
        "priority_id": prio,
        "subject": "t",
        "created_at": created,
        "assignee_id": assignee,
        **cols,
    }
    names = ", ".join(fields)
    marks = ", ".join(f":{k}" for k in fields)
    return owner.execute(
        text(f"INSERT INTO tickets ({names}) VALUES ({marks}) RETURNING id"), fields
    ).scalar_one()


@pytest.fixture
def sla_data(owner, make_org, make_user, utc_always_open):
    a, b = make_org("Alpha Co")["id"], make_org("Beta Co")["id"]
    tech = make_user("tech", "sla-tech@example.com")["id"]
    at = now_utc()
    c = at - timedelta(days=2)
    m = lambda n: c + timedelta(minutes=n)  # noqa: E731
    # Urgent: met/met, breached/breached, unresponded past due, pending, no SLA
    add_ticket(
        owner, a, "Urgent", c, tech,
        sla_first_response_due=m(60), first_responded_at=m(30),
        sla_resolution_due=m(240), resolved_at=m(200),
    )  # fmt: skip
    add_ticket(
        owner, a, "Urgent", c, tech,
        sla_first_response_due=m(60), first_responded_at=m(90),
        sla_resolution_due=m(240), resolved_at=m(300), sla_paused_minutes=40,
    )  # fmt: skip
    add_ticket(
        owner, b, "Urgent", c, None,
        sla_first_response_due=at - timedelta(hours=1),
        sla_resolution_due=at - timedelta(hours=1),
    )  # fmt: skip
    add_ticket(
        owner, b, "Urgent", c, None,
        sla_first_response_due=at + timedelta(hours=1),
        sla_resolution_due=at + timedelta(hours=5),
    )  # fmt: skip
    add_ticket(owner, b, "Urgent", c, None, first_responded_at=m(10))
    # High: resolved_at null, closed_at used
    add_ticket(
        owner, a, "High", c, tech,
        sla_first_response_due=m(50), first_responded_at=m(20),
        sla_resolution_due=m(120), closed_at=m(100),
    )  # fmt: skip
    # Low: pause credit larger than the elapsed time floors the duration at 0
    add_ticket(
        owner, a, "Low", c, tech,
        sla_resolution_due=m(500), resolved_at=m(30), sla_paused_minutes=100,
    )  # fmt: skip
    # outside the range
    add_ticket(owner, a, "Urgent", c - timedelta(days=30), tech, first_responded_at=m(-1))
    return {"a": a, "b": b, "tech": tech}


def sla_params(group="priority"):
    today = datetime.now(UTC).date()
    return {
        "from": (today - timedelta(days=5)).isoformat(),
        "to": today.isoformat(),
        "group": group,
    }


def test_sla_classification_percentiles_and_totals(biller, sla_data):
    d = biller.get("/api/reports/sla", params=sla_params()).json()
    by = {r["label"]: r for r in d["rows"]}
    assert [r["label"] for r in d["rows"]] == ["Urgent", "High", "Low"]  # by priority rank
    u = by["Urgent"]
    assert u["n"] == 5
    fr = u["first_response"]
    assert (fr["met"], fr["breached"], fr["pending"], fr["no_sla"]) == (1, 2, 1, 1)
    assert fr["met_bp"] == 3333  # 1 of the 3 that had a verdict; pending and no_sla excluded
    assert (fr["p50_minutes"], fr["p90_minutes"]) == (30, 90)  # durations 10, 30, 90
    res = u["resolution"]
    assert (res["met"], res["breached"], res["pending"], res["no_sla"]) == (1, 2, 1, 1)
    # 200 elapsed, and 300 - 40 paused = 260
    assert (res["p50_minutes"], res["p90_minutes"]) == (200, 260)
    high = by["High"]
    assert high["resolution"]["met"] == 1 and high["resolution"]["p50_minutes"] == 100
    assert high["first_response"]["met_bp"] == 10000
    assert by["Low"]["resolution"]["p50_minutes"] == 0  # floored at 0
    assert by["Low"]["first_response"]["no_sla"] == 1
    assert (
        by["Low"]["first_response"]["met_bp"] is None
        and by["Low"]["first_response"]["p50_minutes"] is None
    )
    t = d["totals"]
    assert t["n"] == sum(r["n"] for r in d["rows"]) == 7
    for clock in ("first_response", "resolution"):
        for k in ("met", "breached", "pending", "no_sla"):
            assert t[clock][k] == sum(r[clock][k] for r in d["rows"])


def test_sla_groups_by_organization_and_assignee(biller, sla_data):
    d = biller.get("/api/reports/sla", params=sla_params("organization")).json()
    assert [(r["label"], r["n"]) for r in d["rows"]] == [("Alpha Co", 4), ("Beta Co", 3)]
    d = biller.get("/api/reports/sla", params=sla_params("assignee")).json()
    assert [(r["label"], r["n"]) for r in d["rows"]] == [("tech user", 4), ("Unassigned", 3)]
    assert d["rows"][-1]["key"] is None and d["totals"]["n"] == 7
    assert biller.get("/api/reports/sla", params={"group": "nope"}).status_code == 422


def test_sla_empty_range(biller, utc_always_open):
    d = biller.get("/api/reports/sla", params={"from": "2001-01-01", "to": "2001-01-31"}).json()
    assert d["rows"] == [] and d["totals"]["n"] == 0
    assert d["totals"]["first_response"]["met_bp"] is None
    assert d["totals"]["resolution"]["p90_minutes"] is None
    assert (
        biller.get(
            "/api/reports/sla", params={"from": "2026-05-02", "to": "2026-05-01"}
        ).status_code
        == 409
    )


# ---- utilisation ----
MON, SUN = date(2026, 3, 2), date(2026, 3, 8)


def add_time(owner, org, ticket, user, work_date, minutes, billable=True, voided=False):
    wt = owner.execute(text("SELECT id FROM work_types ORDER BY id LIMIT 1")).scalar_one()
    owner.execute(
        text(
            "INSERT INTO time_entries (ticket_id, organization_id, user_id, work_type_id, work_date,"
            " minutes_actual, minutes_billable, billable, voided_at) VALUES (:t, :o, :u, :w, :d,"
            " :m, :b, :bl, CASE WHEN :v THEN now() END)"
        ),
        dict(t=ticket, o=org, u=user, w=wt, d=work_date, m=minutes, b=minutes if billable else 0,
             bl=billable, v=voided),
    )  # fmt: skip


def add_internal(owner, user, work_date, minutes, voided=False):
    cat = owner.execute(text("SELECT id FROM time_categories ORDER BY id LIMIT 1")).scalar_one()
    owner.execute(
        text(
            "INSERT INTO internal_time_entries (user_id, category_id, work_date, minutes, voided_at)"
            " VALUES (:u, :c, :d, :m, CASE WHEN :v THEN now() END)"
        ),
        dict(u=user, c=cat, d=work_date, m=minutes, v=voided),
    )


@pytest.fixture
def util_data(owner, admin, make_org_with_ticket, make_user, utc_always_open):
    org, ticket = make_org_with_ticket("Alpha Co")
    tech = make_user("tech", "util-tech@example.com")["id"]
    for wd in range(5):  # Monday-Friday 09:00-17:00 = 480 minutes
        owner.execute(
            text(
                "INSERT INTO user_work_hours (user_id, weekday, start_minute, end_minute)"
                " VALUES (:u, :d, 540, 1020)"
            ),
            dict(u=tech, d=wd),
        )
    # Wednesday is a holiday; Thursday 12:00-15:00 is approved time off; Friday's is only pending
    owner.execute(text("INSERT INTO holidays (on_date, name) VALUES ('2026-03-04', 'Closed day')"))
    admin_id = admin.user["id"]
    for day, s, e, status in ((5, 12, 15, "approved"), (6, 0, 24, "pending")):
        owner.execute(
            text(
                "INSERT INTO user_time_off (user_id, starts_at, ends_at, status, requested_by,"
                " decided_by, decided_at) VALUES (:u, :s, :e, :st, :u, :by, now())"
            ),
            dict(
                u=tech,
                s=datetime(2026, 3, day, s, tzinfo=UTC),
                e=datetime(2026, 3, day, e, tzinfo=UTC) if e < 24 else datetime(2026, 3, day + 1, tzinfo=UTC),
                st=status,
                by=admin_id,
            ),
        )  # fmt: skip
    add_time(owner, org["id"], ticket["id"], tech, date(2026, 3, 2), 120)
    add_time(owner, org["id"], ticket["id"], tech, date(2026, 3, 3), 60, billable=False)
    add_time(owner, org["id"], ticket["id"], tech, date(2026, 3, 3), 500, voided=True)
    add_time(owner, org["id"], ticket["id"], tech, date(2026, 3, 9), 77)  # after the range
    add_internal(owner, tech, date(2026, 3, 5), 45)
    add_internal(owner, tech, date(2026, 3, 5), 30, voided=True)
    return {"tech": tech}


def test_utilisation_capacity_with_holiday_and_partial_time_off(biller, util_data):
    d = biller.get("/api/reports/utilisation", params={"from": str(MON), "to": str(SUN)}).json()
    row = next(r for r in d["rows"] if r["user_id"] == util_data["tech"])
    # 4 working days x 480 (Wednesday is a holiday) minus 180 minutes of approved time off
    assert row["capacity_minutes"] == 4 * 480 - 180 == 1740
    assert (row["logged_minutes"], row["billable_minutes"]) == (120 + 60 + 45, 120)
    assert row["utilisation_bp"] == rm.bp(225, 1740) == 1293
    assert row["billable_bp"] == rm.bp(120, 1740) == 690
    t = d["totals"]
    assert t["capacity_minutes"] == sum(r["capacity_minutes"] for r in d["rows"])
    assert t["utilisation_bp"] == rm.bp(t["logged_minutes"], t["capacity_minutes"])


def test_utilisation_reconciles_with_time_entries(biller, owner, util_data):
    for lo, hi in ((MON, SUN), (date(2026, 3, 1), date(2026, 3, 31))):
        d = biller.get("/api/reports/utilisation", params={"from": str(lo), "to": str(hi)}).json()
        expected = owner.execute(
            text(
                "SELECT (SELECT coalesce(sum(minutes_actual), 0) FROM time_entries"
                "  WHERE voided_at IS NULL AND work_date BETWEEN :lo AND :hi)"
                " + (SELECT coalesce(sum(minutes), 0) FROM internal_time_entries"
                "  WHERE voided_at IS NULL AND work_date BETWEEN :lo AND :hi)"
            ),
            dict(lo=lo, hi=hi),
        ).scalar_one()
        assert d["totals"]["logged_minutes"] == expected
    assert expected == 120 + 60 + 77 + 45  # the whole of March


def test_utilisation_empty_range_has_capacity_but_no_logged_time(biller, util_data):
    d = biller.get(
        "/api/reports/utilisation", params={"from": "2001-01-01", "to": "2001-01-07"}
    ).json()
    assert d["totals"]["logged_minutes"] == 0 and d["totals"]["utilisation_bp"] == 0
    # a range with no working days at all (Saturday only): zero capacity, null percentages
    sat = biller.get("/api/reports/utilisation", params={"from": "2026-03-07", "to": "2026-03-07"})
    t = sat.json()["totals"]
    row = next(r for r in sat.json()["rows"] if r["user_id"] == util_data["tech"])
    assert row["capacity_minutes"] == 0 and row["utilisation_bp"] is None
    # the admin has no work-hour rows, so works the (24/7) business hours: capacity 1,440
    assert t["capacity_minutes"] == 1440 == sum(r["capacity_minutes"] for r in sat.json()["rows"])


# ---- aging ----
def test_aging_total_equals_open_invoice_balances(biller, owner, make_org, company):
    a, b = make_org("Alpha Co")["id"], make_org("Beta Co")["id"]
    today = datetime.now(UTC).date()
    i1 = final_invoice(biller, a, 10000, invoice_date=today - timedelta(days=45), terms=15)
    final_invoice(biller, a, 5000, invoice_date=today, terms=30)
    i3 = final_invoice(biller, b, 20000, invoice_date=today - timedelta(days=100), terms=15)
    paid = final_invoice(biller, b, 3000, invoice_date=today)
    assert (
        pay(biller, b, 3000, [{"invoice_id": paid["id"], "amount_cents": 3000}]).status_code == 201
    )
    assert pay(biller, a, 4000, [{"invoice_id": i1["id"], "amount_cents": 4000}]).status_code == 201
    assert biller.post(
        f"/api/invoices/{i3['id']}/write-off", json={"amount_cents": 5000, "reason": "bad debt"}
    ).status_code in (200, 201)
    d = biller.get("/api/reports/aging").json()
    balance_sum = owner.execute(
        text(
            """SELECT coalesce(sum(bal), 0) FROM (
                 SELECT i.total_cents
                   - coalesce((SELECT sum(amount_cents) FROM payment_applications
                               WHERE invoice_id = i.id AND voided_at IS NULL), 0)
                   - coalesce((SELECT sum(amount_cents) FROM write_offs
                               WHERE invoice_id = i.id AND voided_at IS NULL), 0)
                   - coalesce((SELECT sum(amount_cents) FROM credit_memo_applications
                               WHERE invoice_id = i.id AND voided_at IS NULL), 0) AS bal
                 FROM invoices i WHERE i.status = 'final') x WHERE bal > 0"""
        )
    ).scalar_one()
    assert balance_sum == 6000 + 5000 + 15000 == d["totals"]["total_open_cents"]
    assert d["as_of"] and d["totals"]["organization_name"] == "Total"
    assert sum(r["total_open_cents"] for r in d["rows"]) == d["totals"]["total_open_cents"]
    t = d["totals"]  # due 30 days ago (1-30), in 30 days (current), 85 days ago (61-90)
    assert (t["current_cents"], t["d1_30_cents"], t["d61_90_cents"]) == (5000, 6000, 15000)


def test_aging_with_nothing_owed(biller):
    d = biller.get("/api/reports/aging").json()
    assert d["rows"] == [] and d["totals"]["total_open_cents"] == 0


# ---- profitability ----
LO, HI = date(2026, 3, 1), date(2026, 3, 31)


def add_user(make_user, email, rate, owner):
    u = make_user("tech", email)
    owner.execute(
        text("UPDATE users SET cost_rate_cents = :r WHERE id = :i"), dict(r=rate, i=u["id"])
    )
    return u["id"]


def add_expense(owner, user, org, d, cents, voided=False):
    owner.execute(
        text(
            "INSERT INTO expenses (user_id, expense_date, kind, category_id, description,"
            " amount_cents, organization_id, voided_at) VALUES (:u, :d, 'expense',"
            " (SELECT id FROM expense_categories LIMIT 1), 'x', :c, :o,"
            " CASE WHEN :v THEN now() END)"
        ),
        dict(u=user, d=d, c=cents, o=org, v=voided),
    )


def add_charge(owner, org, qty, product=None, charged_on=date(2026, 3, 15), voided=False):
    return owner.execute(
        text(
            "INSERT INTO product_charges (organization_id, product_id, description, quantity,"
            " unit_price_cents, taxable, charged_on, voided_at) VALUES (:o, :p, 'c', :q, 100,"
            " false, :d, CASE WHEN :v THEN now() END) RETURNING id"
        ),
        dict(o=org, p=product, q=qty, d=charged_on, v=voided),
    ).scalar_one()


def add_product(owner, name, cost):
    return owner.execute(
        text(
            "INSERT INTO products (name, unit_price_cents, cost_cents) VALUES (:n, 9999, :c) RETURNING id"
        ),
        dict(n=name, c=cost),
    ).scalar_one()


def add_item(owner, org, qty, cost, delivered_on=date(2026, 3, 12), charge=None):
    owner.execute(
        text(
            "INSERT INTO inventory_items (description, quantity, unit_cost_cents, status,"
            " organization_id, delivered_on, received_on, product_charge_id) VALUES ('item', :q,"
            " :c, 'delivered', :o, :d, :d, :ch)"
        ),
        dict(q=qty, c=cost, o=org, d=delivered_on, ch=charge),
    )


@pytest.fixture
def profit_data(admin, biller, owner, make_org_with_ticket, make_user, company):
    zero, zero_t = make_org_with_ticket("Zero Co")
    main, main_t = make_org_with_ticket("Main Co")
    u1 = add_user(make_user, "rate9000@example.com", 9000, owner)
    u2 = add_user(make_user, "rate100@example.com", 100, owner)
    u3 = add_user(make_user, "norate@example.com", None, owner)
    inv = final_invoice(biller, main["id"], 100000, invoice_date=date(2026, 3, 10))
    final_invoice(biller, main["id"], 7000, invoice_date=date(2026, 5, 10))  # out of range
    # labour: 50 min at $90/h = 7,500 c; three 1-minute entries at $1/h round per entry (3 x 2)
    add_time(owner, main["id"], main_t["id"], u1, date(2026, 3, 5), 50)
    add_time(owner, main["id"], main_t["id"], u1, date(2026, 3, 5), 600, voided=True)
    add_time(owner, main["id"], main_t["id"], u1, date(2026, 4, 5), 60)  # out of range
    for _ in range(3):
        add_time(owner, main["id"], main_t["id"], u2, date(2026, 3, 6), 1)
    add_time(owner, main["id"], main_t["id"], u3, date(2026, 3, 7), 30, billable=False)
    add_time(owner, zero["id"], zero_t["id"], u1, date(2026, 3, 8), 60)  # 9,000 c
    # goods: delivered stock; a costed product charge; charges without a known cost; a charge an
    # inventory item already covers (not counted twice); a voided charge
    add_item(owner, main["id"], 2, 5000)  # 10,000
    add_item(owner, main["id"], 1, 5000, delivered_on=date(2026, 4, 2))  # out of range
    costed = add_product(owner, "Switch", 3000)
    uncosted = add_product(owner, "Cable", None)
    add_charge(owner, main["id"], 3, costed)  # round(3 x 3,000) = 9,000
    add_charge(owner, main["id"], 1, None)  # no product: unknown cost
    add_charge(owner, main["id"], 1, uncosted)  # product without cost: unknown cost
    covered = add_charge(owner, main["id"], 1, costed)
    add_item(owner, main["id"], 1, 700, charge=covered)  # 700 via the item, not 3,000 again
    add_charge(owner, main["id"], 1, costed, voided=True)
    add_charge(owner, main["id"], 1, costed, charged_on=date(2026, 4, 20))
    # expenses
    add_expense(owner, u1, main["id"], date(2026, 3, 9), 2500)
    add_expense(owner, u1, main["id"], date(2026, 3, 9), 999, voided=True)
    add_expense(owner, u1, zero["id"], date(2026, 3, 9), 1000)
    return {"zero": zero["id"], "main": main["id"], "invoice": inv}


def test_profitability_costs_margin_and_data_gaps(biller, profit_data):
    d = biller.get("/api/reports/profitability", params={"from": str(LO), "to": str(HI)}).json()
    by = {r["organization_name"]: r for r in d["rows"]}
    main = by["Main Co"]
    assert main["revenue_cents"] == 100000
    assert main["labour_cost_cents"] == 7500 + 3 * 2  # per-entry rounding: 3 x 2, not round(5)
    assert main["goods_cost_cents"] == 10000 + 9000 + 700
    assert main["expense_cost_cents"] == 2500
    assert main["cost_cents"] == 7506 + 19700 + 2500 == 29706
    assert main["margin_cents"] == 70294 and main["margin_bp"] == 7029
    assert main["minutes_without_cost_rate"] == 30 and main["charges_without_cost"] == 2
    zero = by["Zero Co"]  # costs but no revenue: margin_bp must be null, not a division error
    assert (zero["revenue_cents"], zero["labour_cost_cents"], zero["expense_cost_cents"]) == (
        0, 9000, 1000,
    )  # fmt: skip
    assert zero["margin_cents"] == -10000 and zero["margin_bp"] is None
    assert [r["organization_name"] for r in d["rows"]] == ["Main Co", "Zero Co"]
    t = d["totals"]
    assert (t["revenue_cents"], t["cost_cents"], t["margin_cents"]) == (100000, 39706, 60294)
    assert t["margin_bp"] == 6029
    assert t["minutes_without_cost_rate"] == 30 and t["charges_without_cost"] == 2


def test_profitability_revenue_reconciles_with_the_revenue_report(biller, profit_data):
    for lo, hi in ((LO, HI), (date(2026, 1, 1), date(2026, 12, 31))):
        p = {"from": str(lo), "to": str(hi)}
        prof = biller.get("/api/reports/profitability", params=p).json()
        rev = biller.get("/api/reports/revenue", params=p).json()
        assert prof["totals"]["revenue_cents"] == rev["totals"]["subtotal_cents"]
        by = {c["organization_id"]: c["subtotal_cents"] for c in rev["clients"]}
        for r in prof["rows"]:
            assert r["revenue_cents"] == by.get(r["organization_id"], 0)


def test_profitability_empty_range(biller):
    d = biller.get(
        "/api/reports/profitability", params={"from": "2001-01-01", "to": "2001-01-31"}
    ).json()
    assert (
        d["rows"] == [] and d["totals"]["revenue_cents"] == 0 and d["totals"]["margin_bp"] is None
    )


def test_zero_revenue_client_with_no_cost_rate_user(biller, owner, make_org_with_ticket, make_user):
    org, ticket = make_org_with_ticket("Lonely Co")
    u = make_user("tech", "lonely@example.com")["id"]
    add_time(owner, org["id"], ticket["id"], u, date(2026, 3, 3), 45)
    d = biller.get("/api/reports/profitability", params={"from": str(LO), "to": str(HI)}).json()
    [r] = d["rows"]
    assert (r["revenue_cents"], r["cost_cents"], r["margin_cents"]) == (0, 0, 0)
    assert r["margin_bp"] is None and r["minutes_without_cost_rate"] == 45
