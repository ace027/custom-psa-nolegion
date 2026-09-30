"""Inbound mail -> tickets (threading, sender matching, loop protection) and the outbound queue."""

import hashlib
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app import db as dbmod
from app import repositories as repo
from app import ticket_services as tsvc
from app.config import get_settings
from app.deps import Ctx
from app.mail.graph import InboundMessage, MailClient
from app.models import Attachment, EmailMessage, MailboxStatus, OutboundAttachment
from app.scope import Scope

log = logging.getLogger("psa.mail")

TOKEN_RE = re.compile(r"\[#(\d{4,12})\]")
FREEMAIL = {
    "gmail.com",
    "googlemail.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "msn.com",
    "yahoo.com",
    "icloud.com",
    "me.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
}
AUTO_SUBJECT = re.compile(
    r"^\s*(automatic reply|auto:|autoreply|undeliverable|delivery status)", re.I
)
MAX_SEND_ATTEMPTS = 5

_QUOTE_MARKERS = [
    re.compile(r"^[ \t]*On\s.{5,250}?wrote:", re.I | re.M | re.S),
    re.compile(r"^[ \t]*-{2,}\s*Original Message\s*-{2,}", re.I | re.M),
    re.compile(r"^[ \t]*_{10,}[ \t]*$", re.M),
    re.compile(r"^[ \t]*From:[ \t].+\r?\n[ \t]*(Sent|Date):", re.I | re.M),
    re.compile(r"^[ \t]*>", re.M),
]


def strip_quoted(text: str) -> str:
    """Drop quoted reply history. If nothing would be left, keep everything."""
    cut = min((m.start() for p in _QUOTE_MARKERS if (m := p.search(text))), default=None)
    trimmed = text[:cut].rstrip() if cut is not None else text.strip()
    return trimmed or text.strip()


def automated_reason(msg: InboundMessage, mailbox: str) -> str | None:
    """Why this message must NOT create or update a ticket (prevents mail loops)."""
    sender = (msg.from_email or "").lower()
    h = msg.headers
    if not sender:
        return "no_sender"
    if sender == mailbox.lower():
        return "from_self"
    if sender.split("@")[0] in (
        "mailer-daemon",
        "postmaster",
        "no-reply",
        "noreply",
        "do-not-reply",
    ):
        return "system_sender"
    if h.get("auto-submitted", "no").strip().lower() != "no":
        return "auto_submitted"
    if "x-auto-response-suppress" in h or "x-autoreply" in h or "x-autorespond" in h:
        return "auto_response"
    if h.get("precedence", "").strip().lower() in ("bulk", "junk", "list", "auto_reply"):
        return "bulk_precedence"
    if AUTO_SUBJECT.match(msg.subject):
        return "auto_subject"
    return None


def _ctx(db: Session) -> Ctx:
    return Ctx(db=db, user=None, scope=Scope.all())


def _sender_allowed_on(ctx: Ctx, ticket, sender: str) -> bool:
    """Only people we already associate with the ticket may append to it by email. Anyone can
    guess a ticket number, so the token alone is never enough."""
    if ticket.requester_email and ticket.requester_email.lower() == sender:
        return True
    if ticket.contact and (ticket.contact.email or "").lower() == sender:
        return True
    if ticket.organization_id is None:
        return False
    return any(
        c.organization_id == ticket.organization_id for c in repo.contacts_by_email(ctx.db, sender)
    )


def _find_ticket(ctx: Ctx, msg: InboundMessage):
    m = TOKEN_RE.search(msg.subject)
    if m:
        t = repo.get_ticket_by_number(ctx.db, ctx.scope, int(m.group(1)))
        if t:
            return t, f"subject token #{m.group(1)}"
    ids = re.findall(
        r"<[^>]+>", msg.headers.get("in-reply-to", "") + " " + msg.headers.get("references", "")
    )
    tid = repo.find_ticket_by_internet_message_ids(ctx.db, ids)
    if tid:
        t = repo.get_ticket(ctx.db, ctx.scope, tid)
        if t:
            return t, "thread headers"
    return None, None


def _match_sender(ctx: Ctx, sender: str):
    """-> (organization_id, contact_id, note). Ambiguity is never guessed: it goes to triage."""
    contacts = repo.contacts_by_email(ctx.db, sender)
    if len(contacts) == 1:
        return contacts[0].organization_id, contacts[0].id, "matched contact"
    if len(contacts) > 1:
        return None, None, "sender email exists on several contacts/organizations"
    domain = sender.rsplit("@", 1)[-1]
    if domain not in FREEMAIL:
        orgs = repo.orgs_by_email_domain(ctx.db, domain)
        if len(orgs) == 1:
            return orgs[0], None, "matched organization by email domain"
    return None, None, "unknown sender"


def _store_attachments(ctx: Ctx, client: MailClient, msg, email, ticket) -> list[Path]:
    settings = get_settings()
    written: list[Path] = []
    base = Path(settings.attachments_dir)
    for att in client.get_attachments(msg.id, settings.max_attachment_bytes):
        key = f"{ticket.id}/{uuid.uuid4().hex}"
        path = base / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(att.content)
        written.append(path)
        ctx.db.add(
            Attachment(
                email_message_id=email.id,
                ticket_id=ticket.id,
                organization_id=ticket.organization_id,
                filename=att.name[:300],
                content_type=att.content_type,
                size_bytes=att.size,
                sha256=hashlib.sha256(att.content).hexdigest(),
                storage_key=key,
            )
        )
    return written


def process_message(db: Session, client: MailClient, msg: InboundMessage, mailbox: str) -> str:
    """Ingest one message inside the caller's transaction. Returns what happened."""
    dbmod.set_org_scope(db, "all")  # FIRST: with RLS, an unscoped duplicate check sees nothing
    if db.execute(select(EmailMessage.id).where(EmailMessage.graph_message_id == msg.id)).first():
        return "duplicate"
    ctx = _ctx(db)

    def record(status: str, detail: str | None = None, ticket=None) -> EmailMessage:
        e = EmailMessage(
            direction="in",
            graph_message_id=msg.id,
            internet_message_id=msg.internet_message_id,
            in_reply_to=(msg.headers.get("in-reply-to") or None),
            conversation_id=msg.conversation_id,
            from_email=msg.from_email,
            to_emails=msg.to_emails,
            subject=msg.subject[:998],
            body_text=msg.body_text,
            received_at=msg.received_at,
            ingest_status=status,
            ingest_detail=detail,
            ticket_id=ticket.id if ticket else None,
            organization_id=ticket.organization_id if ticket else None,
        )
        db.add(e)
        db.flush()
        return e

    reason = automated_reason(msg, mailbox)
    if reason:
        record("ignored", reason)
        return f"ignored:{reason}"

    sender = msg.from_email
    body = strip_quoted(msg.body_text)[:100_000]
    ticket, how = _find_ticket(ctx, msg)
    written: list[Path] = []
    try:
        if ticket and _sender_allowed_on(ctx, ticket, sender):
            email = record("appended", f"matched by {how}", ticket)
            tsvc.customer_reply(ctx, ticket, body, sender, email)
            written = (
                _store_attachments(ctx, client, msg, email, ticket) if msg.has_attachments else []
            )
            outcome = "appended"
        else:
            org_id, contact_id, note = _match_sender(ctx, sender)
            description = body
            if ticket:  # token/thread pointed at a ticket, but this sender is a stranger to it
                description = (
                    f"[Possible reply to ticket #{ticket.number} from an unrecognized "
                    f"sender; not attached automatically.]\n\n{body}"
                )
            new = tsvc.create_ticket(
                ctx,
                {
                    "organization_id": org_id,
                    "contact_id": contact_id,
                    "subject": (msg.subject or "(no subject)").strip()[:300],
                    "description": description,
                },
                source="email",
                requester_email=sender,
            )
            email = record("ticket_created", note, new)
            written = (
                _store_attachments(ctx, client, msg, email, new) if msg.has_attachments else []
            )
            outcome = "ticket_created"
        db.flush()
    except BaseException:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return outcome


def poll_once(client: MailClient, mailbox: str, max_batches: int = 4) -> dict[str, int]:
    """One polling cycle: ingest unread mail, mark each as read AFTER it is committed."""
    stats: dict[str, int] = {}
    seen: set[str] = set()
    for _ in range(max_batches):
        batch = [m for m in client.list_unread() if m.id not in seen]
        if not batch:
            break
        for msg in batch:
            seen.add(msg.id)
            with dbmod.new_session() as db:
                try:
                    outcome = process_message(db, client, msg, mailbox)
                    db.commit()
                except Exception:
                    db.rollback()
                    log.exception("failed to ingest message %s", msg.id)
                    stats["failed"] = stats.get("failed", 0) + 1
                    continue
            stats[outcome.split(":")[0]] = stats.get(outcome.split(":")[0], 0) + 1
            try:
                client.mark_read(msg.id)
            except Exception:
                # harmless: the graph id is stored, so the next poll skips it as a duplicate
                log.warning("could not mark message %s as read", msg.id, exc_info=True)
    return stats


def send_pending(client: MailClient, mailbox: str, batch: int = 20) -> dict[str, int]:
    """Send queued outbound mail. Failed sends retry on later cycles, then are marked failed."""
    stats = {"sent": 0, "failed": 0, "retry": 0}
    with dbmod.new_session() as db:
        dbmod.set_org_scope(db, "all")
        rows = (
            db.execute(
                select(EmailMessage)
                .where(EmailMessage.direction == "out", EmailMessage.send_status == "pending")
                .order_by(EmailMessage.id)
                .limit(batch)
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )
        for e in rows:
            e.send_attempts += 1
            try:
                if not e.to_emails:
                    raise ValueError("no recipients")
                attachments = [
                    (a.filename, a.content_type, a.data)
                    for a in db.execute(
                        select(OutboundAttachment)
                        .where(OutboundAttachment.email_message_id == e.id)
                        .order_by(OutboundAttachment.id)
                    ).scalars()
                ]
                client.send_mail(
                    e.to_emails, e.subject or "", e.body_text or "", attachments or None
                )
                e.send_status, e.sent_at, e.send_error = "sent", datetime.now(UTC), None
                e.from_email = mailbox
                stats["sent"] += 1
            except Exception as exc:
                e.send_error = str(exc)[:1000]
                if e.send_attempts >= MAX_SEND_ATTEMPTS:
                    e.send_status = "failed"
                    audit.record(
                        db,
                        None,
                        "email.send_failed",
                        e,
                        organization_id=e.organization_id,
                        detail={"ticket_id": e.ticket_id, "error": e.send_error},
                    )
                    stats["failed"] += 1
                else:
                    stats["retry"] += 1
        db.commit()
    return stats


def run_cycle(client: MailClient, mailbox: str) -> None:
    """Poll + send, and record health for the admin status page."""
    now = datetime.now(UTC)
    error = None
    try:
        ingest = poll_once(client, mailbox)
        send_pending(client, mailbox)
    except Exception as exc:  # network/auth problems: log, record, keep the worker alive
        log.exception("mail cycle failed")
        error, ingest = str(exc)[:1000], {}
    with dbmod.new_session() as db:
        st = db.get(MailboxStatus, 1)
        st.mailbox, st.worker_seen_at = mailbox, now
        st.last_poll_at = now
        if error is None and not ingest.get("failed"):
            st.last_success_at, st.last_error = now, None
        else:
            st.last_error = error or f"{ingest['failed']} message(s) could not be ingested"
            st.last_error_at = now
        st.messages_ingested += sum(
            v
            for k, v in ingest.items()
            if k in ("ticket_created", "ticket_created_unmatched", "appended")
        )
        db.commit()


def heartbeat(mailbox: str | None) -> None:
    """Tell the admin page the worker is alive (and whether mail is configured)."""
    with dbmod.new_session() as db:
        st = db.get(MailboxStatus, 1)
        st.mailbox, st.worker_seen_at = mailbox, datetime.now(UTC)
        db.commit()
