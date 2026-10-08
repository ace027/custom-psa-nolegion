from fastapi import APIRouter, Query
from sqlalchemy import or_, select

from app import permissions as P
from app.deps import Ctx, require
from app.models import Asset, Contact, Organization, Ticket
from app.schemas import SearchHit, SearchOut

router = APIRouter(tags=["search"])
PER_KIND = 6


def _like(q: str) -> str:
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@router.get(
    "/search",
    response_model=SearchOut,
    summary="Search tickets, clients, contacts and devices in one box",
)
def search(q: str = Query(min_length=2, max_length=100), ctx: Ctx = require(P.TICKET_READ)):
    """Everything goes through the caller's scope (and RLS behind it). Client, contact and device
    results need the same permission as browsing them."""
    q = q.strip()
    like = _like(q)
    hits: list[SearchHit] = []

    stmt = ctx.scope.apply(select(Ticket), Ticket.organization_id)
    if q.lstrip("#").isdigit():
        stmt = stmt.where(Ticket.number == int(q.lstrip("#")))
    else:
        stmt = stmt.where(
            or_(
                Ticket.subject.ilike(like, escape="\\"),
                Ticket.requester_email.ilike(like, escape="\\"),
            )
        )
    for t in (
        ctx.db.execute(stmt.order_by(Ticket.updated_at.desc()).limit(PER_KIND)).unique().scalars()
    ):
        hits.append(
            SearchHit(
                kind="ticket",
                id=t.id,
                title=f"#{t.number} {t.subject}",
                subtitle=t.status.replace("_", " "),
                organization_id=t.organization_id,
            )
        )

    from app.permissions import has_permission

    if ctx.user is not None and has_permission(ctx.user.role, P.ORG_READ):
        orgs = ctx.scope.apply(select(Organization), Organization.id).where(
            Organization.archived_at.is_(None), Organization.name.ilike(like, escape="\\")
        )
        for o in ctx.db.execute(orgs.order_by(Organization.name).limit(PER_KIND)).scalars():
            hits.append(
                SearchHit(
                    kind="organization", id=o.id, title=o.name, subtitle=None, organization_id=o.id
                )
            )

        contacts = ctx.scope.apply(select(Contact), Contact.organization_id).where(
            Contact.archived_at.is_(None),
            or_(Contact.name.ilike(like, escape="\\"), Contact.email.ilike(like, escape="\\")),
        )
        for c in ctx.db.execute(contacts.order_by(Contact.name).limit(PER_KIND)).scalars():
            hits.append(
                SearchHit(
                    kind="contact",
                    id=c.id,
                    title=c.name,
                    subtitle=c.email,
                    organization_id=c.organization_id,
                )
            )

        assets = ctx.scope.apply(select(Asset), Asset.organization_id).where(
            Asset.retired_at.is_(None),
            or_(
                Asset.name.ilike(like, escape="\\"),
                Asset.serial.ilike(like, escape="\\"),
                Asset.model.ilike(like, escape="\\"),
            ),
        )
        for a in ctx.db.execute(assets.order_by(Asset.name).limit(PER_KIND)).unique().scalars():
            hits.append(
                SearchHit(
                    kind="asset",
                    id=a.id,
                    title=a.name,
                    subtitle=" ".join(x for x in (a.manufacturer, a.model, a.serial) if x) or None,
                    organization_id=a.organization_id,
                )
            )
    return SearchOut(q=q, hits=hits)
