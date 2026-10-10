"""Links between tickets, and "close as duplicate".

Closing as a duplicate never moves anything: notes and time stay on the ticket where they were
written (notes are immutable, and time stays billable where it was logged). The original gets an
internal pointer note; the duplicate is linked, noted and closed."""

from sqlalchemy import or_, select

from app import audit
from app import repositories as repo
from app import ticket_services as tsvc
from app.deps import Ctx
from app.errors import Conflict, NotFound
from app.models import Ticket, TicketLink, TicketNote

# What the OTHER ticket is, seen from the ticket you are looking at.
RELATIONS = ("related", "duplicate_of", "has_duplicate", "parent", "child")
MAX_DEPTH = 20


def _view(ticket_id: int, link: TicketLink) -> tuple[str, int]:
    """(relation of the other ticket as seen from `ticket_id`, other ticket id)."""
    mine_is_source = link.source_ticket_id == ticket_id
    other = link.target_ticket_id if mine_is_source else link.source_ticket_id
    if link.kind == "related":
        return "related", other
    if link.kind == "duplicate_of":
        # source is the duplicate: the other is its original, or (from the original) a duplicate
        return ("duplicate_of" if mine_is_source else "has_duplicate"), other
    return ("child" if mine_is_source else "parent"), other


def _get(ctx: Ctx, ticket_id: int) -> Ticket:
    t = repo.get_ticket(ctx.db, ctx.scope, ticket_id)
    if t is None:
        raise NotFound("Ticket not found")
    return t


def list_links(ctx: Ctx, ticket_id: int) -> list[dict]:
    _get(ctx, ticket_id)
    links = ctx.db.execute(
        select(TicketLink)
        .where(
            or_(TicketLink.source_ticket_id == ticket_id, TicketLink.target_ticket_id == ticket_id)
        )
        .order_by(TicketLink.id)
    ).scalars()
    out = []
    for link in links:
        relation, other_id = _view(ticket_id, link)
        other = repo.get_ticket(ctx.db, ctx.scope, other_id)
        if other is None:
            continue
        out.append(
            dict(
                id=link.id,
                relation=relation,
                ticket_id=other.id,
                number=other.number,
                subject=other.subject,
                status=other.status,
                status_name=other.status_ref.name,
                created_at=link.created_at,
            )
        )
    return out


def _ancestors(ctx: Ctx, ticket_id: int) -> set[int]:
    seen: set[int] = set()
    current = ticket_id
    for _ in range(MAX_DEPTH):
        parent = ctx.db.execute(
            select(TicketLink.source_ticket_id).where(
                TicketLink.target_ticket_id == current, TicketLink.kind == "parent_of"
            )
        ).scalar_one_or_none()
        if parent is None or parent in seen:
            break
        seen.add(parent)
        current = parent
    return seen


def _resolve(ctx: Ctx, ticket: Ticket, other_number: int) -> Ticket:
    other = repo.get_ticket_by_number(ctx.db, ctx.scope, other_number)
    if other is None:
        raise NotFound(f"No ticket #{other_number}")
    if other.id == ticket.id:
        raise Conflict("A ticket cannot be linked to itself")
    if ticket.organization_id is None or other.organization_id != ticket.organization_id:
        raise Conflict("Tickets can only be linked within the same client")
    return other


def _insert(ctx: Ctx, org_id: int, kind: str, source: Ticket, target: Ticket) -> TicketLink:
    """Insert, turning the database's uniqueness rules into plain messages."""
    from sqlalchemy.exc import IntegrityError

    link = TicketLink(
        organization_id=org_id,
        source_ticket_id=source.id,
        target_ticket_id=target.id,
        kind=kind,
        created_by=ctx.user.id if ctx.user else None,
    )
    try:
        with ctx.db.begin_nested():
            ctx.db.add(link)
            ctx.db.flush()
    except IntegrityError:
        raise Conflict(
            "These tickets are already linked, or one is already a duplicate of "
            "another ticket / already has a parent"
        ) from None
    return link


def add_link(ctx: Ctx, ticket_id: int, relation: str, other_number: int) -> TicketLink:
    ticket = _get(ctx, ticket_id)
    other = _resolve(ctx, ticket, other_number)
    if relation == "related":
        kind, source, target = "related", ticket, other
    elif relation == "duplicate_of":
        kind, source, target = "duplicate_of", ticket, other
    elif relation == "has_duplicate":
        kind, source, target = "duplicate_of", other, ticket
    elif relation == "parent":  # `other` is this ticket's parent
        kind, source, target = "parent_of", other, ticket
    elif relation == "child":
        kind, source, target = "parent_of", ticket, other
    else:
        raise Conflict("Unknown relation")
    _check_rules(ctx, kind, source, target)
    link = _insert(ctx, ticket.organization_id, kind, source, target)
    audit.record(
        ctx.db,
        ctx.user,
        "ticket.link_add",
        link,
        after={"kind": kind, "source": source.number, "target": target.number},
        organization_id=ticket.organization_id,
    )
    return link


def _check_rules(ctx: Ctx, kind: str, source: Ticket, target: Ticket) -> None:
    if kind == "parent_of":
        if target.id in _ancestors(ctx, source.id):
            raise Conflict("That would make a ticket its own ancestor")
    if kind == "duplicate_of":
        is_dup = ctx.db.execute(
            select(TicketLink.id).where(
                TicketLink.source_ticket_id == target.id, TicketLink.kind == "duplicate_of"
            )
        ).first()
        if is_dup:
            raise Conflict(f"#{target.number} is itself a duplicate: link to its original instead")
        has_dups = ctx.db.execute(
            select(TicketLink.id).where(
                TicketLink.target_ticket_id == source.id, TicketLink.kind == "duplicate_of"
            )
        ).first()
        if has_dups:
            raise Conflict(f"#{source.number} already has duplicates of its own")


def remove_link(ctx: Ctx, ticket_id: int, link_id: int) -> None:
    _get(ctx, ticket_id)
    link = ctx.db.get(TicketLink, link_id)
    if link is None or ticket_id not in (link.source_ticket_id, link.target_ticket_id):
        raise NotFound("Link not found")
    audit.record(
        ctx.db,
        ctx.user,
        "ticket.link_remove",
        link,
        before={
            "kind": link.kind,
            "source_ticket_id": link.source_ticket_id,
            "target_ticket_id": link.target_ticket_id,
        },
        organization_id=link.organization_id,
    )
    ctx.db.delete(link)
    ctx.db.flush()


def _pointer_note(ctx: Ctx, ticket: Ticket, body: str) -> None:
    ctx.db.add(
        TicketNote(
            ticket_id=ticket.id,
            organization_id=ticket.organization_id,
            author_user_id=ctx.user.id if ctx.user else None,
            visibility="internal",
            source="ui",
            body=body,
        )
    )
    ticket.updated_at = tsvc.now()


def close_as_duplicate(ctx: Ctx, ticket_id: int, original_number: int) -> Ticket:
    ticket = _get(ctx, ticket_id)
    if ticket.status == "closed":
        raise Conflict("That ticket is already closed")
    original = _resolve(ctx, ticket, original_number)
    _check_rules(ctx, "duplicate_of", ticket, original)
    # Resolve everything that queries BEFORE mutating the ticket (autoflush; see _apply_status).
    link = _insert(ctx, ticket.organization_id, "duplicate_of", ticket, original)
    _pointer_note(
        ctx, ticket, f"Closed as a duplicate of #{original.number}. Notes and time stay here."
    )
    _pointer_note(
        ctx,
        original,
        f"#{ticket.number} ({ticket.subject}) was closed as a duplicate of this ticket. "
        "Its notes and time remain on that ticket.",
    )
    tsvc._apply_status(ctx, ticket, "closed")
    ctx.db.flush()
    audit.record(
        ctx.db,
        ctx.user,
        "ticket.close_duplicate",
        ticket,
        after={"original": original.number, "link_id": link.id},
        organization_id=ticket.organization_id,
    )
    ctx.db.refresh(ticket)
    return ticket
