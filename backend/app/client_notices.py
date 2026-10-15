"""Client appointment emails (REQ-05).

Scheduling calls `queue` on every client-visible change; it keeps at most one pending row per
appointment and pushes its send_after out, so a burst of edits becomes a single email. The worker
calls `send_due`, which turns due rows into outbound email_messages (delivered by the mail
worker's send_pending in the same cycle) or into skipped rows with a reason. Appointment notes and
the cancel reason are never put in an email.
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import audit
from app.db import set_org_scope
from app.models import (
    Appointment,
    AppointmentNotice,
    EmailMessage,
    Settings,
    Ticket,
    User,
)
from app.scheduling_schemas import ClientNoticeOut

log = logging.getLogger("psa.client_notices")

DEBOUNCE = timedelta(minutes=2)
BATCH = 50


def queue(db: Session, appt: Appointment, settings: Settings, now: datetime) -> None:
    """Upsert the appointment's pending notice (debounced). Does nothing when emails are off or
    the appointment is hidden from, or muted for, the client."""
    if not (settings.appointment_emails_enabled and appt.client_visible and appt.notify_client):
        return
    stmt = insert(AppointmentNotice).values(
        organization_id=appt.organization_id,
        appointment_id=appt.id,
        state="pending",
        send_after=now + DEBOUNCE,
        starts_at=appt.starts_at,
        ends_at=appt.ends_at,
    )
    db.execute(
        stmt.on_conflict_do_update(
            index_elements=[AppointmentNotice.appointment_id],
            index_where=text("state = 'pending'"),  # literal: a bound value cannot match the index
            set_=dict(
                send_after=stmt.excluded.send_after,
                starts_at=stmt.excluded.starts_at,
                ends_at=stmt.excluded.ends_at,
            ),
        )
    )


def latest_for(db: Session, appointment_ids: list[int]) -> dict[int, ClientNoticeOut]:
    """The pending notice per appointment if any, else the newest one (one query)."""
    if not appointment_ids:
        return {}
    rows = db.execute(
        select(AppointmentNotice)
        .where(AppointmentNotice.appointment_id.in_(appointment_ids))
        .order_by(AppointmentNotice.id)
    ).scalars()
    best: dict[int, AppointmentNotice] = {}
    for n in rows:  # ascending id: a later row replaces an earlier one unless a pending is held
        cur = best.get(n.appointment_id)
        if cur is None or cur.state != "pending" or n.state == "pending":
            best[n.appointment_id] = n
    return {
        i: ClientNoticeOut(
            state=n.state,
            kind=n.kind,
            send_after=n.send_after,
            sent_at=n.sent_at,
            reason=n.reason,
        )
        for i, n in best.items()
    }


# ---- rendering --------------------------------------------------------------------------------
def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return ZoneInfo("UTC")


def _clock(d: datetime) -> str:
    return f"{d.hour % 12 or 12}:{d.minute:02d} {'AM' if d.hour < 12 else 'PM'}"


def _day(d: datetime) -> str:
    return f"{d:%A, %B} {d.day}, {d.year}"


def when(starts: datetime, ends: datetime, tz: ZoneInfo) -> str:
    """'Monday, January 7, 2030, 9:00 AM - 10:00 AM CST' in the business timezone."""
    s, e = starts.astimezone(tz), ends.astimezone(tz)
    zone = e.tzname() or tz.key
    if s.date() == e.date():
        return f"{_day(s)}, {_clock(s)} - {_clock(e)} {zone}"
    return f"{_day(s)}, {_clock(s)} - {_day(e)}, {_clock(e)} {zone}"


def _render(
    kind: str,
    ticket: Ticket,
    appt: Appointment,
    tech: User | None,
    settings: Settings,
    tz: ZoneInfo,
    previous: tuple[datetime, datetime] | None,
    portal: bool,
) -> tuple[str, str]:
    label = {"booked": "booked", "moved": "moved", "cancelled": "cancelled"}[kind]
    subject = f"[Ticket #{ticket.number}] Appointment {label}: {ticket.subject}"[:998]
    first = (tech.display_name.split() or [""])[0] if tech and tech.display_name else None
    lines = [
        {
            "booked": "An appointment has been booked for your support request.",
            "moved": "Your appointment has been moved.",
            "cancelled": "Your appointment has been cancelled.",
        }[kind],
        "",
    ]
    if kind == "moved" and previous:
        lines += [f"New time: {when(appt.starts_at, appt.ends_at, tz)}"]
        lines += [f"Previous time: {when(previous[0], previous[1], tz)}"]
    elif kind == "cancelled":
        lines += [f"Was scheduled for: {when(appt.starts_at, appt.ends_at, tz)}"]
    else:
        lines += [f"When: {when(appt.starts_at, appt.ends_at, tz)}"]
    if first and kind != "cancelled":
        lines += [f"Technician: {first}"]
    lines += [f"Ticket: #{ticket.number} - {ticket.subject}"]
    if portal:
        lines += ["", f"View your requests: {settings_url()}/portal"]
    lines += ["", "Reply to this email if you have questions."]
    return subject, "\n".join(lines) + "\n"


def settings_url() -> str:
    from app.config import get_settings

    return get_settings().public_url.rstrip("/")


# ---- sending ----------------------------------------------------------------------------------
def _decide(db: Session, n: AppointmentNotice, appt: Appointment | None, settings: Settings):
    """(kind, None, last_sent) to send, or (None, reason, last_sent) to skip."""
    if appt is None:
        return None, "appointment not found", None
    last = db.execute(
        select(AppointmentNotice)
        .where(AppointmentNotice.appointment_id == appt.id, AppointmentNotice.state == "sent")
        .order_by(AppointmentNotice.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if not settings.appointment_emails_enabled:
        return None, "appointment emails are turned off", last
    if not (appt.client_visible and appt.notify_client):
        return None, "appointment is hidden from or muted for the client", last
    if appt.status == "cancelled":
        if last is None:
            return None, "cancelled before any email", last
        return "cancelled", None, last
    if last is None:
        return "booked", None, last
    if (last.starts_at, last.ends_at) != (appt.starts_at, appt.ends_at):
        return "moved", None, last
    return None, "no client-visible change", last


def send_due(db: Session, now: datetime) -> int:
    """Process due pending notices; returns how many emails were queued. Commits."""
    set_org_scope(db, "all")
    due = (
        db.execute(
            select(AppointmentNotice)
            .where(AppointmentNotice.state == "pending", AppointmentNotice.send_after <= now)
            .order_by(AppointmentNotice.send_after, AppointmentNotice.id)
            .limit(BATCH)
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .all()
    )
    settings = db.get(Settings, 1)
    sent = 0
    for n in due:
        before = audit.snapshot(n)
        appt = db.get(Appointment, n.appointment_id)
        kind, reason, last = _decide(db, n, appt, settings)
        ticket = db.get(Ticket, appt.ticket_id) if appt else None
        to = None
        if kind is not None:
            if ticket is None:
                kind, reason = None, "ticket not found"
            else:
                contact = ticket.contact
                to = ((contact.email if contact else None) or "").strip() or (
                    (ticket.requester_email or "").strip() or None
                )
                if to is None:
                    kind, reason = None, "no recipient"
        if kind is None:
            n.state, n.reason = "skipped", reason
            db.flush()
            continue
        tech = db.get(User, appt.tech_id)
        portal = bool(settings.portal_enabled and contact is not None and contact.portal_access)
        subject, body = _render(
            kind,
            ticket,
            appt,
            tech,
            settings,
            _zone(settings.timezone),
            (last.starts_at, last.ends_at) if last else None,
            portal,
        )
        email = EmailMessage(
            direction="out",
            ticket_id=ticket.id,
            organization_id=appt.organization_id,
            to_emails=[to],
            subject=subject,
            body_text=body,
            send_status="pending",
            auto_generated=True,
        )
        db.add(email)
        db.flush()
        n.state, n.kind, n.reason = "sent", kind, None
        n.email_message_id, n.sent_at = email.id, now
        n.starts_at, n.ends_at = appt.starts_at, appt.ends_at
        db.flush()
        audit.record(
            db,
            None,
            "appointment_notice.send",
            n,
            before=before,
            after=audit.snapshot(n),
            organization_id=appt.organization_id,
            detail={"to": [to], "kind": kind, "ticket_id": ticket.id},
        )
        sent += 1
    db.commit()
    return sent
