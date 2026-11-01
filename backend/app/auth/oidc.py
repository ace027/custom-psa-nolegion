"""Entra ID OIDC (authorization code + PKCE).

Two app registrations: the single-tenant staff app ('entra_staff') and, for the client portal, a
multi-tenant app ('entra_portal', authority 'organizations') whose sign-ins are mapped to
pre-existing contacts of the organization that owns the token's tenant."""

from dataclasses import dataclass
from functools import lru_cache

from authlib.integrations.starlette_client import OAuth
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
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
    # Neither name may be a prefix of the other: authlib keys its state entries in the shared
    # OIDC state cookie by client name, and prefix overlap would mix the two namespaces.
    _register(oauth, "entra_staff", s.entra_tenant_id, s.entra_client_id, s.entra_client_secret)
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


def portal_claims_options() -> dict:
    """Passed to authorize_access_token for the portal client (authlib reads claims_options per
    call, not from register()). Supplying claims_options REPLACES authlib's defaults, so aud must
    be pinned here explicitly or it is not checked at all. Signature, exp, iat and nonce remain
    authlib's own checks."""
    return {
        "iss": {"essential": True, "validate": portal_issuer_matches_tid},
        "aud": {"essential": True, "values": [get_settings().portal_entra_client_id]},
    }


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


@dataclass
class PortalMatch:
    """Outcome of mapping portal claims. `bound` is True when the contact already holds this oid
    and may be signed in directly; otherwise the match came from the email claim alone and must be
    confirmed through a one-time link sent to the contact's mailbox before anything is bound."""

    contact: Contact
    bound: bool
    oid: str
    tid: str


def resolve_contact_from_claims(db: Session, claims: dict) -> PortalMatch:
    """Map verified portal ID-token claims to an EXISTING portal contact. Never auto-provisions and
    never writes.

    The token's tenant (tid) selects exactly one organization (staff set its entra_tenant_id), and
    the contact is looked up inside THAT organization only: first by the bound Entra object id,
    otherwise by email. Entra does not verify the email / preferred_username claims (any tenant
    member, or an invited guest, can carry an address equal to a contact's), so an email match is
    only a candidate: the caller must prove mailbox ownership with an emailed link before the oid
    is bound (bind_confirmed_oid). A bound oid is never silently replaced.
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
    return PortalMatch(contact=contact, bound=bound is not None, oid=oid, tid=tid)


def _oid_holder(db: Session, oid: str) -> int | None:
    return db.execute(select(Contact.id).where(Contact.entra_oid == oid)).scalar_one_or_none()


def bind_confirmed_oid(
    db: Session, contact: Contact, oid: str, tid: str, *, same_browser: bool
) -> str | None:
    """Bind the oid carried by a redeemed SSO confirmation link. Everything is re-checked now,
    because the link may have sat in the mailbox while staff unlinked, re-pointed the tenant, or
    the same Microsoft account got bound to someone else. Returns None when bound, otherwise the
    reason it was skipped. Raises PortalLoginDenied('oid_conflict') if a concurrent bind of the
    same oid wins the unique index between the check and the write.

    same_browser: the redeeming browser holds the secret set by the SSO callback. Without it the
    mailbox owner may be clicking a link triggered by someone else's Microsoft sign-in; binding
    would hand that other account permanent access to this contact."""
    if not same_browser:
        return "different_browser"
    if contact.entra_oid is not None:
        return "contact_already_linked"
    if _oid_holder(db, oid) is not None:
        return "oid_bound_elsewhere"
    org = db.get(Organization, contact.organization_id)
    current = str((org.entra_tenant_id if org else None) or "").strip().lower()
    if not current or current != str(tid or "").strip().lower():
        return "tenant_changed"
    savepoint = db.begin_nested()
    contact.entra_oid = oid
    try:
        db.flush()
    except IntegrityError:
        savepoint.rollback()
        raise PortalLoginDenied("oid_conflict") from None
    savepoint.commit()
    return None
