"""Business rules. Every write records an audit row in the same transaction."""

from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app import audit
from app import repositories as repo
from app.auth import sessions
from app.deps import Ctx
from app.errors import Conflict, Forbidden, NotFound
from app.models import Contact, Organization, Site, User

CONTACT_CONFLICT = (
    "That email is already used by a contact here, or already has portal access for another client"
)


def _flush(ctx: Ctx, message: str) -> None:
    try:
        ctx.db.flush()
    except IntegrityError as exc:
        ctx.db.rollback()
        raise Conflict(message) from exc


def _apply(obj, data: dict) -> None:
    for key, value in data.items():
        setattr(obj, key, value)


# ---- organizations ----
def create_organization(ctx: Ctx, data: dict) -> Organization:
    org = Organization(**data)
    ctx.db.add(org)
    _flush(ctx, "An active organization with that name already exists")
    audit.record(
        ctx.db,
        ctx.user,
        "organization.create",
        org,
        after=audit.snapshot(org),
        organization_id=org.id,
    )
    return org


def update_organization(ctx: Ctx, org_id: int, data: dict) -> Organization:
    org = repo.get_organization(ctx.db, ctx.scope, org_id)
    if org is None:
        raise NotFound("Organization not found")
    before = audit.snapshot(org)
    _apply(org, data)
    _flush(ctx, "An active organization with that name already exists")
    ctx.db.refresh(org)
    audit.record(
        ctx.db,
        ctx.user,
        "organization.update",
        org,
        before=before,
        after=audit.snapshot(org),
        organization_id=org.id,
    )
    return org


def set_organization_archived(ctx: Ctx, org_id: int, archived: bool) -> Organization:
    org = repo.get_organization(ctx.db, ctx.scope, org_id)
    if org is None:
        raise NotFound("Organization not found")
    before = audit.snapshot(org)
    org.archived_at = datetime.now(UTC) if archived else None
    _flush(ctx, "An active organization with that name already exists")
    ctx.db.refresh(org)
    audit.record(
        ctx.db,
        ctx.user,
        "organization.archive" if archived else "organization.unarchive",
        org,
        before=before,
        after=audit.snapshot(org),
        organization_id=org.id,
    )
    return org


# ---- sites ----
def create_site(ctx: Ctx, org_id: int, data: dict) -> Site:
    if repo.get_organization(ctx.db, ctx.scope, org_id) is None:
        raise NotFound("Organization not found")
    site = Site(organization_id=org_id, **data)
    ctx.db.add(site)
    ctx.db.flush()
    audit.record(
        ctx.db, ctx.user, "site.create", site, after=audit.snapshot(site), organization_id=org_id
    )
    return site


def update_site(ctx: Ctx, site_id: int, data: dict) -> Site:
    site = repo.get_site(ctx.db, ctx.scope, site_id)
    if site is None:
        raise NotFound("Site not found")
    before = audit.snapshot(site)
    _apply(site, data)
    ctx.db.flush()
    ctx.db.refresh(site)
    audit.record(
        ctx.db,
        ctx.user,
        "site.update",
        site,
        before=before,
        after=audit.snapshot(site),
        organization_id=site.organization_id,
    )
    return site


def set_site_archived(ctx: Ctx, site_id: int, archived: bool) -> Site:
    site = repo.get_site(ctx.db, ctx.scope, site_id)
    if site is None:
        raise NotFound("Site not found")
    before = audit.snapshot(site)
    site.archived_at = datetime.now(UTC) if archived else None
    ctx.db.flush()
    ctx.db.refresh(site)
    audit.record(
        ctx.db,
        ctx.user,
        "site.archive" if archived else "site.unarchive",
        site,
        before=before,
        after=audit.snapshot(site),
        organization_id=site.organization_id,
    )
    return site


# ---- contacts ----
def _check_site(ctx: Ctx, org_id: int, site_id: int | None) -> None:
    if site_id is None:
        return
    site = repo.get_site(ctx.db, ctx.scope, site_id)
    if site is None or site.organization_id != org_id:
        raise Conflict("Site does not belong to this organization")


def _clear_other_primary(ctx: Ctx, org_id: int, keep_id: int | None) -> None:
    current = repo.get_primary_contact(ctx.db, ctx.scope, org_id)
    if current is not None and current.id != keep_id:
        before = audit.snapshot(current)
        current.is_primary = False
        ctx.db.flush()
        audit.record(
            ctx.db,
            ctx.user,
            "contact.update",
            current,
            before=before,
            after=audit.snapshot(current),
            organization_id=org_id,
        )


def create_contact(ctx: Ctx, org_id: int, data: dict) -> Contact:
    if repo.get_organization(ctx.db, ctx.scope, org_id) is None:
        raise NotFound("Organization not found")
    _check_site(ctx, org_id, data.get("site_id"))
    if data.get("is_primary"):
        _clear_other_primary(ctx, org_id, None)
    if data.get("portal_access") and not data.get("email"):
        raise Conflict("Portal access needs an email address on the contact")
    contact = Contact(organization_id=org_id, **data)
    ctx.db.add(contact)
    _flush(ctx, CONTACT_CONFLICT)
    audit.record(
        ctx.db,
        ctx.user,
        "contact.create",
        contact,
        after=audit.snapshot(contact),
        organization_id=org_id,
    )
    return contact


def _revoke_portal(ctx: Ctx, contact: Contact) -> None:
    from app.auth import portal_sessions

    portal_sessions.revoke_contact_sessions(ctx.db, contact.id)


def update_contact(ctx: Ctx, contact_id: int, data: dict) -> Contact:
    contact = repo.get_contact(ctx.db, ctx.scope, contact_id)
    if contact is None:
        raise NotFound("Contact not found")
    _check_site(ctx, contact.organization_id, data.get("site_id"))
    before = audit.snapshot(contact)
    if data.get("is_primary"):
        _clear_other_primary(ctx, contact.organization_id, contact.id)
    _apply(contact, data)
    if contact.portal_access and not contact.email:
        raise Conflict("Portal access needs an email address on the contact")
    _flush(ctx, CONTACT_CONFLICT)
    if not contact.portal_access and before["portal_access"]:
        _revoke_portal(ctx, contact)
    ctx.db.refresh(contact)
    audit.record(
        ctx.db,
        ctx.user,
        "contact.update",
        contact,
        before=before,
        after=audit.snapshot(contact),
        organization_id=contact.organization_id,
    )
    return contact


def set_contact_archived(ctx: Ctx, contact_id: int, archived: bool) -> Contact:
    contact = repo.get_contact(ctx.db, ctx.scope, contact_id)
    if contact is None:
        raise NotFound("Contact not found")
    before = audit.snapshot(contact)
    contact.archived_at = datetime.now(UTC) if archived else None
    if archived:
        _revoke_portal(ctx, contact)
    if archived:
        contact.is_primary = False
    _flush(ctx, CONTACT_CONFLICT)
    ctx.db.refresh(contact)
    audit.record(
        ctx.db,
        ctx.user,
        "contact.archive" if archived else "contact.unarchive",
        contact,
        before=before,
        after=audit.snapshot(contact),
        organization_id=contact.organization_id,
    )
    return contact


# ---- users ----
def create_user(ctx: Ctx, data: dict) -> User:
    if repo.get_user_by_email(ctx.db, data["email"]) is not None:
        raise Conflict("A user with that email already exists")
    user = User(**data)
    ctx.db.add(user)
    _flush(ctx, "A user with that email already exists")
    audit.record(ctx.db, ctx.user, "user.create", user, after=audit.snapshot(user))
    return user


def update_user(ctx: Ctx, user_id: int, data: dict) -> User:
    user = repo.get_user(ctx.db, user_id)
    if user is None:
        raise NotFound("User not found")
    if user.id == ctx.user.id and (
        data.get("is_active") is False or ("role" in data and data["role"] != user.role)
    ):
        raise Forbidden("You cannot change your own role or deactivate yourself")
    before = audit.snapshot(user)
    _apply(user, data)
    ctx.db.flush()
    ctx.db.refresh(user)
    audit.record(ctx.db, ctx.user, "user.update", user, before=before, after=audit.snapshot(user))
    if "role" in data and data["role"] != before["role"]:
        audit.record(
            ctx.db,
            ctx.user,
            "auth.role_changed",
            user,
            detail={"from": before["role"], "to": data["role"]},
        )
    if data.get("is_active") is False:
        # deactivation takes effect immediately: kill their sessions
        revoked = sessions.revoke_user_sessions(ctx.db, user.id)
        audit.record(ctx.db, ctx.user, "auth.sessions_revoked", user, detail={"count": revoked})
    return user


def touch_login(ctx_db, user: User) -> None:
    ctx_db.execute(update(User).where(User.id == user.id).values(last_login_at=datetime.now(UTC)))
