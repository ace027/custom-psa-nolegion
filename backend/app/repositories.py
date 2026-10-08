"""All database queries live here. Anything client-owned goes through Scope."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Contact, Organization, Site, User
from app.scope import Scope


def _count(db: Session, stmt) -> int:
    return db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()


# ---- organizations ----
def list_organizations(db, scope: Scope, *, q, include_archived, limit, offset):
    stmt = scope.apply(select(Organization), Organization.id)
    if not include_archived:
        stmt = stmt.where(Organization.archived_at.is_(None))
    if q:
        stmt = stmt.where(Organization.name.ilike(f"%{q}%"))
    total = _count(db, stmt)
    rows = db.execute(stmt.order_by(func.lower(Organization.name)).limit(limit).offset(offset))
    return list(rows.scalars()), total


def get_organization(db, scope: Scope, org_id: int) -> Organization | None:
    stmt = scope.apply(select(Organization).where(Organization.id == org_id), Organization.id)
    return db.execute(stmt).scalar_one_or_none()


# ---- sites ----
def list_sites(db, scope: Scope, org_id: int, include_archived: bool):
    stmt = scope.apply(select(Site).where(Site.organization_id == org_id), Site.organization_id)
    if not include_archived:
        stmt = stmt.where(Site.archived_at.is_(None))
    return list(db.execute(stmt.order_by(func.lower(Site.name))).scalars())


def get_site(db, scope: Scope, site_id: int) -> Site | None:
    stmt = scope.apply(select(Site).where(Site.id == site_id), Site.organization_id)
    return db.execute(stmt).scalar_one_or_none()


# ---- contacts ----
def list_contacts(db, scope: Scope, org_id: int, include_archived: bool):
    stmt = scope.apply(
        select(Contact).where(Contact.organization_id == org_id), Contact.organization_id
    )
    if not include_archived:
        stmt = stmt.where(Contact.archived_at.is_(None))
    return list(db.execute(stmt.order_by(func.lower(Contact.name))).scalars())


def get_contact(db, scope: Scope, contact_id: int) -> Contact | None:
    stmt = scope.apply(select(Contact).where(Contact.id == contact_id), Contact.organization_id)
    return db.execute(stmt).scalar_one_or_none()


def get_primary_contact(db, scope: Scope, org_id: int) -> Contact | None:
    stmt = scope.apply(
        select(Contact).where(
            Contact.organization_id == org_id,
            Contact.is_primary.is_(True),
            Contact.archived_at.is_(None),
        ),
        Contact.organization_id,
    )
    return db.execute(stmt).scalar_one_or_none()


# ---- users (not client-owned, so no Scope) ----
def list_users(db: Session):
    return list(db.execute(select(User).order_by(func.lower(User.display_name))).scalars())


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.execute(
        select(User).where(func.lower(User.email) == email.lower())
    ).scalar_one_or_none()


def get_user_by_oid(db: Session, oid: str) -> User | None:
    return db.execute(select(User).where(User.entra_oid == oid)).scalar_one_or_none()


# ---- audit ----
def list_audit(
    db: Session, *, entity_type, entity_id, organization_id, actor_id, action, limit, offset
):
    stmt = select(AuditLog)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if organization_id is not None:
        stmt = stmt.where(AuditLog.organization_id == organization_id)
    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if action:
        stmt = stmt.where(AuditLog.action.like(f"{action}%"))
    total = _count(db, stmt)
    rows = db.execute(stmt.order_by(AuditLog.id.desc()).limit(limit).offset(offset))
    return list(rows.scalars()), total


# ---------------------------------------------------------------------------------------
# Phase 2: ticketing
# ---------------------------------------------------------------------------------------
from app.models import (  # noqa: E402
    Attachment,
    EmailMessage,
    MailboxStatus,
    Priority,
    Settings,
    Ticket,
    TicketNote,
    TimeEntry,
)

OPEN_STATUSES = ("new", "open", "waiting_on_customer")


def get_settings_row(db: Session) -> Settings:
    return db.get(Settings, 1)


def get_mailbox_status(db: Session) -> MailboxStatus:
    return db.get(MailboxStatus, 1)


def list_lookup(db: Session, model, include_archived: bool):
    stmt = select(model)
    if not include_archived:
        stmt = stmt.where(model.archived_at.is_(None))
    order = model.rank if model is Priority else func.lower(model.name)
    return list(db.execute(stmt.order_by(order, model.id)).scalars())


def get_lookup(db: Session, model, obj_id: int):
    return db.get(model, obj_id)


def get_default(db: Session, model):
    return db.execute(
        select(model).where(model.is_default.is_(True), model.archived_at.is_(None))
    ).scalar_one_or_none()


def _ticket_stmt(scope: Scope):
    return scope.apply(select(Ticket), Ticket.organization_id)


def get_ticket(db: Session, scope: Scope, ticket_id: int) -> Ticket | None:
    stmt = _ticket_stmt(scope).where(Ticket.id == ticket_id)
    return db.execute(stmt).unique().scalar_one_or_none()


def get_ticket_by_number(db: Session, scope: Scope, number: int) -> Ticket | None:
    stmt = _ticket_stmt(scope).where(Ticket.number == number)
    return db.execute(stmt).unique().scalar_one_or_none()


def list_tickets(
    db: Session,
    scope: Scope,
    *,
    statuses,
    open_only,
    queue_id,
    assignee_id,
    unassigned,
    organization_id,
    priority_id,
    needs_triage,
    q,
    limit,
    offset,
    sort="updated",
    descending=True,
):
    stmt = _ticket_stmt(scope)
    if statuses:
        stmt = stmt.where(Ticket.status.in_(statuses))
    if open_only:
        stmt = stmt.where(Ticket.status.in_(OPEN_STATUSES))
    if queue_id is not None:
        stmt = stmt.where(Ticket.queue_id == queue_id)
    if assignee_id is not None:
        stmt = stmt.where(Ticket.assignee_id == assignee_id)
    if unassigned:
        stmt = stmt.where(Ticket.assignee_id.is_(None))
    if organization_id is not None:
        stmt = stmt.where(Ticket.organization_id == organization_id)
    if priority_id is not None:
        stmt = stmt.where(Ticket.priority_id == priority_id)
    if needs_triage:
        stmt = stmt.where(Ticket.organization_id.is_(None))
    if q:
        if q.lstrip("#").isdigit():
            stmt = stmt.where(Ticket.number == int(q.lstrip("#")))
        else:
            stmt = stmt.where(Ticket.subject.ilike(f"%{q}%"))
    total = _count(db, stmt.with_only_columns(Ticket.id))
    order = _ticket_order(sort, descending)
    if sort == "priority":
        stmt = stmt.join(Priority, Priority.id == Ticket.priority_id)
    rows = db.execute(stmt.order_by(*order, Ticket.id.desc()).limit(limit).offset(offset))
    return list(rows.unique().scalars()), total


TICKET_SORTS = ("updated", "created", "number", "priority", "due")


def _ticket_order(sort: str, descending: bool):
    # 'priority' sorts by rank (1 = most urgent first when ascending); 'due' puts tickets with no
    # resolution target last in either direction.
    col = {
        "updated": Ticket.updated_at,
        "created": Ticket.created_at,
        "number": Ticket.number,
        "priority": Priority.rank,
        "due": Ticket.sla_resolution_due,
    }[sort]
    ordered = col.desc() if descending else col.asc()
    return (ordered.nulls_last(),) if sort == "due" else (ordered,)


def open_tickets(db: Session, scope: Scope, limit: int = 1000) -> list[Ticket]:
    stmt = _ticket_stmt(scope).where(Ticket.status.in_(OPEN_STATUSES))
    return list(db.execute(stmt.order_by(Ticket.created_at).limit(limit)).unique().scalars())


def list_notes(db: Session, scope: Scope, ticket_id: int):
    stmt = scope.apply(
        select(TicketNote).where(TicketNote.ticket_id == ticket_id), TicketNote.organization_id
    )
    return list(db.execute(stmt.order_by(TicketNote.id)).unique().scalars())


def get_email(db: Session, email_id: int) -> EmailMessage | None:
    return db.get(EmailMessage, email_id)


def email_status_map(db: Session, ids: list[int]) -> dict[int, EmailMessage]:
    if not ids:
        return {}
    rows = db.execute(select(EmailMessage).where(EmailMessage.id.in_(ids))).scalars()
    return {e.id: e for e in rows}


def list_time_entries(db: Session, scope: Scope, ticket_id: int, include_voided: bool):
    stmt = select(TimeEntry).where(TimeEntry.ticket_id == ticket_id)
    stmt = scope.apply(stmt, TimeEntry.organization_id)
    if not include_voided:
        stmt = stmt.where(TimeEntry.voided_at.is_(None))
    return list(db.execute(stmt.order_by(TimeEntry.work_date, TimeEntry.id)).scalars())


def get_time_entry(db: Session, scope: Scope, entry_id: int) -> TimeEntry | None:
    stmt = scope.apply(select(TimeEntry).where(TimeEntry.id == entry_id), TimeEntry.organization_id)
    return db.execute(stmt).scalar_one_or_none()


def list_attachments(db: Session, scope: Scope, ticket_id: int):
    stmt = select(Attachment).where(Attachment.ticket_id == ticket_id)
    stmt = scope.apply(stmt, Attachment.organization_id)
    return list(db.execute(stmt.order_by(Attachment.id)).scalars())


def get_attachment(db: Session, scope: Scope, attachment_id: int) -> Attachment | None:
    stmt = scope.apply(
        select(Attachment).where(Attachment.id == attachment_id), Attachment.organization_id
    )
    return db.execute(stmt).scalar_one_or_none()


def find_ticket_by_internet_message_ids(db: Session, ids: list[str]) -> int | None:
    if not ids:
        return None
    return db.execute(
        select(EmailMessage.ticket_id)
        .where(EmailMessage.internet_message_id.in_(ids), EmailMessage.ticket_id.is_not(None))
        .order_by(EmailMessage.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def contacts_by_email(db: Session, email: str) -> list[Contact]:
    return list(
        db.execute(
            select(Contact).where(
                func.lower(Contact.email) == email.lower(), Contact.archived_at.is_(None)
            )
        ).scalars()
    )


def orgs_by_email_domain(db: Session, domain: str) -> list[int]:
    rows = db.execute(
        select(Contact.organization_id)
        .where(
            func.lower(func.split_part(Contact.email, "@", 2)) == domain.lower(),
            Contact.archived_at.is_(None),
        )
        .distinct()
    )
    return [r[0] for r in rows]
