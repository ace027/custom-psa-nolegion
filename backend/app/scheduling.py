"""Scheduling: per-user timezone and working hours, time off (request + admin approval) and
ticket-linked appointments.

Conflicts (outside hours, time off, double booking) are warnings returned with the appointment;
they never block a booking. Only APPROVED time off removes availability; pending time off is
reported as a `time_off_pending` conflict. Appointments are client-owned: queries go through
Scope and RLS backs them up. Nothing here is deleted: time off and appointments are cancelled.
Every write is audited in the same transaction."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Select, select

from app import audit, availability, calendar_sync
from app import permissions as P
from app import repositories as repo
from app import ticket_services as tsvc
from app.deps import Ctx
from app.errors import Conflict, Forbidden, NotFound
from app.models import (
    Appointment,
    Holiday,
    Organization,
    Settings,
    Ticket,
    User,
    UserTimeOff,
    UserWorkHours,
)

BOOKABLE_ROLES = ("admin", "tech")
MAX_APPOINTMENT = timedelta(hours=24)
MAX_TIME_OFF = timedelta(days=366)
MAX_APPOINTMENT_RANGE = timedelta(days=62)
MAX_CONFLICT_RANGE = timedelta(days=8)
MAX_AVAILABILITY_RANGE = timedelta(days=31)
MAX_AVAILABILITY_USERS = 50
EARLIEST = datetime(1970, 1, 1, tzinfo=UTC)
LATEST = datetime(2200, 1, 1, tzinfo=UTC)


class InvalidSchedule(ValueError):
    """A request the API answers with 422 (bad timezone, bad range, missing range)."""


# ---- helpers ----------------------------------------------------------------------------------
def _is_approver(ctx: Ctx) -> bool:
    return P.has_permission(ctx.user.role, P.TIMEOFF_APPROVE)


def _bookable(ctx: Ctx, user_id: int) -> User:
    user = repo.get_user(ctx.db, user_id)
    if user is None or not user.is_active or user.role not in BOOKABLE_ROLES:
        raise Conflict("Appointments and working hours are for active admins and techs")
    return user


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError) as exc:
        raise InvalidSchedule(f"Unknown timezone: {name}") from exc


def _tz(user: User, settings: Settings) -> ZoneInfo:
    for name in (user.timezone, settings.timezone):
        if not name:
            continue
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            continue  # a bad stored zone must not take the whole board down
    return ZoneInfo("UTC")


def _holidays(ctx: Ctx, start: date, end: date) -> dict[date, tuple[int, int] | None]:
    rows = ctx.db.execute(
        select(Holiday).where(Holiday.on_date >= start, Holiday.on_date <= end)
    ).scalars()
    return {
        h.on_date: None
        if h.open_minute is None or h.close_minute is None
        else (h.open_minute, h.close_minute)
        for h in rows
    }


def _rows(ctx: Ctx, user_id: int) -> list[UserWorkHours]:
    return list(
        ctx.db.execute(
            select(UserWorkHours)
            .where(UserWorkHours.user_id == user_id)
            .order_by(UserWorkHours.weekday)
        ).scalars()
    )


def _weekly(ctx: Ctx, user: User) -> dict[int, tuple[int, int]]:
    rows = _rows(ctx, user.id)
    if not rows:
        return availability.default_weekly(repo.get_settings_row(ctx.db))
    return {r.weekday: (r.start_minute, r.end_minute) for r in rows}


def _aware(*values: datetime | None) -> None:
    for v in values:
        if v is None:
            continue
        if v.tzinfo is None:
            raise InvalidSchedule("Times must include a timezone offset (for example Z)")
        if not EARLIEST <= v < LATEST:  # keeps the day padding in _local_dates from overflowing
            raise InvalidSchedule(f"Times must fall between {EARLIEST.year} and {LATEST.year}")


def _range(start: datetime, end: datetime, longest: timedelta, what: str) -> None:
    _aware(start, end)
    if end <= start:
        raise InvalidSchedule("The end must be after the start")
    if end - start > longest:
        raise InvalidSchedule(f"{what} can span at most {_human(longest)}")


def _human(d: timedelta) -> str:
    return f"{d.days} days" if d.days else f"{int(d.total_seconds() // 3600)} hours"


def _local_dates(start: datetime, end: datetime, tz: ZoneInfo) -> tuple[date, date]:
    """Local dates that working_windows may look at for [start, end] (it pads a day each way)."""
    return (
        start.astimezone(tz).date() - timedelta(days=1),
        end.astimezone(tz).date() + timedelta(days=1),
    )


def _working(
    ctx: Ctx, user: User, start: datetime, end: datetime
) -> tuple[ZoneInfo, list[availability.Interval]]:
    settings = repo.get_settings_row(ctx.db)
    tz = _tz(user, settings)
    lo, hi = _local_dates(start, end, tz)
    return tz, availability.working_windows(
        start, end, tz, _weekly(ctx, user), _holidays(ctx, lo, hi)
    )


# ---- schedule ---------------------------------------------------------------------------------
def _self_or_approver(ctx: Ctx, user_id: int) -> None:
    if user_id != ctx.user.id and not _is_approver(ctx):
        raise Forbidden("You can only see or change your own schedule")


def _schedule_view(ctx: Ctx, user: User) -> dict:
    settings = repo.get_settings_row(ctx.db)
    rows = _rows(ctx, user.id)
    weekly = (
        {r.weekday: (r.start_minute, r.end_minute) for r in rows}
        if rows
        else availability.default_weekly(settings)
    )
    return dict(
        user_id=user.id,
        timezone=user.timezone or settings.timezone,
        timezone_override=user.timezone,
        uses_default_hours=not rows,
        work_hours=[
            dict(weekday=d, start_minute=s, end_minute=e) for d, (s, e) in sorted(weekly.items())
        ],
    )


def _schedule_snapshot(ctx: Ctx, user: User) -> dict:
    return {
        "timezone": user.timezone,
        "work_hours": [[r.weekday, r.start_minute, r.end_minute] for r in _rows(ctx, user.id)],
    }


def get_schedule(ctx: Ctx, user_id: int) -> dict:
    _self_or_approver(ctx, user_id)
    user = repo.get_user(ctx.db, user_id)
    if user is None:
        raise NotFound("User not found")
    return _schedule_view(ctx, user)


def put_schedule(ctx: Ctx, user_id: int, data: dict) -> dict:
    """Replace the user's timezone override and weekly hours (null = the org defaults)."""
    _self_or_approver(ctx, user_id)
    user = _bookable(ctx, user_id)
    tz = data.get("timezone")
    if tz is not None:
        tz = tz.strip() or None
    if tz is not None:
        _zone(tz)
    hours = data.get("work_hours")
    if hours is not None:
        if not hours:
            raise InvalidSchedule("List at least one working day, or send null")
        if len({h["weekday"] for h in hours}) != len(hours):
            raise InvalidSchedule("Each weekday can appear only once")
        for h in hours:
            if not 0 <= h["start_minute"] < h["end_minute"] <= 1440:
                raise InvalidSchedule("Each day needs 0 <= start_minute < end_minute <= 1440")
    before = _schedule_snapshot(ctx, user)
    user.timezone = tz
    for row in _rows(ctx, user.id):
        ctx.db.delete(row)
    ctx.db.flush()
    for h in hours or []:
        ctx.db.add(
            UserWorkHours(
                user_id=user.id,
                weekday=h["weekday"],
                start_minute=h["start_minute"],
                end_minute=h["end_minute"],
            )
        )
    ctx.db.flush()
    audit.record(
        ctx.db,
        ctx.user,
        "schedule.update",
        user,
        before=before,
        after=_schedule_snapshot(ctx, user),
    )
    return _schedule_view(ctx, user)


# ---- time off ---------------------------------------------------------------------------------
def time_off_view(ctx: Ctx, t: UserTimeOff) -> dict:
    user = repo.get_user(ctx.db, t.user_id)
    can_see_reason = t.user_id == ctx.user.id or _is_approver(ctx)
    return dict(
        id=t.id,
        user_id=t.user_id,
        user_name=user.display_name if user else f"User {t.user_id}",
        starts_at=t.starts_at,
        ends_at=t.ends_at,
        reason=t.reason if can_see_reason else None,
        status=t.status,
        requested_by=t.requested_by,
        decided_by=t.decided_by,
        decided_at=t.decided_at,
        decision_note=t.decision_note if can_see_reason else None,
        created_at=t.created_at,
    )


def _get_time_off(ctx: Ctx, time_off_id: int) -> UserTimeOff:
    """Load and lock the request, so concurrent decisions and cancels serialize."""
    t = ctx.db.execute(
        select(UserTimeOff).where(UserTimeOff.id == time_off_id).with_for_update()
    ).scalar_one_or_none()
    if t is None:
        raise NotFound("Time off not found")
    return t


def create_time_off(ctx: Ctx, data: dict) -> UserTimeOff:
    """Request time off. An approver's own entry (for anyone) is approved at once."""
    user_id = data.get("user_id") or ctx.user.id
    approver = _is_approver(ctx)
    if user_id != ctx.user.id and not approver:
        raise Forbidden("Only admins can enter time off for someone else")
    _bookable(ctx, user_id)
    _range(data["starts_at"], data["ends_at"], MAX_TIME_OFF, "Time off")
    reason = (data.get("reason") or "").strip() or None
    t = UserTimeOff(
        user_id=user_id,
        starts_at=data["starts_at"],
        ends_at=data["ends_at"],
        reason=reason,
        status="approved" if approver else "pending",
        requested_by=ctx.user.id,
        decided_by=ctx.user.id if approver else None,
        decided_at=tsvc.now() if approver else None,
    )
    ctx.db.add(t)
    ctx.db.flush()
    ctx.db.refresh(t)
    audit.record(ctx.db, ctx.user, "time_off.create", t, after=audit.snapshot(t))
    return t


def decide_time_off(ctx: Ctx, time_off_id: int, approve: bool, note: str | None) -> UserTimeOff:
    if not _is_approver(ctx):
        raise Forbidden("Only admins can approve or reject time off")
    t = _get_time_off(ctx, time_off_id)
    if t.status != "pending":
        raise Conflict(f"This request is already {t.status}")
    before = audit.snapshot(t)
    t.status = "approved" if approve else "rejected"
    t.decided_by = ctx.user.id
    t.decided_at = tsvc.now()
    t.decision_note = (note or "").strip() or None
    ctx.db.flush()
    ctx.db.refresh(t)
    audit.record(
        ctx.db,
        ctx.user,
        "time_off.approve" if approve else "time_off.reject",
        t,
        before=before,
        after=audit.snapshot(t),
    )
    return t


def cancel_time_off(ctx: Ctx, time_off_id: int) -> UserTimeOff:
    t = _get_time_off(ctx, time_off_id)
    if t.user_id != ctx.user.id and not _is_approver(ctx):
        raise Forbidden("You can only cancel your own time off")
    if not (t.status == "pending" or (t.status == "approved" and t.ends_at > tsvc.now())):
        raise Conflict(
            "Only pending time off, or approved time off that has not ended, can be cancelled"
        )
    before = audit.snapshot(t)
    t.status = "cancelled"
    ctx.db.flush()
    ctx.db.refresh(t)
    audit.record(ctx.db, ctx.user, "time_off.cancel", t, before=before, after=audit.snapshot(t))
    return t


def list_time_off(
    ctx: Ctx,
    *,
    user_id: int | None,
    status: str | None,
    start: datetime | None,
    end: datetime | None,
) -> list[UserTimeOff]:
    _aware(start, end)
    q = select(UserTimeOff)
    if user_id is not None:
        q = q.where(UserTimeOff.user_id == user_id)
    if status is not None:
        q = q.where(UserTimeOff.status == status)
    if start is not None:
        q = q.where(UserTimeOff.ends_at > start)
    if end is not None:
        q = q.where(UserTimeOff.starts_at < end)
    return list(
        ctx.db.execute(q.order_by(UserTimeOff.starts_at, UserTimeOff.id).limit(1000)).scalars()
    )


# ---- appointments -----------------------------------------------------------------------------
def _scoped(ctx: Ctx) -> Select[tuple[Appointment]]:
    return ctx.scope.apply(select(Appointment), Appointment.organization_id)


def get_appointment(ctx: Ctx, appointment_id: int, *, lock: bool = False) -> Appointment:
    q = _scoped(ctx).where(Appointment.id == appointment_id)
    if lock:  # writers serialize, so a move and a cancel cannot interleave
        q = q.with_for_update()
    a = ctx.db.execute(q).scalar_one_or_none()
    if a is None:
        raise NotFound("Appointment not found")
    return a


def appointment_view(ctx: Ctx, a: Appointment, *, with_conflicts: bool = False) -> dict:
    org = ctx.db.get(Organization, a.organization_id)
    ticket = ctx.db.get(Ticket, a.ticket_id)
    tech = repo.get_user(ctx.db, a.tech_id)
    return dict(
        id=a.id,
        organization_id=a.organization_id,
        organization_name=org.name if org else None,
        ticket_id=a.ticket_id,
        ticket_number=ticket.number if ticket else None,
        ticket_subject=ticket.subject if ticket else None,
        tech_id=a.tech_id,
        tech_name=tech.display_name if tech else None,
        starts_at=a.starts_at,
        ends_at=a.ends_at,
        status=a.status,
        notes=a.notes,
        client_visible=a.client_visible,
        created_by=a.created_by,
        cancelled_at=a.cancelled_at,
        cancel_reason=a.cancel_reason,
        conflicts=conflicts_for(ctx, a) if with_conflicts else [],
    )


def create_appointment(ctx: Ctx, data: dict) -> Appointment:
    ticket = repo.get_ticket(ctx.db, ctx.scope, data["ticket_id"])
    if ticket is None:
        raise NotFound("Ticket not found")
    if ticket.organization_id is None:
        raise Conflict("Assign the ticket to a client first")
    if ticket.status == "closed":
        raise Conflict("Reopen the ticket first")
    _bookable(ctx, data["tech_id"])
    _range(data["starts_at"], data["ends_at"], MAX_APPOINTMENT, "An appointment")
    a = Appointment(
        organization_id=ticket.organization_id,
        ticket_id=ticket.id,
        tech_id=data["tech_id"],
        starts_at=data["starts_at"],
        ends_at=data["ends_at"],
        status="scheduled",
        notes=data.get("notes"),
        client_visible=data.get("client_visible", True),
        created_by=ctx.user.id,
    )
    ctx.db.add(a)
    ctx.db.flush()
    ctx.db.refresh(a)
    calendar_sync.enqueue(ctx.db, a)
    audit.record(
        ctx.db,
        ctx.user,
        "appointment.create",
        a,
        after=audit.snapshot(a),
        organization_id=a.organization_id,
    )
    return a


def update_appointment(ctx: Ctx, appointment_id: int, data: dict) -> Appointment:
    """Move, reassign or annotate a scheduled appointment. `data` holds only the sent fields."""
    a = get_appointment(ctx, appointment_id, lock=True)
    if a.status != "scheduled":
        raise Conflict("Only scheduled appointments can be changed")
    for f in ("tech_id", "starts_at", "ends_at", "client_visible"):
        if f in data and data[f] is None:
            raise InvalidSchedule(f"{f} cannot be cleared")
    if any(f in data for f in ("tech_id", "starts_at", "ends_at")):
        ticket = ctx.db.get(Ticket, a.ticket_id)
        if ticket is not None and ticket.status == "closed":
            raise Conflict("Reopen the ticket first")
    tech_id = _bookable(ctx, data["tech_id"]).id if "tech_id" in data else a.tech_id
    starts = data.get("starts_at", a.starts_at)
    ends = data.get("ends_at", a.ends_at)
    _range(starts, ends, MAX_APPOINTMENT, "An appointment")
    before = audit.snapshot(a)
    moved = (a.tech_id, a.starts_at, a.ends_at) != (tech_id, starts, ends)
    a.tech_id, a.starts_at, a.ends_at = tech_id, starts, ends
    if "notes" in data:
        a.notes = data["notes"]
    if "client_visible" in data:
        a.client_visible = data["client_visible"]
    ctx.db.flush()
    ctx.db.refresh(a)
    if moved:
        calendar_sync.enqueue(ctx.db, a)
    audit.record(
        ctx.db,
        ctx.user,
        "appointment.update",
        a,
        before=before,
        after=audit.snapshot(a),
        organization_id=a.organization_id,
    )
    return a


def cancel_appointment(ctx: Ctx, appointment_id: int, reason: str | None) -> Appointment:
    a = get_appointment(ctx, appointment_id, lock=True)
    if a.status != "scheduled":
        raise Conflict("This appointment is already cancelled")
    before = audit.snapshot(a)
    a.status = "cancelled"
    a.cancelled_at = tsvc.now()
    a.cancelled_by = ctx.user.id
    a.cancel_reason = (reason or "").strip() or None
    ctx.db.flush()
    ctx.db.refresh(a)
    calendar_sync.enqueue(ctx.db, a)
    audit.record(
        ctx.db,
        ctx.user,
        "appointment.cancel",
        a,
        before=before,
        after=audit.snapshot(a),
        organization_id=a.organization_id,
    )
    return a


def list_appointments(
    ctx: Ctx,
    *,
    tech_id: int | None,
    ticket_id: int | None,
    start: datetime | None,
    end: datetime | None,
    include_cancelled: bool,
    with_conflicts: bool = False,
) -> list[Appointment]:
    """Appointments overlapping [start, end). The range is required unless ticket_id is given.
    with_conflicts (the caller then computes conflicts per item) needs a range of at most 8 days."""
    _aware(start, end)
    if with_conflicts and (start is None or end is None or end - start > MAX_CONFLICT_RANGE):
        raise InvalidSchedule("with_conflicts needs a from/to range of at most 8 days")
    if ticket_id is None and (start is None or end is None):
        raise InvalidSchedule("Give from and to (or a ticket_id)")
    if start is not None and end is not None:
        _range(start, end, MAX_APPOINTMENT_RANGE, "The range")
    q = _scoped(ctx)
    if tech_id is not None:
        q = q.where(Appointment.tech_id == tech_id)
    if ticket_id is not None:
        q = q.where(Appointment.ticket_id == ticket_id)
    if start is not None:
        q = q.where(Appointment.ends_at > start)
    if end is not None:
        q = q.where(Appointment.starts_at < end)
    if not include_cancelled:
        q = q.where(Appointment.status == "scheduled")
    return list(
        ctx.db.execute(q.order_by(Appointment.starts_at, Appointment.id).limit(2000)).scalars()
    )


def _busy_time_off(
    ctx: Ctx, user_id: int, start: datetime, end: datetime, statuses: tuple[str, ...]
) -> list[UserTimeOff]:
    return list(
        ctx.db.execute(
            select(UserTimeOff)
            .where(
                UserTimeOff.user_id == user_id,
                UserTimeOff.status.in_(statuses),
                UserTimeOff.starts_at < end,
                UserTimeOff.ends_at > start,
            )
            .order_by(UserTimeOff.starts_at)
        ).scalars()
    )


def _busy_appointments(ctx: Ctx, tech_id: int, start: datetime, end: datetime) -> list[Appointment]:
    return list(
        ctx.db.execute(
            _scoped(ctx)
            .where(
                Appointment.tech_id == tech_id,
                Appointment.status == "scheduled",
                Appointment.starts_at < end,
                Appointment.ends_at > start,
            )
            .order_by(Appointment.starts_at)
        ).scalars()
    )


def conflicts_for(ctx: Ctx, a: Appointment) -> list[dict]:
    """Warnings for a scheduled appointment (cancelled ones have none)."""
    if a.status != "scheduled":
        return []
    tech = repo.get_user(ctx.db, a.tech_id)
    if tech is None:
        return []
    slot = (a.starts_at, a.ends_at)
    _, working = _working(ctx, tech, a.starts_at - timedelta(days=1), a.ends_at + timedelta(days=1))
    time_off = [
        (t.id, t.status, (t.starts_at, t.ends_at))
        for t in _busy_time_off(ctx, a.tech_id, *slot, ("pending", "approved"))
    ]
    others = [
        (o.id, (o.starts_at, o.ends_at))
        for o in _busy_appointments(ctx, a.tech_id, *slot)
        if o.id != a.id
    ]
    return [
        {"time_off_id": None, "appointment_id": None, **c}
        for c in availability.conflicts(slot, working, time_off, others)
    ]


# ---- availability -----------------------------------------------------------------------------
def availability_for(
    ctx: Ctx, user_ids: list[int] | None, start: datetime, end: datetime
) -> list[dict]:
    """Working, approved time off, scheduled appointments and free windows per user.
    No user_ids = every active admin and tech."""
    _range(start, end, MAX_AVAILABILITY_RANGE, "Availability")
    if user_ids and len(set(user_ids)) > MAX_AVAILABILITY_USERS:
        raise InvalidSchedule(f"Ask for at most {MAX_AVAILABILITY_USERS} users at a time")
    if user_ids:
        users = [_bookable(ctx, uid) for uid in dict.fromkeys(user_ids)]
    else:
        users = list(
            ctx.db.execute(
                select(User)
                .where(User.is_active.is_(True), User.role.in_(BOOKABLE_ROLES))
                .order_by(User.id)
            ).scalars()
        )
    out = []
    for user in users:
        tz, working = _working(ctx, user, start, end)
        off = [
            (t.starts_at, t.ends_at)
            for t in _busy_time_off(ctx, user.id, start, end, ("approved",))
        ]
        pending = [
            (t.starts_at, t.ends_at) for t in _busy_time_off(ctx, user.id, start, end, ("pending",))
        ]
        appts = _busy_appointments(ctx, user.id, start, end)
        free = availability.subtract(working, off + [(a.starts_at, a.ends_at) for a in appts])
        out.append(
            dict(
                user_id=user.id,
                timezone=tz.key,
                working=[dict(starts_at=s, ends_at=e) for s, e in working],
                time_off=[dict(starts_at=s, ends_at=e) for s, e in off],
                time_off_pending=[dict(starts_at=s, ends_at=e) for s, e in pending],
                appointments=[
                    dict(id=a.id, starts_at=a.starts_at, ends_at=a.ends_at) for a in appts
                ],
                free=[dict(starts_at=s, ends_at=e) for s, e in free],
            )
        )
    return out
