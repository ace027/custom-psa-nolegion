"""Email notifications to staff. Only the ticket's assignee is told, only about their own tickets:
assigned to them, SLA at risk / breached, and a customer replying. Messages carry facts and a link,
never the ticket text or the customer's words. They use the normal outbox, so they need the mailbox
to be configured (otherwise nothing is queued, so there is no backlog to flush later).

Notification subjects deliberately contain no `[#12345]` token: a reply to one must not be mistaken
for a customer reply on that ticket."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import repositories as repo
from app.config import get_settings
from app.deps import Ctx
from app.models import EmailMessage, Priority, StaffNotification, Ticket, TicketEscalation, User
from app.sla import sla_state
from app.ticket_services import calendar, now

PREFERENCE = {
    "assigned": "notify_assigned",
    "sla_at_risk": "notify_sla",
    "sla_breached": "notify_sla",
    "customer_reply": "notify_reply",
}
HEADLINE = {
    "assigned": "was assigned to you",
    "sla_at_risk": "is at risk of breaching its SLA",
    "sla_breached": "has breached its SLA",
    "customer_reply": "has a new reply from the customer",
}


def _line(text: str | None) -> str:
    return " ".join((text or "").split())[:200]


def compose(ticket: Ticket, event: str) -> tuple[str, str]:
    url = f"{get_settings().public_url.rstrip('/')}/tickets/{ticket.id}"
    subject = f"PSA: ticket #{ticket.number} {HEADLINE[event]}"
    due = ticket.sla_resolution_due
    client = _line(ticket.organization.name) if ticket.organization else "not yet matched"
    lines = [
        f"Ticket #{ticket.number} {HEADLINE[event]}.",
        "",
        f"Subject:  {_line(ticket.subject)}",
        f"Client:   {client}",
        f"Priority: {ticket.priority.name}",
        f"Status:   {ticket.status}",
    ]
    if due:
        lines.append(f"Resolution due: {due.strftime('%Y-%m-%d %H:%M UTC')}")
    lines += ["", f"Open it: {url}", "", "You can turn these emails off under your profile."]
    return subject, "\n".join(lines)


def notify(
    ctx: Ctx, user_id: int | None, ticket: Ticket, event: str, key: str, actor: User | None = None
) -> bool:
    """Queue one email. Returns False when skipped (off, not configured, self, duplicate)."""
    if user_id is None or (actor is not None and actor.id == user_id):
        return False
    settings = repo.get_settings_row(ctx.db)
    if not settings.notify_staff or repo.get_mailbox_status(ctx.db).mailbox is None:
        return False
    user = repo.get_user(ctx.db, user_id)
    if user is None or not user.is_active or not getattr(user, PREFERENCE[event]):
        return False
    subject, body = compose(ticket, event)
    try:
        with ctx.db.begin_nested():  # a duplicate must not poison the caller's transaction
            email = EmailMessage(
                direction="out",
                organization_id=ticket.organization_id,  # row-level security applies to it
                to_emails=[user.email],
                subject=subject,
                body_text=body,
                send_status="pending",
            )
            ctx.db.add(email)
            ctx.db.flush()
            ctx.db.add(
                StaffNotification(
                    user_id=user.id,
                    ticket_id=ticket.id,
                    event=event,
                    dedupe_key=key,
                    email_message_id=email.id,
                )
            )
            ctx.db.flush()
    except IntegrityError:
        return False
    return True


def scan_sla(ctx: Ctx) -> int:
    """Tell assignees about tickets that reached at-risk or breached (once per state)."""
    settings = repo.get_settings_row(ctx.db)
    cal, t = calendar(ctx), now()
    tickets = (
        ctx.db.execute(
            select(Ticket).where(
                Ticket.assignee_id.is_not(None), Ticket.status.notin_(("resolved", "closed"))
            )
        )
        .unique()
        .scalars()
    )
    sent = 0
    for ticket in tickets:
        state = sla_state(ticket, cal, settings.sla_at_risk_percent, t)
        if state in ("at_risk", "breached"):
            sent += notify(ctx, ticket.assignee_id, ticket, f"sla_{state}", state)
    return sent + scan_escalations(ctx)


def scan_escalations(ctx: Ctx) -> int:
    """Once per ticket that has breached its SLA: email the configured escalation address and,
    if switched on, raise the priority one step. Off until an address or the bump is configured."""
    settings = repo.get_settings_row(ctx.db)
    to = settings.escalation_email
    if not to and not settings.escalation_bump_priority:
        return 0
    can_mail = bool(to) and repo.get_mailbox_status(ctx.db).mailbox is not None
    if not can_mail and not settings.escalation_bump_priority:
        return 0
    cal, t = calendar(ctx), now()
    done = select(TicketEscalation.ticket_id)
    tickets = (
        ctx.db.execute(
            select(Ticket).where(
                Ticket.status.notin_(("resolved", "closed")), Ticket.id.notin_(done)
            )
        )
        .unique()
        .scalars()
    )
    escalated = 0
    for ticket in list(tickets):
        if sla_state(ticket, cal, settings.sla_at_risk_percent, t) != "breached":
            continue
        email_id = bumped_from = None
        if can_mail:
            subject, body = compose(ticket, "sla_breached")
            email = EmailMessage(
                direction="out",
                organization_id=ticket.organization_id,
                to_emails=[to],
                subject=f"PSA escalation: ticket #{ticket.number} has breached its SLA",
                body_text=body.replace("\n\nYou can turn these emails off under your profile.", "")
                + "\n\nThis escalation was sent to the address set under Settings.",
                send_status="pending",
                auto_generated=True,
            )
            ctx.db.add(email)
            ctx.db.flush()
            email_id = email.id
        if settings.escalation_bump_priority:
            higher = ctx.db.execute(
                select(Priority)
                .where(Priority.archived_at.is_(None), Priority.rank < ticket.priority.rank)
                .order_by(Priority.rank.desc())
                .limit(1)
            ).scalar_one_or_none()
            if higher is not None:
                bumped_from = ticket.priority_id
                from app.ticket_services import update_ticket

                update_ticket(ctx, ticket.id, {"priority_id": higher.id})
        ctx.db.add(
            TicketEscalation(
                ticket_id=ticket.id, email_message_id=email_id, bumped_from_priority_id=bumped_from
            )
        )
        ctx.db.flush()
        escalated += 1
    return escalated
