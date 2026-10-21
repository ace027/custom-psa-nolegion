"""Renewal reminders: each agreement with an end date gets one reminder per configured lead time
(settings.renewal_reminder_days), the first of which also opens a renewal opportunity. Created once
each (UNIQUE agreement_id + lead_days), so a dismissed reminder is never recreated."""

import logging
from datetime import date, timedelta

from sqlalchemy import exists, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from app import audit, crm
from app import repositories as repo
from app.billing import monthly_amount_cents
from app.config import get_settings
from app.deps import Ctx
from app.errors import Conflict, NotFound
from app.models import (
    Agreement,
    EmailMessage,
    Opportunity,
    OpportunityStage,
    RenewalReminder,
)

log = logging.getLogger(__name__)


def _line(text: str | None) -> str:
    return " ".join((text or "").split())[:200]


def _latest_renewal(ctx: Ctx, agreement_id: int) -> tuple[Opportunity, str] | None:
    """The newest renewal opportunity of the agreement in any stage, with its stage kind."""
    row = ctx.db.execute(
        select(Opportunity, OpportunityStage.kind)
        .join(OpportunityStage, OpportunityStage.id == Opportunity.stage_id)
        .where(Opportunity.kind == "renewal", Opportunity.agreement_id == agreement_id)
        .order_by(Opportunity.id.desc())
        .limit(1)
    ).first()
    return (row[0], row[1]) if row else None


def _compose(a: Agreement) -> tuple[str, str]:
    client = _line(a.organization.name)
    name = _line(a.name)
    end = a.end_date.isoformat()
    url = f"{get_settings().public_url.rstrip('/')}/crm/renewals"
    subject = f"PSA: agreement {name} for {client} ends {end}"
    body = "\n".join(
        [
            f"Agreement {name} is coming up for renewal.",
            "",
            f"Client:    {client}",
            f"Agreement: {name}",
            f"Ends:      {end}",
            "",
            f"Open the renewals list: {url}",
        ]
    )
    return subject, body


def _insert(ctx: Ctx, a: Agreement, lead_days: int) -> RenewalReminder | None:
    try:
        with ctx.db.begin_nested():  # a duplicate must not poison the job's transaction
            reminder = RenewalReminder(
                organization_id=a.organization_id,
                agreement_id=a.id,
                lead_days=lead_days,
                due_on=a.end_date,
                status="open",
            )
            ctx.db.add(reminder)
            ctx.db.flush()
    except IntegrityError:
        return None
    return reminder


def _process(ctx, a, today, days, settings, can_mail, counts) -> None:
    _follow_end_date(ctx, a)
    fresh = []
    for n in days:
        if today >= a.end_date - timedelta(days=n):
            reminder = _insert(ctx, a, n)
            if reminder is not None:
                fresh.append(reminder)
    if not fresh:
        return
    counts["reminders"] += len(fresh)
    latest = _latest_renewal(ctx, a.id)
    opp, closed = (latest[0], latest[1] != "open") if latest else (None, False)
    if opp is None:
        opp = crm.create_opportunity(
            ctx,
            {
                "organization_id": a.organization_id,
                "name": f"Renewal: {_line(a.name)}",
                "kind": "renewal",
                "monthly_cents": monthly_amount_cents(a),
                "term_months": 12,
                "expected_close_date": a.end_date,
                "agreement_id": a.id,
            },
        )
        counts["opportunities"] += 1
    for reminder in fresh:
        reminder.opportunity_id = opp.id
        if closed:  # the renewal is already won or lost: nothing to chase, nothing to email
            reminder.status = "done"
            counts["done"] += 1
            continue
        if can_mail:
            subject, body = _compose(a)
            email = EmailMessage(
                direction="out",
                organization_id=a.organization_id,
                to_emails=[settings.renewal_email],
                subject=subject,
                body_text=body,
                send_status="pending",
                auto_generated=True,
            )
            ctx.db.add(email)
            ctx.db.flush()
            reminder.email_message_id = email.id
            counts["emails"] += 1
    ctx.db.flush()


def _follow_end_date(ctx: Ctx, a: Agreement) -> None:
    """The agreement's end date moved after reminders were made: move the open reminders, the open
    renewal opportunity's expected close date, and rewrite any reminder email still waiting to be
    sent (an email already sent or failed is left alone)."""
    stale = (
        ctx.db.execute(
            select(RenewalReminder).where(
                RenewalReminder.agreement_id == a.id,
                RenewalReminder.status == "open",
                RenewalReminder.due_on != a.end_date,
            )
        )
        .scalars()
        .all()
    )
    if not stale:
        return
    subject, body = _compose(a)
    for reminder in stale:
        reminder.due_on = a.end_date
        if reminder.email_message_id is not None:
            mail = ctx.db.get(EmailMessage, reminder.email_message_id)
            if mail is not None and mail.send_status == "pending":
                mail.subject = subject
                mail.body_text = body
    latest = _latest_renewal(ctx, a.id)
    if latest is not None and latest[1] == "open":
        latest[0].expected_close_date = a.end_date
    ctx.db.flush()


def scan(ctx: Ctx, today: date) -> dict:
    """Create the reminders that have come due, plus their renewal opportunity and optional email.
    Idempotent. -> counts of reminders, opportunities, emails and reminders marked done."""
    counts = {"reminders": 0, "opportunities": 0, "emails": 0, "done": 0, "errors": 0}
    settings = repo.get_settings_row(ctx.db)
    days = sorted(set(settings.renewal_reminder_days or []), reverse=True)
    can_mail = bool(settings.renewal_email) and repo.get_mailbox_status(ctx.db).mailbox is not None
    # A reprice ends the old agreement the day before its successor starts; that is not a renewal.
    successor = aliased(Agreement)
    replaced = exists().where(
        successor.organization_id == Agreement.organization_id,
        successor.id != Agreement.id,
        successor.start_date == Agreement.end_date + 1,
    )
    agreements = (
        ctx.db.execute(
            select(Agreement)
            .where(Agreement.end_date.is_not(None), Agreement.end_date >= today, ~replaced)
            .order_by(Agreement.id)
        )
        .unique()
        .scalars()
    )
    for a in list(agreements):
        part = {"reminders": 0, "opportunities": 0, "emails": 0, "done": 0}
        agreement_id = a.id
        try:
            with ctx.db.begin_nested():  # one bad agreement must not undo the others' reminders
                _process(ctx, a, today, days, settings, can_mail, part)
        except (Conflict, IntegrityError) as exc:
            log.warning("renewal reminder for agreement %s skipped: %s", agreement_id, exc)
            counts["errors"] += 1
            continue
        for key, n in part.items():
            counts[key] += n

    closed = (
        select(Opportunity.id)
        .join(OpportunityStage, OpportunityStage.id == Opportunity.stage_id)
        .where(OpportunityStage.kind.in_(("won", "lost")))
    )
    result = ctx.db.execute(
        update(RenewalReminder)
        .where(RenewalReminder.status == "open", RenewalReminder.opportunity_id.in_(closed))
        .values(status="done")
    )
    counts["done"] += result.rowcount or 0
    return counts


def list_reminders(ctx: Ctx, status: str | None = None) -> list[dict]:
    stmt = ctx.scope.apply(
        select(RenewalReminder, Agreement)
        .join(Agreement, Agreement.id == RenewalReminder.agreement_id)
        .order_by(RenewalReminder.due_on, RenewalReminder.lead_days.desc(), RenewalReminder.id),
        RenewalReminder.organization_id,
    )
    if status:
        stmt = stmt.where(RenewalReminder.status == status)
    return [
        {
            "id": r.id,
            "organization_id": r.organization_id,
            "organization_name": a.organization.name,
            "agreement_id": r.agreement_id,
            "agreement_name": a.name,
            "lead_days": r.lead_days,
            "due_on": r.due_on,
            "status": r.status,
            "opportunity_id": r.opportunity_id,
            "created_at": r.created_at,
        }
        for r, a in ctx.db.execute(stmt).unique().all()
    ]


def dismiss(ctx: Ctx, reminder_id: int) -> dict:
    reminder = ctx.db.execute(
        ctx.scope.apply(
            select(RenewalReminder).where(RenewalReminder.id == reminder_id),
            RenewalReminder.organization_id,
        ).with_for_update()
    ).scalar_one_or_none()
    if reminder is None:
        raise NotFound("Reminder not found")
    if reminder.status != "open":
        raise Conflict(f"This reminder is already {reminder.status}")
    before = audit.snapshot(reminder)
    reminder.status = "dismissed"
    ctx.db.flush()
    audit.record(
        ctx.db,
        ctx.user,
        "renewal_reminder.dismiss",
        reminder,
        before=before,
        after=audit.snapshot(reminder),
        organization_id=reminder.organization_id,
    )
    return next(r for r in list_reminders(ctx) if r["id"] == reminder.id)
