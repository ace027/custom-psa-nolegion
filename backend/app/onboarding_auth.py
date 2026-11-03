"""One-time admin consent for the setup wizard (incremental consent on the staff SSO app).

The admin is sent to Microsoft with prompt=consent for the three directory scopes below. The
one-time state (plus the PKCE verifier) lives in the signed, 10-minute OIDC state cookie, bound to
the signed-in admin's user id. The resulting access token is stored ONLY as Fernet ciphertext in
onboarding_tokens (at most 60 minutes, one row per admin); it is never logged, never put in the
session cookie and never returned in a response.
"""

import base64
import hashlib
import hmac
import logging
import secrets
import time
from collections.abc import MutableMapping
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException
from sqlalchemy import delete, func, select

from app import crypto
from app.auth.oidc import LOGIN_BASE
from app.config import get_settings
from app.deps import Ctx
from app.errors import Conflict
from app.models import OnboardingToken

logger = logging.getLogger(__name__)

ADMIN_SCOPES = (
    "https://graph.microsoft.com/Application.ReadWrite.All"
    " https://graph.microsoft.com/AppRoleAssignment.ReadWrite.All"
    " https://graph.microsoft.com/DelegatedPermissionGrant.ReadWrite.All"
)
SESSION_KEY = "onboarding_consent"  # no prefix overlap with authlib's "_state_entra_*" keys
STATE_TTL_SECONDS = 600
MAX_TOKEN_SECONDS = 3600
EXPIRED_MESSAGE = "Sign in to Microsoft again to continue setup"


class ConsentFailed(Exception):
    """Microsoft refused or the code exchange failed; `reason` is safe to audit."""

    def __init__(self, reason: str):
        self.reason = reason


def _redirect_uri() -> str:
    return f"{get_settings().public_url}/api/v1/onboarding/consent/callback"


def _authority() -> str:
    return f"{LOGIN_BASE}/{get_settings().entra_tenant_id}/oauth2/v2.0"


def _http_client() -> httpx.Client:
    return httpx.Client(timeout=15, follow_redirects=False)


def start(ctx: Ctx, session: MutableMapping) -> str:
    """Authorize URL for the consent redirect; replaces any earlier pending state."""
    s = get_settings()
    if not s.entra_configured:
        raise HTTPException(503, "Entra ID sign-in is not configured")
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    session[SESSION_KEY] = {
        "state": state,
        "verifier": verifier,
        "user_id": ctx.user.id,
        "expires": time.time() + STATE_TTL_SECONDS,
    }
    # Housekeeping: expired ciphertext is useless but need not linger.
    ctx.db.execute(delete(OnboardingToken).where(OnboardingToken.expires_at <= func.now()))
    query = urlencode(
        {
            "client_id": s.entra_client_id,
            "response_type": "code",
            "redirect_uri": _redirect_uri(),
            "response_mode": "query",
            "scope": ADMIN_SCOPES,
            "state": state,
            "prompt": "consent",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{_authority()}/authorize?{query}"


def check_state(ctx: Ctx, session: MutableMapping, state: str | None) -> str:
    """Consume the pending state (cleared whatever the outcome) and return its PKCE verifier.
    400 unless it matches, belongs to this signed-in admin and is unexpired."""
    pending = session.pop(SESSION_KEY, None)
    if (
        not isinstance(pending, dict)
        or not state
        or not hmac.compare_digest(str(pending.get("state", "")), state)
        or pending.get("user_id") != ctx.user.id
        or float(pending.get("expires", 0)) < time.time()
    ):
        raise HTTPException(400, "Invalid or expired consent request")
    return pending["verifier"]


def callback(ctx: Ctx, session: MutableMapping, code: str, state: str) -> None:
    verifier = check_state(ctx, session, state)
    if not code:
        raise ConsentFailed("missing_code")
    s = get_settings()
    try:
        with _http_client() as http:
            r = http.post(
                f"{_authority()}/token",
                data={
                    "client_id": s.entra_client_id,
                    "client_secret": s.entra_client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": _redirect_uri(),
                    "code_verifier": verifier,
                    "scope": ADMIN_SCOPES,
                },
            )
    except httpx.HTTPError as exc:
        logger.warning("onboarding consent token exchange failed: %s", type(exc).__name__)
        raise ConsentFailed("token_exchange") from None
    if r.status_code != 200:
        # The body may echo the code; log only the status and Microsoft's error code.
        try:
            err = r.json().get("error")
        except ValueError:
            err = None
        logger.warning("onboarding consent token exchange: HTTP %s %s", r.status_code, err)
        raise ConsentFailed("token_exchange")
    body = r.json()
    access_token = body.get("access_token")
    if not access_token:
        raise ConsentFailed("no_access_token")
    try:
        lifetime = min(int(body.get("expires_in", MAX_TOKEN_SECONDS)), MAX_TOKEN_SECONDS)
    except (TypeError, ValueError):
        lifetime = MAX_TOKEN_SECONDS
    ctx.db.execute(delete(OnboardingToken).where(OnboardingToken.user_id == ctx.user.id))
    ctx.db.add(
        OnboardingToken(
            user_id=ctx.user.id,
            token_ciphertext=crypto.encrypt_credentials({"access_token": access_token}),
            scopes=str(body.get("scope") or ADMIN_SCOPES)[:2000],
            expires_at=datetime.now(UTC) + timedelta(seconds=max(lifetime, 0)),
        )
    )
    ctx.db.flush()


def get_admin_token(ctx: Ctx) -> str:
    """The caller's own unexpired consent token, decrypted; 409 when there is none."""
    row = ctx.db.execute(
        select(OnboardingToken).where(
            OnboardingToken.user_id == ctx.user.id, OnboardingToken.expires_at > func.now()
        )
    ).scalar_one_or_none()
    if row is None:
        raise Conflict(EXPIRED_MESSAGE)
    return crypto.decrypt_credentials(row.token_ciphertext)["access_token"]


def discard(ctx: Ctx) -> None:
    ctx.db.execute(delete(OnboardingToken).where(OnboardingToken.user_id == ctx.user.id))
    ctx.db.flush()
