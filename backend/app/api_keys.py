"""API keys: hashed at rest, scoped to a subset of the owner's permissions, revocable.

The token is shown once at creation. Only its SHA-256 is stored; the 8-hex `prefix` is for
humans (listing, audit) and is not used as a secret.
"""

import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.errors import Conflict, NotFound
from app.models import ApiKey
from app.permissions import KEY_FORBIDDEN, MATRIX, has_permission

if TYPE_CHECKING:
    from app.deps import Ctx

TOKEN_RE = re.compile(r"^psa_[0-9a-f]{8}_[A-Za-z0-9_-]{20,}$")
LAST_USED_THROTTLE = timedelta(minutes=5)
ALL_PERMISSIONS = frozenset().union(*MATRIX.values())


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate() -> tuple[str, str, str]:
    """(token, prefix, sha256 hex of the token)"""
    prefix = secrets.token_hex(4)
    token = f"psa_{prefix}_{secrets.token_urlsafe(32)}"
    return token, prefix, _hash(token)


def state(key: ApiKey, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    if key.revoked_at is not None:
        return "revoked"
    if key.expires_at is not None and key.expires_at <= now:
        return "expired"
    return "active"


def _validate_permissions(ctx: "Ctx", permissions: list[str]) -> list[str]:
    perms = sorted(set(permissions))
    if not perms:
        raise Conflict("Choose at least one permission for the key")
    for p in perms:
        if p in KEY_FORBIDDEN:
            raise Conflict(f"API keys cannot hold the {p} permission")
        if p not in ALL_PERMISSIONS:
            raise Conflict(f"Unknown permission: {p}")
        if ctx.user is None or not has_permission(ctx.user.role, p):
            raise Conflict(f"You cannot grant a permission you do not have: {p}")
    return perms


def create(
    ctx: "Ctx", name: str, permissions: list[str], expires_in_days: int = 365
) -> tuple[ApiKey, str]:
    name = (name or "").strip()
    if not 1 <= len(name) <= 100:
        raise Conflict("Name must be 1 to 100 characters")
    perms = _validate_permissions(ctx, permissions)
    token, prefix, key_hash = generate()
    key = ApiKey(
        name=name,
        prefix=prefix,
        key_hash=key_hash,
        user_id=ctx.user.id,
        permissions=perms,
        expires_at=datetime.now(UTC) + timedelta(days=expires_in_days),
    )
    ctx.db.add(key)
    ctx.db.flush()
    ctx.db.refresh(key)
    audit.record(
        ctx.db,
        ctx.user,
        "api_key.created",
        key,
        detail={
            "prefix": prefix,
            "permissions": perms,
            "expires_at": key.expires_at.isoformat(),
        },
    )
    return key, token


def list_keys(ctx: "Ctx") -> list[ApiKey]:
    return list(ctx.db.scalars(select(ApiKey).order_by(ApiKey.created_at.desc(), ApiKey.id.desc())))


def revoke(ctx: "Ctx", key_id: int) -> ApiKey:
    key = ctx.db.get(ApiKey, key_id)
    if key is None:
        raise NotFound("API key not found")
    if key.revoked_at is not None:
        raise Conflict("API key is already revoked")
    key.revoked_at = datetime.now(UTC)
    key.revoked_by_id = ctx.user.id if ctx.user else None
    ctx.db.flush()
    audit.record(ctx.db, ctx.user, "api_key.revoked", key, detail={"prefix": key.prefix})
    return key


def authenticate(db: Session, token: str) -> ApiKey | None:
    if not TOKEN_RE.match(token or ""):
        return None
    digest = _hash(token)
    key = db.scalar(select(ApiKey).where(ApiKey.key_hash == digest))
    if key is None or not hmac.compare_digest(key.key_hash, digest):
        return None
    now = datetime.now(UTC)
    if state(key, now) != "active" or not key.user.is_active:
        return None
    if key.last_used_at is None or now - key.last_used_at > LAST_USED_THROTTLE:
        key.last_used_at = now
        db.flush()
    return key


def effective_permission(key: ApiKey, permission: str) -> bool:
    return (
        permission in key.permissions
        and permission not in KEY_FORBIDDEN
        and has_permission(key.user.role, permission)
    )
