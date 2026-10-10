"""One-way push of appointments to the assigned tech's Outlook calendar.

The API only calls `enqueue` (an outbox row in the same transaction as the appointment write).
The worker calls `push_pending`. A claimed row is leased (next_attempt_at moves forward) and its
lock is released before any Graph call, so appointment writes never wait on Graph. The result is
written under a fresh row lock; if desired_version moved meanwhile the row stays pending and is
pushed again. Creates carry a deterministic transaction id so a retry cannot duplicate an event.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import set_org_scope
from app.mail.graph import GraphError, event_payload
from app.models import Appointment, AppointmentSync, Settings, User

log = logging.getLogger("psa.calendar")

LEASE = timedelta(minutes=10)
MAX_ATTEMPTS = 6
SKIP_AFTER = timedelta(days=1)
NO_EMAIL = "Tech has no email address"


def enqueue(db: Session, appointment: Appointment) -> None:
    """Mark the appointment as needing a push (insert the sync row, or bump its version)."""
    t = AppointmentSync.__table__.c
    stmt = insert(AppointmentSync).values(
        appointment_id=appointment.id, organization_id=appointment.organization_id
    )
    db.execute(
        stmt.on_conflict_do_update(
            index_elements=[t.appointment_id],
            set_=dict(
                organization_id=stmt.excluded.organization_id,
                desired_version=t.desired_version + 1,
                state="pending",
                attempts=0,
                next_attempt_at=func.now(),
                last_error=None,
                updated_at=func.now(),
            ),
        )
    )


@dataclass
class _Work:
    """Event state while one row is pushed; saved even when the push fails half way."""

    event_id: str | None
    tech_id: int | None
    generation: int


def _email(db: Session, user_id: int | None) -> str | None:
    user = db.get(User, user_id) if user_id is not None else None
    return ((user.email if user else None) or "").strip() or None


def _push(db: Session, client, appt: Appointment, work: _Work, version_zero: bool, now: datetime):
    """Bring Outlook in line with the appointment. Returns the final state ('synced'/'skipped')."""
    if version_zero and work.event_id is None and appt.ends_at < now - SKIP_AFTER:
        return "skipped"
    if appt.status == "cancelled":
        if work.event_id:
            old = _email(db, work.tech_id)
            if old is None:
                raise GraphError(NO_EMAIL)
            client.delete_event(old, work.event_id)
        work.event_id, work.tech_id = None, None
        return "synced"
    email = _email(db, appt.tech_id)
    if email is None:
        raise GraphError(NO_EMAIL)
    if work.tech_id is not None and work.tech_id != appt.tech_id:
        if work.event_id:
            old = _email(db, work.tech_id)
            if old is None:
                raise GraphError(NO_EMAIL)
            client.delete_event(old, work.event_id)
        work.event_id, work.tech_id = None, None
        work.generation += 1
    payload = event_payload(appt.ticket_id, appt.starts_at, appt.ends_at, get_settings().public_url)
    if work.event_id is not None:
        try:
            client.update_event(email, work.event_id, payload)
            return "synced"
        except GraphError as e:
            if e.status != 404:
                raise
        work.event_id, work.tech_id = None, None  # deleted in Outlook by hand: start over
        work.generation += 1
    txn = f"psa-appt-{appt.id}-{appt.tech_id}-{work.generation}"
    work.event_id = client.create_event(email, payload, txn)
    work.tech_id = appt.tech_id
    return "synced"


def _finish(
    db: Session,
    appointment_id: int,
    work: _Work,
    version: int,
    now: datetime,
    state: str | None,
    error: GraphError | None,
) -> None:
    set_org_scope(db, "all")
    row = db.execute(
        select(AppointmentSync)
        .where(AppointmentSync.appointment_id == appointment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one()
    row.graph_event_id, row.synced_tech_id, row.generation = (
        work.event_id,
        work.tech_id,
        work.generation,
    )
    row.updated_at = now
    if row.desired_version != version:
        # written to while pushing: enqueue already reset state/attempts/next_attempt_at
        if error is None:
            row.synced_version = version
    elif error is None:
        row.synced_version = version
        row.state = state or "synced"
        row.attempts = 0
        row.last_error = None
    else:
        row.attempts += 1
        row.last_error = str(error)[:500]
        if not error.transient or row.attempts >= MAX_ATTEMPTS:
            row.state = "failed"
        else:
            row.next_attempt_at = now + timedelta(minutes=min(2**row.attempts, 60))
    db.commit()
    if error is not None:
        log.warning("outlook push failed for appointment %s: %s", appointment_id, row.last_error)
    else:
        log.info("outlook push %s for appointment %s (v%s)", row.state, appointment_id, version)


def push_pending(db: Session, client, *, now: datetime, batch: int = 20) -> int:
    """Push due outbox rows to Outlook; returns how many rows were processed."""
    set_org_scope(db, "all")  # transaction-local, so it is set again after every commit
    settings = db.get(Settings, 1)
    if settings is None or not settings.outlook_sync_enabled:
        db.rollback()
        return 0
    claimed = list(
        db.execute(
            select(AppointmentSync)
            .where(AppointmentSync.state == "pending", AppointmentSync.next_attempt_at <= now)
            .order_by(AppointmentSync.next_attempt_at)
            .limit(batch)
            .with_for_update(skip_locked=True)
        ).scalars()
    )
    for row in claimed:
        row.next_attempt_at = now + LEASE  # lease: other workers skip it, a crash retries later
    db.commit()
    ids = [r.appointment_id for r in claimed]
    for appointment_id in ids:
        set_org_scope(db, "all")
        row = db.execute(
            select(AppointmentSync)
            .where(AppointmentSync.appointment_id == appointment_id)
            .execution_options(populate_existing=True)
        ).scalar_one()
        version = row.desired_version
        work = _Work(row.graph_event_id, row.synced_tech_id, row.generation)
        never_synced = row.synced_version == 0
        appt = db.get(Appointment, appointment_id, populate_existing=True)
        db.expunge(appt)
        db.rollback()  # end the read transaction before talking to Graph
        set_org_scope(db, "all")
        state, error = None, None
        try:
            state = _push(db, client, appt, work, never_synced, now)
        except GraphError as e:
            error = e
        except Exception as e:  # never let one bad row stop the batch
            log.exception("unexpected error pushing appointment %s", appointment_id)
            error = GraphError(f"{type(e).__name__}: {e}", None, True)
        _finish(db, appointment_id, work, version, now, state, error)
    return len(ids)
