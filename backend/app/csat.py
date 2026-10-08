"""Customer satisfaction (CSAT): one survey per ticket, sent when it is first resolved.

- off by default (settings.csat_enabled); only for tickets that belong to a known client
- the email carries one link per rating (1-5). Links hold a single-use token in the URL
  FRAGMENT, which browsers never send to a server, so mail scanners that pre-fetch links cannot
  answer for the customer: the page asks for a confirmation click (and an optional comment)
- only the token's hash is stored; it answers once, expires after 30 days, and reveals nothing
  but the ticket number it belongs to
- sent as an auto-generated message (suppress-auto-response headers; never replied to)"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app import audit
from app import repositories as repo
from app.config import get_settings
from app.deps import Ctx
from app.errors import NotFound
from app.models import CsatSurvey, EmailMessage, Ticket
from app.ticket_services import recipient_for

EXPIRY_DAYS = 30
RATING_WORDS = {1: "Very unhappy", 2: "Unhappy", 3: "Okay", 4: "Happy", 5: "Very happy"}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _body(ticket: Ticket, company: str, token: str) -> str:
    base = f"{get_settings().public_url.rstrip('/')}/csat#token={token}&rating="
    links = "\n".join(f"  {n} - {RATING_WORDS[n]}: {base}{n}" for n in (5, 4, 3, 2, 1))
    name = ticket.contact.name if ticket.contact else "there"
    return (
        f"Hi {name},\n\n"
        f"Your request #{ticket.number} ({ticket.subject}) has been marked resolved. "
        f"How did {company} do? Choose one (you can add a comment on the next page):\n\n"
        f"{links}\n\n"
        "This is an automated message; please do not reply. If the problem is not fixed, "
        "reply to our earlier email about this request instead.\n"
    )


def maybe_request(ctx: Ctx, ticket: Ticket) -> bool:
    """Queue the survey email. Returns False when skipped for any reason."""
    settings = repo.get_settings_row(ctx.db)
    if not settings.csat_enabled or ticket.organization_id is None:
        return False
    to = (recipient_for(ticket) or "").strip().lower()
    if not to:
        return False
    token = secrets.token_urlsafe(32)
    try:
        with ctx.db.begin_nested():  # a duplicate (second resolve) must not poison the caller
            email = EmailMessage(
                direction="out",
                ticket_id=ticket.id,
                organization_id=ticket.organization_id,
                to_emails=[to],
                subject=f"[#{ticket.number}] How did we do?"[:998],
                body_text=_body(ticket, settings.company_name or "we", token),
                send_status="pending",
                auto_generated=True,
            )
            ctx.db.add(email)
            ctx.db.flush()
            ctx.db.add(
                CsatSurvey(
                    ticket_id=ticket.id,
                    organization_id=ticket.organization_id,
                    token_hash=_hash(token),
                    sent_to=to,
                    email_message_id=email.id,
                    expires_at=datetime.now(UTC) + timedelta(days=EXPIRY_DAYS),
                )
            )
            ctx.db.flush()
    except IntegrityError:
        return False
    return True


def respond(db, token: str, rating: int, comment: str | None):
    """Record the answer, atomically and once. Returns the ticket number."""
    row = db.execute(
        update(CsatSurvey)
        .where(
            CsatSurvey.token_hash == _hash(token),
            CsatSurvey.responded_at.is_(None),
            CsatSurvey.expires_at > datetime.now(UTC),
        )
        .values(
            rating=rating,
            comment=(comment or "").strip() or None,
            responded_at=datetime.now(UTC),
        )
        .returning(CsatSurvey.ticket_id, CsatSurvey.organization_id)
    ).first()
    if row is None:
        audit.record_auth_event("csat.respond_failed", detail={"reason": "bad_or_used_link"})
        raise NotFound("This link has expired or was already used")
    ticket = db.get(Ticket, row.ticket_id)
    audit.record(
        db,
        None,
        "csat.respond",
        ticket,
        after={"rating": rating, "has_comment": bool((comment or "").strip())},
        organization_id=row.organization_id,
    )
    return ticket.number


def for_ticket(ctx: Ctx, ticket_id: int) -> CsatSurvey | None:
    if repo.get_ticket(ctx.db, ctx.scope, ticket_id) is None:
        raise NotFound("Ticket not found")
    return ctx.db.execute(
        select(CsatSurvey).where(CsatSurvey.ticket_id == ticket_id)
    ).scalar_one_or_none()


def summary(ctx: Ctx, days: int) -> dict:
    since = datetime.now(UTC) - timedelta(days=days)
    base = ctx.scope.apply(
        select(CsatSurvey.rating, func.count()).where(CsatSurvey.created_at >= since),
        CsatSurvey.organization_id,
    )
    counts = dict(ctx.db.execute(base.group_by(CsatSurvey.rating)).all())
    answered = {k: v for k, v in counts.items() if k is not None}
    n = sum(answered.values())
    return dict(
        days=days,
        requested=sum(counts.values()),
        responses=n,
        average=round(sum(k * v for k, v in answered.items()) / n, 2) if n else None,
        distribution={str(i): answered.get(i, 0) for i in range(1, 6)},
    )
