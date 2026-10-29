"""Role dashboards: the technician's own numbers and the manager KPI payload.

Everything here reuses app/report_metrics.py and app/reports.py so the dashboard figures equal the
report totals for the same range. Dates are business time zone dates.
"""

from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from app import report_metrics as metrics
from app import reports
from app import repositories as repo
from app.billing import today
from app.deps import Ctx
from app.models import Appointment, Ticket
from app.sla import sla_state
from app.ticket_services import calendar, now


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def me(ctx: Ctx) -> dict:
    """The calling user's own open tickets, SLA state, appointments today and week-to-date time."""
    user = ctx.user
    cal = calendar(ctx)
    settings = repo.get_settings_row(ctx.db)
    at = now()
    day = at.astimezone(cal.tz).date()

    stmt = ctx.scope.apply(
        select(Ticket).where(Ticket.assignee_id == user.id, Ticket.status.in_(repo.OPEN_STATUSES)),
        Ticket.organization_id,
    )
    tickets = list(ctx.db.execute(stmt).unique().scalars())
    states = [sla_state(t, cal, settings.sla_at_risk_percent, at) for t in tickets]

    lo = datetime(day.year, day.month, day.day, tzinfo=cal.tz)
    nxt = day + timedelta(days=1)
    hi = datetime(nxt.year, nxt.month, nxt.day, tzinfo=cal.tz)
    appts = ctx.db.execute(
        ctx.scope.apply(
            select(func.count())
            .select_from(Appointment)
            .where(
                Appointment.tech_id == user.id,
                Appointment.status == "scheduled",
                Appointment.starts_at >= lo,
                Appointment.starts_at < hi,
            ),
            Appointment.organization_id,
        )
    ).scalar_one()

    week = metrics.utilisation(ctx, _monday(day), day)
    mine = next((r for r in week["rows"] if r["user_id"] == user.id), None)
    return dict(
        open_tickets=len(tickets),
        sla_at_risk=states.count("at_risk"),
        sla_breached=states.count("breached"),
        appointments_today=int(appts),
        week=dict(
            logged_minutes=mine["logged_minutes"] if mine else 0,
            billable_minutes=mine["billable_minutes"] if mine else 0,
            capacity_minutes=mine["capacity_minutes"] if mine else 0,
            utilisation_bp=mine["utilisation_bp"] if mine else None,
        ),
    )


def manager(ctx: Ctx) -> dict:
    """Month-to-date money, receivables, unbilled work, 30-day SLA and last week's utilisation."""
    on = today(ctx)
    prof = metrics.profitability(ctx, on.replace(day=1), on)["totals"]
    ag = metrics.aging(ctx)["totals"]
    unbilled = reports.unbilled(ctx, None)["totals"]
    sla = metrics.sla(ctx, on - timedelta(days=29), on)["totals"]
    last_monday = _monday(on) - timedelta(days=7)
    util = metrics.utilisation(ctx, last_monday, last_monday + timedelta(days=6))["totals"]
    return dict(
        revenue_mtd_cents=prof["revenue_cents"],
        margin_mtd_cents=prof["margin_cents"],
        margin_mtd_bp=prof["margin_bp"],
        ar_total_cents=ag["total_open_cents"],
        ar_buckets={
            k: ag[k]
            for k in (
                "current_cents",
                "d1_30_cents",
                "d31_60_cents",
                "d61_90_cents",
                "d90_plus_cents",
            )
        },
        unbilled_cents=unbilled["total_cents"],
        sla_30d=dict(
            first_response_met_bp=sla["first_response"]["met_bp"],
            resolution_met_bp=sla["resolution"]["met_bp"],
            n=sla["n"],
        ),
        team_utilisation_last_week_bp=util["utilisation_bp"],
    )
