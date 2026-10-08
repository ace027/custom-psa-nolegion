"""Timers, internal (non-ticket) time and the weekly timesheet view.

Ticket time keeps going through ticket_services.add_time (rounding, locking, audit), so a timer
is only a convenient way to arrive at the same entry. Internal time is separate and never
billable. A "week" is Monday to Sunday in the business time zone."""

from datetime import date, timedelta

from sqlalchemy import select

from app import audit, timesheets
from app import repositories as repo
from app import ticket_services as tsvc
from app.deps import Ctx
from app.errors import Conflict, Forbidden, NotFound
from app.models import (
    InternalTimeEntry,
    TimeCategory,
    TimeEntry,
    Timer,
    WorkType,
)

MAX_MINUTES = 1440


def week_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _own_or_admin(ctx: Ctx, user_id: int) -> None:
    if user_id != ctx.user.id and ctx.user.role != "admin":
        raise Forbidden("You can only change your own time")


def _category(ctx: Ctx, category_id: int) -> TimeCategory:
    cat = ctx.db.get(TimeCategory, category_id)
    if cat is None or cat.archived_at is not None:
        raise Conflict("Unknown or archived time category")
    return cat


# ---- internal time --------------------------------------------------------------------------
def add_internal(ctx: Ctx, data: dict) -> InternalTimeEntry:
    _category(ctx, data["category_id"])
    user_id = data.get("user_id") or ctx.user.id
    if user_id != ctx.user.id:
        if ctx.user.role != "admin":
            raise Forbidden("Only admins can log time for someone else")
        target = repo.get_user(ctx.db, user_id)
        if target is None or not target.is_active:
            raise Conflict("Unknown or inactive user")
    work_date = tsvc._entry_date(ctx, data.get("work_date"))
    timesheets.assert_open(ctx, user_id, work_date)
    entry = InternalTimeEntry(
        user_id=user_id,
        category_id=data["category_id"],
        work_date=work_date,
        minutes=data["minutes"],
        note=data.get("note"),
    )
    ctx.db.add(entry)
    ctx.db.flush()
    audit.record(ctx.db, ctx.user, "internal_time.create", entry, after=audit.snapshot(entry))
    return entry


def _get_internal(ctx: Ctx, entry_id: int) -> InternalTimeEntry:
    entry = ctx.db.get(InternalTimeEntry, entry_id)
    if entry is None:
        raise NotFound("Time entry not found")
    _own_or_admin(ctx, entry.user_id)
    if entry.voided_at:
        raise Conflict("Voided time entries cannot be changed")
    return entry


def update_internal(ctx: Ctx, entry_id: int, data: dict) -> InternalTimeEntry:
    entry = _get_internal(ctx, entry_id)
    timesheets.assert_open(ctx, entry.user_id, entry.work_date)
    if data.get("work_date"):
        timesheets.assert_open(ctx, entry.user_id, data["work_date"])
    before = audit.snapshot(entry)
    if data.get("category_id"):
        _category(ctx, data["category_id"])
        entry.category_id = data["category_id"]
    for key in ("minutes", "work_date", "note"):
        if key in data and data[key] is not None:
            setattr(entry, key, data[key])
    ctx.db.flush()
    ctx.db.refresh(entry)
    audit.record(
        ctx.db,
        ctx.user,
        "internal_time.update",
        entry,
        before=before,
        after=audit.snapshot(entry),
    )
    return entry


def void_internal(ctx: Ctx, entry_id: int) -> InternalTimeEntry:
    entry = _get_internal(ctx, entry_id)
    timesheets.assert_open(ctx, entry.user_id, entry.work_date)
    before = audit.snapshot(entry)
    entry.voided_at = tsvc.now()
    ctx.db.flush()
    ctx.db.refresh(entry)
    audit.record(
        ctx.db,
        ctx.user,
        "internal_time.void",
        entry,
        before=before,
        after=audit.snapshot(entry),
    )
    return entry


# ---- timers ---------------------------------------------------------------------------------
def current_timer(ctx: Ctx) -> Timer | None:
    return ctx.db.get(Timer, ctx.user.id)


def timer_view(ctx: Ctx, timer: Timer) -> dict:
    ticket = repo.get_ticket(ctx.db, ctx.scope, timer.ticket_id) if timer.ticket_id else None
    category = ctx.db.get(TimeCategory, timer.category_id) if timer.category_id else None
    return dict(
        ticket_id=timer.ticket_id,
        ticket_number=ticket.number if ticket else None,
        ticket_subject=ticket.subject if ticket else None,
        work_type_id=timer.work_type_id,
        category_id=timer.category_id,
        category_name=category.name if category else None,
        billable=timer.billable,
        note=timer.note,
        started_at=timer.started_at,
        elapsed_seconds=max(0, int((tsvc.now() - timer.started_at).total_seconds())),
    )


def start_timer(ctx: Ctx, data: dict) -> Timer:
    if current_timer(ctx) is not None:
        raise Conflict("A timer is already running: stop or discard it first")
    ticket_id, category_id = data.get("ticket_id"), data.get("category_id")
    if (ticket_id is None) == (category_id is None):
        raise Conflict("Choose either a ticket or an internal category")
    work_type_id = None
    if ticket_id is not None:
        ticket = repo.get_ticket(ctx.db, ctx.scope, ticket_id)
        if ticket is None:
            raise NotFound("Ticket not found")
        if ticket.organization_id is None:
            raise Conflict("Match the ticket to an organization before logging time")
        work_type_id = data.get("work_type_id")
        wt = ctx.db.get(WorkType, work_type_id) if work_type_id else None
        if wt is None or wt.archived_at is not None:
            raise Conflict("Choose an active work type for ticket time")
    else:
        _category(ctx, category_id)
    timer = Timer(
        user_id=ctx.user.id,
        ticket_id=ticket_id,
        work_type_id=work_type_id,
        category_id=category_id,
        billable=bool(data.get("billable", True)) if ticket_id is not None else False,
        note=data.get("note"),
        started_at=tsvc.now(),
    )
    ctx.db.add(timer)
    ctx.db.flush()
    audit.record(ctx.db, ctx.user, "timer.start", timer, after=audit.snapshot(timer))
    return timer


def stop_timer(ctx: Ctx) -> dict:
    """Turn the running timer into a normal entry. Returns {kind, id, minutes}."""
    timer = current_timer(ctx)
    if timer is None:
        raise NotFound("No timer is running")
    seconds = (tsvc.now() - timer.started_at).total_seconds()
    minutes = max(1, -(-int(seconds) // 60))  # round up; a stopped timer is at least a minute
    if minutes > MAX_MINUTES:
        raise Conflict("This timer ran for over 24 hours. Discard it and enter the time by hand")
    date_ = tsvc._entry_date(ctx, None)
    if timer.ticket_id is not None:
        entry = tsvc.add_time(
            ctx,
            timer.ticket_id,
            dict(
                work_type_id=timer.work_type_id,
                minutes=minutes,
                work_date=date_,
                billable=timer.billable,
                note=timer.note,
            ),
        )
        out = dict(kind="ticket", id=entry.id, minutes=minutes)
    else:
        entry = add_internal(
            ctx,
            dict(category_id=timer.category_id, minutes=minutes, work_date=date_, note=timer.note),
        )
        out = dict(kind="internal", id=entry.id, minutes=minutes)
    audit.record(ctx.db, ctx.user, "timer.stop", timer, after=out)
    ctx.db.delete(timer)
    ctx.db.flush()
    return out


def discard_timer(ctx: Ctx) -> None:
    timer = current_timer(ctx)
    if timer is None:
        raise NotFound("No timer is running")
    audit.record(ctx.db, ctx.user, "timer.discard", timer, before=audit.snapshot(timer))
    ctx.db.delete(timer)
    ctx.db.flush()


# ---- weekly timesheet -----------------------------------------------------------------------
def timesheet(ctx: Ctx, week_start: date, user_id: int | None) -> dict:
    if week_start.weekday() != 0:
        raise Conflict("A timesheet week starts on a Monday")
    target_id = user_id or ctx.user.id
    if target_id != ctx.user.id and ctx.user.role != "admin":
        raise Forbidden("Only admins can view someone else's timesheet")
    target = repo.get_user(ctx.db, target_id)
    if target is None:
        raise NotFound("User not found")
    end = week_start + timedelta(days=6)
    rows: list[dict] = []
    ticket_entries = ctx.db.execute(
        select(TimeEntry)
        .where(
            TimeEntry.user_id == target_id,
            TimeEntry.work_date >= week_start,
            TimeEntry.work_date <= end,
            TimeEntry.voided_at.is_(None),
        )
        .order_by(TimeEntry.work_date, TimeEntry.id)
    ).scalars()
    work_types = {w.id: w.name for w in repo.list_lookup(ctx.db, WorkType, True)}
    for e in ticket_entries:
        t = repo.get_ticket(ctx.db, ctx.scope, e.ticket_id)
        rows.append(
            dict(
                kind="ticket",
                id=e.id,
                work_date=e.work_date,
                label=f"#{t.number} {t.subject}" if t else f"Ticket {e.ticket_id}",
                detail=work_types.get(e.work_type_id),
                ticket_id=e.ticket_id,
                minutes_actual=e.minutes_actual,
                minutes_billable=e.minutes_billable,
                billable=e.billable,
                note=e.note,
                invoiced=e.invoice_line_id is not None,
            )
        )
    for i in ctx.db.execute(
        select(InternalTimeEntry)
        .where(
            InternalTimeEntry.user_id == target_id,
            InternalTimeEntry.work_date >= week_start,
            InternalTimeEntry.work_date <= end,
            InternalTimeEntry.voided_at.is_(None),
        )
        .order_by(InternalTimeEntry.work_date, InternalTimeEntry.id)
    ).scalars():
        rows.append(
            dict(
                kind="internal",
                id=i.id,
                work_date=i.work_date,
                label=i.category.name,
                detail=None,
                ticket_id=None,
                minutes_actual=i.minutes,
                minutes_billable=0,
                billable=False,
                note=i.note,
                invoiced=False,
            )
        )
    rows.sort(key=lambda r: (r["work_date"], r["kind"], r["id"]))
    days = []
    for n in range(7):
        d = week_start + timedelta(days=n)
        day_rows = [r for r in rows if r["work_date"] == d]
        days.append(
            dict(
                date=d,
                minutes=sum(r["minutes_actual"] for r in day_rows),
                billable_minutes=sum(r["minutes_billable"] for r in day_rows),
            )
        )
    sheet = timesheets.get(ctx, target_id, week_start)
    return dict(
        status=sheet.status if sheet else "open",
        return_reason=sheet.return_reason if sheet and sheet.status == "returned" else None,
        user_id=target.id,
        user_name=target.display_name,
        week_start=week_start,
        week_end=end,
        total_minutes=sum(d["minutes"] for d in days),
        billable_minutes=sum(d["billable_minutes"] for d in days),
        internal_minutes=sum(r["minutes_actual"] for r in rows if r["kind"] == "internal"),
        days=days,
        entries=rows,
    )
