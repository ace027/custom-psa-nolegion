"""Timesheet approval: submit a week, an admin approves or returns it, and a submitted or
approved week is locked against edits. Approval is for payroll and records only: billing runs do
not look at it."""

from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import and_, func, select

from app import audit
from app import repositories as repo
from app.deps import Ctx
from app.errors import Conflict, NotFound
from app.models import InternalTimeEntry, TimeCategory, TimeEntry, Timer, Timesheet, User

LOCKED = ("submitted", "approved")


def utcnow() -> datetime:
    return datetime.now(UTC)


def week_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def get(ctx: Ctx, user_id: int, week_start: date) -> Timesheet | None:
    return ctx.db.execute(
        select(Timesheet).where(Timesheet.user_id == user_id, Timesheet.week_start == week_start)
    ).scalar_one_or_none()


def assert_open(ctx: Ctx, user_id: int, day: date) -> None:
    """Refuse a change to time that falls in a submitted or approved week."""
    sheet = get(ctx, user_id, week_of(day))
    if sheet is not None and sheet.status in LOCKED:
        raise Conflict(
            f"The week of {sheet.week_start} is {sheet.status} and locked. "
            "Ask an admin to return it to make changes"
        )


def _minutes(ctx: Ctx, user_id: int, week_start: date) -> int:
    end = week_start + timedelta(days=6)
    t = ctx.db.execute(
        select(func.coalesce(func.sum(TimeEntry.minutes_actual), 0)).where(
            TimeEntry.user_id == user_id,
            TimeEntry.work_date.between(week_start, end),
            TimeEntry.voided_at.is_(None),
        )
    ).scalar_one()
    i = ctx.db.execute(
        select(func.coalesce(func.sum(InternalTimeEntry.minutes), 0)).where(
            InternalTimeEntry.user_id == user_id,
            InternalTimeEntry.work_date.between(week_start, end),
            InternalTimeEntry.voided_at.is_(None),
        )
    ).scalar_one()
    return int(t) + int(i)


def _monday(week_start: date) -> None:
    if week_start.weekday() != 0:
        raise Conflict("A timesheet week starts on a Monday")


def submit(ctx: Ctx, week_start: date) -> Timesheet:
    _monday(week_start)
    from app import ticket_services as tsvc  # lazy: it imports this module for the edit lock

    if week_start > tsvc._entry_date(ctx, None):
        raise Conflict("That week has not started yet")
    if ctx.db.get(Timer, ctx.user.id) is not None:
        raise Conflict("Stop or discard your running timer before submitting")
    sheet = get(ctx, ctx.user.id, week_start)
    if sheet is not None and sheet.status != "returned":
        raise Conflict(f"This week is already {sheet.status}")
    if _minutes(ctx, ctx.user.id, week_start) == 0:
        raise Conflict("Nothing is logged this week")
    before = audit.snapshot(sheet) if sheet else None
    if sheet is None:
        sheet = Timesheet(user_id=ctx.user.id, week_start=week_start, status="submitted")
        ctx.db.add(sheet)
    sheet.status = "submitted"
    sheet.submitted_at = utcnow()
    ctx.db.flush()
    audit.record(
        ctx.db, ctx.user, "timesheet.submit", sheet, before=before, after=audit.snapshot(sheet)
    )
    return sheet


def _target(ctx: Ctx, user_id: int, week_start: date) -> Timesheet:
    _monday(week_start)
    sheet = get(ctx, user_id, week_start)
    if sheet is None or sheet.status == "returned":
        raise NotFound("That week has not been submitted")
    return sheet


def approve(ctx: Ctx, user_id: int, week_start: date) -> Timesheet:
    sheet = _target(ctx, user_id, week_start)
    if sheet.status == "approved":
        raise Conflict("Already approved")
    before = audit.snapshot(sheet)
    sheet.status = "approved"
    sheet.approved_by, sheet.approved_at = ctx.user.id, utcnow()
    ctx.db.flush()
    audit.record(
        ctx.db, ctx.user, "timesheet.approve", sheet, before=before, after=audit.snapshot(sheet)
    )
    return sheet


def return_sheet(ctx: Ctx, user_id: int, week_start: date, reason: str) -> Timesheet:
    """Send a submitted OR approved week back: it is editable again until resubmitted."""
    sheet = _target(ctx, user_id, week_start)
    before = audit.snapshot(sheet)
    sheet.status = "returned"
    sheet.returned_by, sheet.returned_at = ctx.user.id, utcnow()
    sheet.return_reason = reason.strip()
    sheet.approved_by = sheet.approved_at = None
    ctx.db.flush()
    audit.record(
        ctx.db, ctx.user, "timesheet.return", sheet, before=before, after=audit.snapshot(sheet)
    )
    return sheet


def queue(ctx: Ctx, status: str | None) -> list[dict]:
    q = select(Timesheet, User.display_name).join(User, User.id == Timesheet.user_id)
    q = q.where(Timesheet.status == status) if status else q
    q = q.order_by(Timesheet.week_start.desc(), User.display_name)
    out = []
    for sheet, name in ctx.db.execute(q.limit(500)).all():
        out.append(
            dict(
                id=sheet.id,
                user_id=sheet.user_id,
                user_name=name,
                week_start=sheet.week_start,
                status=sheet.status,
                submitted_at=sheet.submitted_at,
                approved_at=sheet.approved_at,
                return_reason=sheet.return_reason,
                total_minutes=_minutes(ctx, sheet.user_id, sheet.week_start),
            )
        )
    return out


def _hours(minutes: int) -> str:
    return str((Decimal(minutes) / 60).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def export_rows(ctx: Ctx, start: date, end: date) -> list[list]:
    """Actual hours per person, day and category, for APPROVED weeks only. Voided time is out."""
    if end < start:
        raise Conflict("The end date is before the start date")
    approved = and_(
        Timesheet.status == "approved",
    )
    rows: list[tuple] = []
    t = (
        select(TimeEntry.user_id, TimeEntry.work_date, func.sum(TimeEntry.minutes_actual))
        .join(
            Timesheet,
            and_(
                Timesheet.user_id == TimeEntry.user_id,
                TimeEntry.work_date >= Timesheet.week_start,
                TimeEntry.work_date <= Timesheet.week_start + 6,
            ),
        )
        .where(approved, TimeEntry.voided_at.is_(None), TimeEntry.work_date.between(start, end))
        .group_by(TimeEntry.user_id, TimeEntry.work_date)
    )
    for uid, day, mins in ctx.db.execute(t):
        rows.append((uid, day, "Ticket time", int(mins)))
    i = (
        select(
            InternalTimeEntry.user_id,
            InternalTimeEntry.work_date,
            TimeCategory.name,
            func.sum(InternalTimeEntry.minutes),
        )
        .join(TimeCategory, TimeCategory.id == InternalTimeEntry.category_id)
        .join(
            Timesheet,
            and_(
                Timesheet.user_id == InternalTimeEntry.user_id,
                InternalTimeEntry.work_date >= Timesheet.week_start,
                InternalTimeEntry.work_date <= Timesheet.week_start + 6,
            ),
        )
        .where(
            approved,
            InternalTimeEntry.voided_at.is_(None),
            InternalTimeEntry.work_date.between(start, end),
        )
        .group_by(InternalTimeEntry.user_id, InternalTimeEntry.work_date, TimeCategory.name)
    )
    for uid, day, cat, mins in ctx.db.execute(i):
        rows.append((uid, day, cat, int(mins)))
    users = {u: repo.get_user(ctx.db, u) for u in {r[0] for r in rows}}
    rows.sort(key=lambda r: (users[r[0]].display_name.lower(), r[1], r[2]))
    return [[users[u].display_name, users[u].email, d, c, _hours(m)] for u, d, c, m in rows]
