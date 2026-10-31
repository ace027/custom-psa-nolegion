"""Entra ID OIDC (authorization code + PKCE).

Two app registrations: the single-tenant staff app ('entra') and, for the client portal, a
multi-tenant app ('entra_portal', authority 'organizations') whose sign-ins are mapped to
pre-existing contacts of the organization that owns the token's tenant."""

from functools import lru_cache

from authlib.integrations.starlette_client import OAuth
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import repositories as repo
from app.config import get_settings
from app.models import Contact, Organization, User

LOGIN_BASE = "https://login.microsoftonline.com"


def _register(oauth: OAuth, name: str, authority: str, client_id: str, secret: str) -> None:
    oauth.register(
        name=name,
        server_metadata_url=f"{LOGIN_BASE}/{authority}/v2.0/.well-known/openid-configuration",
        client_id=client_id,
        client_secret=secret,
        client_kwargs={"scope": "openid profile email", "code_challenge_method": "S256"},
    )


@lru_cache
def get_oauth() -> OAuth:
    s = get_settings()
    oauth = OAuth()
    _register(oauth, "entra", s.entra_tenant_id, s.entra_client_id, s.entra_client_secret)
    if s.portal_sso_configured:
        _register(
            oauth,
            "entra_portal",
            "organizations",
            s.portal_entra_client_id,
            s.portal_entra_client_secret,
        )
    return oauth


def portal_issuer_matches_tid(claims: dict, iss: str | None) -> bool:
    """The multi-tenant metadata advertises the issuer as a template,
    'https://login.microsoftonline.com/{tenantid}/v2.0', which authlib's default exact-match check
    can never satisfy, and skipping the check would accept any issuer. Every tenant's tokens are
    signed with the same Microsoft keys, so the issuer must instead be pinned to the token's OWN
    tenant: iss has to equal the template filled with the signed tid claim."""
    tid = claims.get("tid")
    return bool(tid) and iss == f"{LOGIN_BASE}/{tid}/v2.0"


# Passed to authorize_access_token for the portal client (authlib reads claims_options per call,
# not from register()). Signature, aud, exp, iat and nonce stay authlib's own checks.
PORTAL_CLAIMS_OPTIONS = {"iss": {"essential": True, "validate": portal_issuer_matches_tid}}


class LoginDenied(Exception):
    def __init__(self, reason: str):
        self.reason = reason


def resolve_user_from_claims(db: Session, claims: dict) -> User:
    """Map verified ID-token claims to a PRE-PROVISIONED active staff user.

    Users are never auto-created: an admin must add them first (least privilege). The Entra
    object id (`oid`) is bound on first login and used for matching from then on.
    """
    tenant = get_settings().entra_tenant_id
    if not tenant or claims.get("tid") != tenant:
        raise LoginDenied("wrong_tenant")
    oid = claims.get("oid")
    if not oid:
        raise LoginDenied("missing_oid")

    user = repo.get_user_by_oid(db, oid)
    if user is None:
        email = claims.get("email") or claims.get("preferred_username")
        if not email:
            raise LoginDenied("missing_email")
        user = repo.get_user_by_email(db, email)
        if user is None:
            raise LoginDenied("not_provisioned")
        if user.entra_oid is not None and user.entra_oid != oid:
            raise LoginDenied("oid_mismatch")
        if user.is_active:
            user.entra_oid = oid
    if not user.is_active:
        raise LoginDenied("inactive")
    user.entra_tenant_id = claims["tid"]
    return user


class PortalLoginDenied(Exception):
    def __init__(self, reason: str):
        self.reason = reason


def resolve_contact_from_claims(db: Session, claims: dict) -> Contact:
    """Map verified portal ID-token claims to an EXISTING portal contact. Never auto-provisions.

    The token's tenant (tid) selects exactly one organization (staff set its entra_tenant_id), and
    the contact is looked up inside THAT organization only: first by the bound Entra object id,
    otherwise by email. The email claim is trusted only because it was issued by the client's own
    tenant, whose admins control it; it is never used to reach another organization's contacts.
    The oid is bound on the first successful sign-in and never silently replaced.
    """
    tid = str(claims.get("tid") or "").strip().lower()
    if not tid:
        raise PortalLoginDenied("missing_tid")
    oid = claims.get("oid")
    if not oid:
        raise PortalLoginDenied("missing_oid")

    org = db.execute(
        select(Organization).where(func.lower(Organization.entra_tenant_id) == tid)
    ).scalar_one_or_none()  # partial unique index: at most one
    if org is None:
        raise PortalLoginDenied("unknown_tenant")
    if org.archived_at is not None:
        raise PortalLoginDenied("organization_archived")

    bound = db.execute(select(Contact).where(Contact.entra_oid == oid)).scalar_one_or_none()
    if bound is not None and bound.organization_id != org.id:
        raise PortalLoginDenied("oid_bound_elsewhere")
    contact = bound
    if contact is None:
        email = str(claims.get("email") or claims.get("preferred_username") or "").strip().lower()
        if not email:
            raise PortalLoginDenied("missing_email")
        in_org = select(Contact).where(
            Contact.organization_id == org.id, func.lower(Contact.email) == email
        )
        contact = db.execute(in_org.where(Contact.archived_at.is_(None))).scalar_one_or_none()
        if contact is None:
            archived = db.execute(in_org.limit(1)).scalar_one_or_none()
            raise PortalLoginDenied("contact_archived" if archived else "no_contact")
        if contact.entra_oid is not None and contact.entra_oid != oid:
            raise PortalLoginDenied("oid_mismatch")

    if contact.archived_at is not None:
        raise PortalLoginDenied("contact_archived")
    if not contact.portal_access:
        raise PortalLoginDenied("no_portal_access")
    if contact.entra_oid is None:
        contact.entra_oid = oid
        db.flush()
    return contact
