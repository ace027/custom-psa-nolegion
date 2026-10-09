"""Client-portal sign-in: one-time emailed links and portal sessions.

Separate from staff sessions on purpose: a different cookie, different tables, and a principal
(a contact) that can only ever be scoped to its own organization."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Contact, Organization, PortalLoginToken, PortalSession

MAX_LINKS_PER_CONTACT_PER_HOUR = 3
MAX_LINKS_PER_IP_PER_HOUR = 20


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def find_contact_by_email(db: Session, email: str) -> Contact | None:
    """The one active, portal-enabled contact for this address (the unique index guarantees one)."""
    return db.execute(
        select(Contact)
        .join(Organization, Organization.id == Contact.organization_id)
        .where(
            func.lower(Contact.email) == email.strip().lower(),
            Contact.portal_access.is_(True),
            Contact.archived_at.is_(None),
            Organization.archived_at.is_(None),
        )
    ).scalar_one_or_none()


def may_issue_link(db: Session, contact: Contact, ip: str | None) -> bool:
    since = datetime.now(UTC) - timedelta(hours=1)
    per_contact = db.execute(
        select(func.count()).where(
            PortalLoginToken.contact_id == contact.id, PortalLoginToken.created_at > since
        )
    ).scalar_one()
    if per_contact >= MAX_LINKS_PER_CONTACT_PER_HOUR:
        return False
    if ip:
        per_ip = db.execute(
            select(func.count()).where(
                PortalLoginToken.requested_ip == ip, PortalLoginToken.created_at > since
            )
        ).scalar_one()
        if per_ip >= MAX_LINKS_PER_IP_PER_HOUR:
            return False
    return True


def issue_link_token(db: Session, contact: Contact, ip: str | None) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        PortalLoginToken(
            token_hash=_hash(token),
            contact_id=contact.id,
            expires_at=datetime.now(UTC) + timedelta(minutes=get_settings().portal_link_minutes),
            requested_ip=ip,
        )
    )
    db.flush()
    return token


def consume_link_token(db: Session, token: str) -> Contact | None:
    """Single use, atomically: two clicks race on one UPDATE and only one wins."""
    contact_id = db.execute(
        update(PortalLoginToken)
        .where(
            PortalLoginToken.token_hash == _hash(token),
            PortalLoginToken.used_at.is_(None),
            PortalLoginToken.expires_at > datetime.now(UTC),
        )
        .values(used_at=datetime.now(UTC))
        .returning(PortalLoginToken.contact_id)
    ).scalar_one_or_none()
    if contact_id is None:
        return None
    contact = db.get(Contact, contact_id)
    return contact if _active(db, contact) else None


def _active(db: Session, contact: Contact | None) -> bool:
    if contact is None or not contact.portal_access or contact.archived_at is not None:
        return False
    org = db.get(Organization, contact.organization_id)
    return org is not None and org.archived_at is None


def create_session(db: Session, contact: Contact, ip: str | None, user_agent: str | None) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        PortalSession(
            token_hash=_hash(token),
            contact_id=contact.id,
            expires_at=datetime.now(UTC) + timedelta(hours=get_settings().portal_session_hours),
            ip=ip,
            user_agent=(user_agent or "")[:300] or None,
        )
    )
    return token


def get_contact_for_token(db: Session, token: str | None) -> Contact | None:
    """The signed-in contact, provided access has not been revoked since the session began."""
    if not token:
        return None
    contact = db.execute(
        select(Contact)
        .join(PortalSession, PortalSession.contact_id == Contact.id)
        .where(
            PortalSession.token_hash == _hash(token), PortalSession.expires_at > datetime.now(UTC)
        )
    ).scalar_one_or_none()
    return contact if _active(db, contact) else None


def delete_session(db: Session, token: str) -> None:
    db.execute(delete(PortalSession).where(PortalSession.token_hash == _hash(token)))


def revoke_contact_sessions(db: Session, contact_id: int) -> None:
    db.execute(delete(PortalSession).where(PortalSession.contact_id == contact_id))
