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
