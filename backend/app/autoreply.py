"""Automatic acknowledgement of tickets created from email.

Loop and backscatter protection, all of it enforced here or upstream in mail.ingest:
- off by default; needs the mailbox configured
- never for automated senders (ingest drops those before a ticket exists) or our own mailbox
- only when the sender is a KNOWN client (matched contact or domain): a spoofed From on an
  unknown address would otherwise make us a spam relay
- once per ticket (unique row) and at most MAX_PER_SENDER_PER_DAY per address per 24 hours
- carries X-Auto-Response-Suppress / X-PSA-Auto-Reply headers (Graph only allows x- headers),
  which our own inbound filter also treats as automated
The subject keeps the [#number] token so the customer's reply threads onto the ticket."""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import repositories as repo
from app.deps import Ctx
from app.models import EmailMessage, Ticket, TicketAutoAck
from app.notices import render
from app.ticket_services import now

ACK_PLACEHOLDERS = {"ticket_number", "contact_name", "company", "subject"}
MAX_PER_SENDER_PER_DAY = 3
AUTO_HEADERS = {"X-Auto-Response-Suppress": "All", "X-PSA-Auto-Reply": "ack"}


def maybe_acknowledge(ctx: Ctx, ticket: Ticket, sender: str, mailbox: str) -> bool:
    """Queue one acknowledgement. Returns False when skipped for any reason."""
    settings = repo.get_settings_row(ctx.db)
    sender = (sender or "").strip().lower()
    if not settings.auto_ack_enabled or not sender or sender == mailbox.lower():
        return False
    if ticket.organization_id is None:  # unknown sender: no backscatter
        return False
    since = now() - timedelta(hours=24)
    recent = ctx.db.execute(
        select(func.count())
        .select_from(TicketAutoAck)
        .where(TicketAutoAck.sent_to == sender, TicketAutoAck.created_at > since)
    ).scalar_one()
    if recent >= MAX_PER_SENDER_PER_DAY:
        return False
    values = {
        "ticket_number": ticket.number,
        "contact_name": ticket.contact.name if ticket.contact else "there",
        "company": settings.company_name or "us",
        "subject": " ".join((ticket.subject or "").split())[:200],
    }
    subject = render(settings.auto_ack_subject, values)
    if f"[#{ticket.number}]" not in subject:
        subject = f"[#{ticket.number}] {subject}"  # replies must thread
    try:
        with ctx.db.begin_nested():  # a duplicate must not poison the caller's transaction
            email = EmailMessage(
                direction="out",
                ticket_id=ticket.id,
                organization_id=ticket.organization_id,
                to_emails=[sender],
                subject=subject[:998],
                body_text=render(settings.auto_ack_body, values),
                send_status="pending",
                auto_generated=True,
            )
            ctx.db.add(email)
            ctx.db.flush()
            ctx.db.add(
                TicketAutoAck(ticket_id=ticket.id, sent_to=sender, email_message_id=email.id)
            )
            ctx.db.flush()
    except IntegrityError:
        return False
    return True
