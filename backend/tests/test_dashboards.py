"""Role dashboards: the technician sees only their own numbers; managers get the KPI payload,
which must equal the corresponding report totals."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app import report_metrics as rm
from tests.conftest import biz_today
from tests.test_payments import final_invoice
from tests.test_report_metrics import add_ticket as _add_ticket
from tests.test_report_metrics import add_time, now_utc


@pytest.fixture
def utc_always_open(owner):
    owner.execute(
        text(
            "UPDATE settings SET timezone = 'UTC', business_days = '{0,1,2,3,4,5,6}', "
            "business_start_minute = 0, business_end_minute = 1440"
        )
    )


def add_ticket(owner, org, priority, created, assignee, status, **cols):
    sid = owner.execute(text("SELECT default_status_id(:s)"), {"s": status}).scalar_one()
    return _add_ticket(
        owner, org, priority, created, assignee, status=status, status_id=sid, **cols
    )


def add_appointment(owner, org, ticket, tech, starts, status="scheduled"):
    owner.execute(
        text(
            "INSERT INTO appointments (organization_id, ticket_id, tech_id, starts_at, ends_at,"
            " status, cancelled_at) VALUES (:o, :t, :u, :s, :e, :st,"
            " CAST(:c AS timestamptz))"
        ),
        dict(
            o=org,
            t=ticket,
            u=tech,
            s=starts,
            e=starts + timedelta(hours=1),
            st=status,
            c=starts if status == "cancelled" else None,
        ),
    )


@pytest.fixture
def two_techs(owner, login, make_org, utc_always_open):
    org = make_org("Alpha Co")["id"]
    mine = login("tech", "mine@example.com")
    other = login("tech", "other@example.com")
    at = now_utc()
    today = at.date()
    me, them = mine.user["id"], other.user["id"]
    cr = at - timedelta(hours=3)
    # mine: one breached, one at risk, one fine, one resolved (not open)
    breached = add_ticket(
        owner, org, "Normal", cr, me, "open",
        sla_first_response_due=at - timedelta(hours=1),
        sla_resolution_due=at - timedelta(minutes=30),
    )  # fmt: skip
    add_ticket(
        owner, org, "Normal", cr, me, "open",
        first_responded_at=cr, sla_resolution_due=at + timedelta(minutes=10),
    )  # fmt: skip
    add_ticket(
        owner, org, "Normal", cr, me, "open",
        first_responded_at=cr, sla_resolution_due=at + timedelta(days=30),
    )  # fmt: skip
    add_ticket(
        owner, org, "Normal", cr, me, "resolved",
        sla_first_response_due=at - timedelta(hours=1), resolved_at=at,
    )  # fmt: skip
    # the other tech: one breached ticket and lots of time that must not count for "mine"
    theirs = add_ticket(
        owner, org, "Normal", cr, them, "open",
        sla_first_response_due=at - timedelta(hours=1),
        sla_resolution_due=at - timedelta(minutes=30),
    )  # fmt: skip
    add_time(owner, org, breached, me, today, 60, billable=True)
    add_time(owner, org, breached, me, today, 30, billable=False)
    add_time(owner, org, breached, me, today, 45, billable=True, voided=True)
    add_time(owner, org, theirs, them, today, 300, billable=True)
    midnight = datetime(today.year, today.month, today.day, tzinfo=UTC)
    add_appointment(owner, org, breached, me, midnight + timedelta(minutes=30))
    add_appointment(owner, org, breached, me, midnight + timedelta(minutes=90), "cancelled")
    add_appointment(owner, org, breached, me, midnight - timedelta(days=1, hours=-2))  # yesterday
    add_appointment(owner, org, theirs, them, midnight + timedelta(minutes=30))
    return mine, other


def test_tech_sees_only_their_own_numbers(two_techs):
    mine, other = two_techs
    d = mine.get("/api/v1/dashboard/me").json()
    assert (d["open_tickets"], d["sla_breached"], d["sla_at_risk"]) == (3, 1, 1)
    assert d["appointments_today"] == 1
    w = d["week"]
    assert (w["logged_minutes"], w["billable_minutes"]) == (90, 60)
    assert w["capacity_minutes"] > 0
    assert w["utilisation_bp"] == rm.bp(90, w["capacity_minutes"])

    o = other.get("/api/v1/dashboard/me").json()
    assert (o["open_tickets"], o["sla_breached"], o["sla_at_risk"]) == (1, 1, 0)
    assert o["appointments_today"] == 1
    assert (o["week"]["logged_minutes"], o["week"]["billable_minutes"]) == (300, 300)


def test_dashboard_me_is_for_staff_with_ticket_read_only(anon, login):
    assert anon.get("/api/v1/dashboard/me").status_code == 401
    d = login("admin").get("/api/v1/dashboard/me").json()
    assert d["open_tickets"] == 0 and d["week"]["logged_minutes"] == 0


def test_manager_payload_equals_the_report_totals(biller, company, make_org, wt, log, make_ticket):
    a, b = make_org("Alpha Co")["id"], make_org("Beta Co")["id"]
    today = biz_today()
    final_invoice(biller, a, 5000, invoice_date=today, terms=30)
    final_invoice(biller, a, 10000, invoice_date=today - timedelta(days=45), terms=15)
    final_invoice(biller, b, 20000, invoice_date=today - timedelta(days=100), terms=15)
    t = make_ticket()
    log(t["id"], wt["Remote"], 60)  # unbilled time
    month_start = today.replace(day=1)

    dash = biller.get("/api/v1/reports/dashboard").json()
    prof = biller.get(
        "/api/v1/reports/profitability", params={"from": month_start, "to": today}
    ).json()["totals"]
    assert dash["revenue_mtd_cents"] == prof["revenue_cents"] >= 5000
    assert dash["margin_mtd_cents"] == prof["margin_cents"]
    assert dash["margin_mtd_bp"] == prof["margin_bp"]

    aging = biller.get("/api/v1/reports/aging").json()["totals"]
    assert dash["ar_total_cents"] == aging["total_open_cents"] == 35000
    assert dash["ar_buckets"] == {
        k: aging[k]
        for k in ("current_cents", "d1_30_cents", "d31_60_cents", "d61_90_cents", "d90_plus_cents")
    }
    assert (
        dash["unbilled_cents"]
        == biller.get("/api/v1/reports/unbilled").json()["totals"]["total_cents"]
        > 0
    )

    sla = biller.get(
        "/api/v1/reports/sla", params={"from": today - timedelta(days=29), "to": today}
    ).json()["totals"]
    assert dash["sla_30d"] == {
        "first_response_met_bp": sla["first_response"]["met_bp"],
        "resolution_met_bp": sla["resolution"]["met_bp"],
        "n": sla["n"],
    }
    assert dash["sla_30d"]["n"] == 1

    monday = today - timedelta(days=today.weekday() + 7)
    util = biller.get(
        "/api/v1/reports/utilisation", params={"from": monday, "to": monday + timedelta(days=6)}
    ).json()["totals"]
    assert dash["team_utilisation_last_week_bp"] == util["utilisation_bp"]
    assert set(dash) == {
        "revenue_mtd_cents", "margin_mtd_cents", "margin_mtd_bp", "ar_total_cents", "ar_buckets",
        "unbilled_cents", "sla_30d", "team_utilisation_last_week_bp",
    }  # fmt: skip


def test_manager_dashboard_is_empty_safe(biller):
    d = biller.get("/api/v1/reports/dashboard").json()
    assert d["revenue_mtd_cents"] == 0 and d["margin_mtd_bp"] is None
    assert d["sla_30d"] == {"first_response_met_bp": None, "resolution_met_bp": None, "n": 0}


@pytest.mark.parametrize("role", ["tech", "read_only"])
def test_manager_dashboard_is_refused_without_report_read(login, role):
    assert login(role).get("/api/v1/reports/dashboard").status_code == 403
