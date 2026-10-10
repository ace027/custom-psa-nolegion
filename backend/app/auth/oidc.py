"""Entra ID OIDC (authorization code + PKCE). Single-tenant app registration."""

from functools import lru_cache

from authlib.integrations.starlette_client import OAuth
from sqlalchemy.orm import Session

from app import repositories as repo
from app.config import get_settings
from app.models import User


@lru_cache
def get_oauth() -> OAuth:
    s = get_settings()
    oauth = OAuth()
    oauth.register(
        name="entra",
        server_metadata_url=(
            f"https://login.microsoftonline.com/{s.entra_tenant_id}/v2.0/.well-known/"
            "openid-configuration"
        ),
        client_id=s.entra_client_id,
        client_secret=s.entra_client_secret,
        client_kwargs={"scope": "openid profile email", "code_challenge_method": "S256"},
    )
    return oauth


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
    return user
