"""Request plumbing for the client portal. A portal principal is a contact, and its data scope is
exactly one organization, both in the app layer and in Postgres row-level security."""

from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import audit
from app import db as dbmod
from app import repositories as repo
from app.auth import portal_sessions
from app.config import get_settings
from app.deps import Ctx
from app.models import Contact
from app.scope import Scope


@dataclass
class PortalCtx(Ctx):
    contact: Contact | None = None


def portal_enabled(db: Session) -> bool:
    return repo.get_settings_row(db).portal_enabled


def _portal_ctx(request: Request) -> Iterator[PortalCtx]:
    db = dbmod.new_session()
    try:
        # Looking the session up needs to see the contact whichever client it belongs to; after
        # that the transaction is narrowed to that one organization.
        dbmod.set_org_scope(db, "all")
        contact = portal_sessions.get_contact_for_token(
            db, request.cookies.get(get_settings().portal_cookie_name)
        )
        if contact is None:
            raise HTTPException(status_code=401, detail="Not signed in")
        if not portal_enabled(db):
            raise HTTPException(status_code=403, detail="The client portal is turned off")
        scope = Scope.orgs(contact.organization_id)
        dbmod.set_org_scope(db, scope.rls_value())
        yield PortalCtx(db=db, user=None, scope=scope, contact=contact)
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


_portal_ctx.__psa_permission__ = "portal"  # type: ignore[attr-defined]


def portal_required():
    return Depends(_portal_ctx, scope="function")


def billing_only(ctx: PortalCtx) -> None:
    """Invoices and statements are for the client's billing contacts only."""
    if not ctx.contact.is_billing_contact:
        audit.record_auth_event(
            "portal.denied", detail={"contact_id": ctx.contact.id, "reason": "not_billing_contact"}
        )
        raise HTTPException(status_code=403, detail="Billing information is not available to you")


def public_session() -> Iterator[Session]:
    """Unauthenticated portal endpoints (request a link, redeem a link). They run with an
    all-organization scope so a contact can be found by email; they touch nothing else."""
    db = dbmod.new_session()
    try:
        dbmod.set_org_scope(db, "all")
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def devices_only(ctx: PortalCtx) -> None:
    """Device and warranty data needs BOTH a tech publishing it for the client and an explicit
    flag on this contact. The two reasons look the same to the caller."""
    from app import portal as svc

    org = repo.get_organization(ctx.db, ctx.scope, ctx.contact.organization_id)
    if not svc.devices_visible(ctx, org):
        audit.record_auth_event(
            "portal.denied", detail={"contact_id": ctx.contact.id, "reason": "devices_not_shared"}
        )
        raise HTTPException(status_code=403, detail="Device information is not available to you")
