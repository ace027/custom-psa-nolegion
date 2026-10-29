"""Scheduled report emails.

A schedule is weekly (previous Monday..Sunday, due from `weekday` on) or monthly (previous calendar
month, due from `day_of_month` on, 1..28). The worker calls run_due(); the unique (schedule_id,
period_start) run row makes it idempotent. Recipients are staff user ids who hold report:read; they
are checked when the schedule is saved and again when the email is queued.
"""

import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import audit
from app import permissions as P
from app import report_metrics as metrics
from app.deps import Ctx
from app.errors import Conflict, NotFound
from app.models import (
    EmailMessage,
    OutboundAttachment,
    ReportSchedule,
    ReportScheduleRun,
    User,
)
from app.scope import Scope

log = logging.getLogger("psa.reports")


# ---- management -------------------------------------------------------------------------
def _eligible(user: User | None) -> bool:
    return user is not None and user.is_active and P.has_permission(user.role, P.REPORT_READ)


def _validate_recipients(ctx: Ctx, ids: list[int]) -> list[int]:
    ids = list(dict.fromkeys(ids))
    users = {u.id: u for u in ctx.db.execute(select(User).where(User.id.in_(ids))).scalars()}
    for i in ids:
        u = users.get(i)
        if u is None:
            raise Conflict(f"User {i} does not exist")
        if not u.is_active:
            raise Conflict(f"{u.display_name} is not an active user")
        if not P.has_permission(u.role, P.REPORT_READ):
            raise Conflict(f"{u.display_name} cannot read reports (needs {P.REPORT_READ})")
    return ids


def _normalise_timing(data: dict) -> None:
    if data["frequency"] == "weekly":
        if data.get("weekday") is None:
            raise Conflict("A weekly schedule needs a weekday (0 = Monday)")
        data["day_of_month"] = None
    else:
        if data.get("day_of_month") is None:
            raise Conflict("A monthly schedule needs a day of the month (1 to 28)")
        data["weekday"] = None


def list_schedules(ctx: Ctx) -> list[ReportSchedule]:
    stmt = select(ReportSchedule).order_by(ReportSchedule.active.desc(), ReportSchedule.id)
    return list(ctx.db.execute(stmt).scalars())


def get_schedule(ctx: Ctx, schedule_id: int) -> ReportSchedule:
    obj = ctx.db.get(ReportSchedule, schedule_id)
    if obj is None:
        raise NotFound("Report schedule not found")
    return obj


def create_schedule(ctx: Ctx, data: dict) -> ReportSchedule:
    data = dict(data)
    _normalise_timing(data)
    data["recipient_user_ids"] = _validate_recipients(ctx, data["recipient_user_ids"])
    obj = ReportSchedule(**data, created_by=ctx.user.id if ctx.user else None)
    ctx.db.add(obj)
    ctx.db.flush()
    ctx.db.refresh(obj)
    audit.record(ctx.db, ctx.user, "report_schedule.create", obj, after=audit.snapshot(obj))
    return obj


def update_schedule(ctx: Ctx, schedule_id: int, changes: dict) -> ReportSchedule:
    obj = get_schedule(ctx, schedule_id)
    before = audit.snapshot(obj)
    merged = {
        k: getattr(obj, k) for k in ("name", "report", "frequency", "weekday", "day_of_month")
    }
    merged.update({k: v for k, v in changes.items() if k in merged and v is not None})
    _normalise_timing(merged)
    for k, v in merged.items():
        setattr(obj, k, v)
    if changes.get("recipient_user_ids") is not None:
        obj.recipient_user_ids = _validate_recipients(ctx, changes["recipient_user_ids"])
    if changes.get("active") is not None:
        obj.active = changes["active"]
    ctx.db.flush()
    ctx.db.refresh(obj)
    audit.record(
        ctx.db,
        ctx.user,
        "report_schedule.update",
        obj,
        before=before,
        after=audit.snapshot(obj),
    )
    return obj


def list_runs(ctx: Ctx, schedule_id: int, limit: int = 50) -> list[ReportScheduleRun]:
    get_schedule(ctx, schedule_id)
    stmt = (
        select(ReportScheduleRun)
        .where(ReportScheduleRun.schedule_id == schedule_id)
        .order_by(ReportScheduleRun.period_start.desc(), ReportScheduleRun.id.desc())
        .limit(limit)
    )
    return list(ctx.db.execute(stmt).scalars())


# ---- the worker job ---------------------------------------------------------------------
def due_period(schedule: ReportSchedule, today: date) -> tuple[date, date] | None:
    """The period to report on now, or None when the schedule is not due yet in this cycle."""
    if schedule.frequency == "weekly":
        if schedule.weekday is None or today.weekday() < schedule.weekday:
            return None
        monday = today - timedelta(days=today.weekday())
        return monday - timedelta(days=7), monday - timedelta(days=1)
    if schedule.frequency == "monthly":
        if schedule.day_of_month is None or today.day < schedule.day_of_month:
            return None
        last = today.replace(day=1) - timedelta(days=1)
        return last.replace(day=1), last
    return None


def _record(
    ctx: Ctx, sid: int, period: tuple[date, date], status: str, **cols
) -> ReportScheduleRun:
    run = ReportScheduleRun(
        schedule_id=sid, period_start=period[0], period_end=period[1], status=status, **cols
    )
    ctx.db.add(run)
    ctx.db.flush()
    return run


def _send_one(ctx: Ctx, schedule: ReportSchedule, period: tuple[date, date], today: date) -> str:
    """Queue the email for one schedule/period and record the run. Returns sent or skipped."""
    start, end = period
    users = ctx.db.execute(
        select(User).where(User.id.in_(schedule.recipient_user_ids)).order_by(User.id)
    ).scalars()
    emails: list[str] = []
    for u in users:
        if _eligible(u) and u.email.lower() not in {e.lower() for e in emails}:
            emails.append(u.email)
    if not emails:
        _record(
            ctx,
            schedule.id,
            period,
            "skipped",
            detail="No active recipient holds report:read any more",
        )
        return "skipped"
    all_ctx = Ctx(db=ctx.db, user=ctx.user, scope=Scope.all())
    filename, text = metrics.csv_for(all_ctx, schedule.report, start, end)
    subject = f"{schedule.name}: {start} to {end}"
    body = (
        f"{schedule.name}\nReport: {schedule.report}\n"
        + (f"As of {today}\n" if schedule.report == "aging" else f"Period: {start} to {end}\n")
        + f"The report is attached as {filename}.\n"
    )
    email = EmailMessage(
        direction="out",
        to_emails=emails,
        subject=subject[:998],
        body_text=body,
        send_status="pending",
        auto_generated=True,
    )
    ctx.db.add(email)
    ctx.db.flush()
    ctx.db.add(
        OutboundAttachment(
            email_message_id=email.id,
            filename=filename[:300],
            content_type="text/csv",
            data=text.encode("utf-8"),
        )
    )
    run = _record(ctx, schedule.id, period, "sent", recipients=emails, email_message_id=email.id)
    audit.record(
        ctx.db,
        ctx.user,
        "report_schedule.send",
        schedule,
        detail={"run_id": run.id, "to": emails, "attachment": filename, "subject": subject},
    )
    return "sent"


def run_due(ctx: Ctx, today: date) -> dict:
    """Email every active schedule that is due and has no run for its period. Safe to repeat."""
    counts = {"sent": 0, "skipped": 0, "failed": 0}
    stmt = (
        select(ReportSchedule)
        .where(ReportSchedule.active.is_(True))
        .order_by(ReportSchedule.id)
        .with_for_update(skip_locked=True)  # a second worker skips what the first is handling
    )
    for schedule in list(ctx.db.execute(stmt).scalars()):
        period = due_period(schedule, today)
        if period is None:
            continue
        sid = schedule.id
        done = ctx.db.execute(
            select(ReportScheduleRun.id).where(
                ReportScheduleRun.schedule_id == sid,
                ReportScheduleRun.period_start == period[0],
            )
        ).first()
        if done:
            continue
        try:
            with ctx.db.begin_nested():
                status = _send_one(ctx, schedule, period, today)
            counts[status] += 1
        except Exception as exc:
            log.exception("scheduled report %s failed", sid)
            try:
                with ctx.db.begin_nested():
                    _record(
                        ctx, sid, period, "failed", detail=f"{type(exc).__name__}: {exc}"[:2000]
                    )
                counts["failed"] += 1
            except IntegrityError:  # another worker recorded this period meanwhile
                pass
    return counts
