import base64
import hashlib
import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import text

from app import crypto, onboarding_auth
from app import db as dbmod
from app import permissions as P
from app.config import get_settings
from app.deps import Ctx
from app.errors import Conflict
from app.models import User
from app.scope import Scope

TOKEN = "eyJ-admin-graph-token-never-shown"


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(get_settings(), "onboarding_enabled", True)


@pytest.fixture
def token_endpoint(monkeypatch):
    calls: list[httpx.Request] = []
    reply = {"status": 200, "json": {"access_token": TOKEN, "expires_in": 7200, "scope": "x"}}

    def handler(request):
        calls.append(request)
        return httpx.Response(reply["status"], json=reply["json"])

    monkeypatch.setattr(
        onboarding_auth,
        "_http_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return calls, reply


def start(client) -> dict:
    r = client.get("/api/v1/onboarding/consent/start")
    assert r.status_code == 200, r.text
    url = urlparse(r.json()["url"])
    q = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert url.netloc == "login.microsoftonline.com"
    assert url.path == "/tenant-1/oauth2/v2.0/authorize"
    return q


def callback(client, **params):
    return client.get("/api/v1/onboarding/consent/callback", params=params, follow_redirects=False)


def ctx_for(user_id: int):
    db = dbmod.new_session()
    return Ctx(db=db, user=db.get(User, user_id), scope=Scope.all())


def test_happy_path_stores_only_ciphertext(admin, enabled, token_endpoint, owner, caplog):
    caplog.set_level(logging.DEBUG)
    calls, _ = token_endpoint
    q = start(admin)
    assert q["client_id"] == "client-1" and q["prompt"] == "consent"
    assert q["scope"] == onboarding_auth.ADMIN_SCOPES
    assert q["redirect_uri"].endswith("/api/v1/onboarding/consent/callback")
    assert q["code_challenge_method"] == "S256" and len(q["state"]) >= 43

    r = callback(admin, code="auth-code-1", state=q["state"])
    assert r.status_code == 303
    assert r.headers["location"].endswith("/setup?consent=ok")
    assert TOKEN not in r.text and TOKEN not in str(r.headers)

    (req,) = calls
    form = parse_qs(req.content.decode())
    assert req.url.path == "/tenant-1/oauth2/v2.0/token"
    assert form["code"] == ["auth-code-1"] and form["client_secret"] == ["secret-1"]
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(form["code_verifier"][0].encode()).digest()
    ).rstrip(b"=")
    assert challenge.decode() == q["code_challenge"]

    row = owner.execute(text("SELECT * FROM onboarding_tokens")).one()
    assert row.user_id == admin.user["id"]
    assert TOKEN not in row.token_ciphertext
    assert crypto.decrypt_credentials(row.token_ciphertext) == {"access_token": TOKEN}
    assert row.expires_at <= datetime.now(UTC) + timedelta(minutes=60, seconds=5)  # capped

    audit_rows = owner.execute(
        text("SELECT action, detail::text AS d FROM audit_log WHERE action LIKE 'onboarding.%'")
    ).all()
    assert {a.action for a in audit_rows} == {
        "onboarding.consent_started",
        "onboarding.consent_granted",
    }
    assert all(TOKEN not in (a.d or "") for a in audit_rows)
    assert TOKEN not in caplog.text
    assert TOKEN not in str(admin.cookies)

    ctx = ctx_for(admin.user["id"])
    try:
        assert onboarding_auth.get_admin_token(ctx) == TOKEN
        onboarding_auth.discard(ctx)
        with pytest.raises(Conflict, match="Sign in to Microsoft again"):
            onboarding_auth.get_admin_token(ctx)
        ctx.db.commit()
    finally:
        ctx.db.close()
    assert owner.execute(text("SELECT count(*) FROM onboarding_tokens")).scalar_one() == 0


def test_second_consent_replaces_row(admin, enabled, token_endpoint, owner):
    for _ in range(2):
        q = start(admin)
        assert callback(admin, code="c", state=q["state"]).status_code == 303
    assert owner.execute(text("SELECT count(*) FROM onboarding_tokens")).scalar_one() == 1


def test_expired_token_asks_to_sign_in_again(admin, enabled, token_endpoint, owner):
    q = start(admin)
    callback(admin, code="c", state=q["state"])
    owner.execute(text("UPDATE onboarding_tokens SET expires_at = now() - interval '1 second'"))
    ctx = ctx_for(admin.user["id"])
    try:
        with pytest.raises(Conflict, match="Sign in to Microsoft again"):
            onboarding_auth.get_admin_token(ctx)
    finally:
        ctx.db.close()


def test_bad_state_rejected_and_cleared(admin, enabled, token_endpoint, owner):
    calls, _ = token_endpoint
    q = start(admin)
    assert callback(admin, code="c", state="forged").status_code == 400
    assert callback(admin, code="c", state=q["state"]).status_code == 400  # one-time
    assert callback(admin, code="c").status_code == 400
    assert calls == []
    assert owner.execute(text("SELECT count(*) FROM onboarding_tokens")).scalar_one() == 0
    assert (
        owner.execute(
            text("SELECT count(*) FROM audit_log WHERE action = 'onboarding.consent_rejected'")
        ).scalar_one()
        == 3
    )


def test_expired_state_rejected(admin, enabled, token_endpoint, monkeypatch):
    monkeypatch.setattr(onboarding_auth, "STATE_TTL_SECONDS", -1)
    q = start(admin)
    assert callback(admin, code="c", state=q["state"]).status_code == 400


def test_foreign_state_rejected(admin, login, enabled, token_endpoint, make_user):
    q = start(admin)
    other = login("admin", "admin2@example.com")
    other.cookies.set("psa_oidc_state", admin.cookies.get("psa_oidc_state"))
    assert callback(other, code="c", state=q["state"]).status_code == 400


def test_consent_denied_at_microsoft(admin, enabled, token_endpoint):
    calls, _ = token_endpoint
    start(admin)
    r = callback(admin, error="access_denied", error_description="user declined")
    assert r.status_code == 303 and r.headers["location"].endswith("/setup?consent=error")
    assert calls == []


def test_token_exchange_failure_redirects_error(admin, enabled, token_endpoint, owner):
    _, reply = token_endpoint
    reply.update(status=400, json={"error": "invalid_grant"})
    q = start(admin)
    r = callback(admin, code="c", state=q["state"])
    assert r.headers["location"].endswith("/setup?consent=error")
    assert owner.execute(text("SELECT count(*) FROM onboarding_tokens")).scalar_one() == 0
    detail = owner.execute(
        text("SELECT detail FROM audit_log WHERE action = 'onboarding.consent_failed'")
    ).scalar_one()
    assert detail == {"reason": "token_exchange"}


@pytest.mark.parametrize("role", ["tech", "manager", "billing"])
def test_non_admin_forbidden(login, enabled, role):
    client = login(role)
    assert client.get("/api/v1/onboarding/consent/start").status_code == 403
    assert callback(client, code="c", state="s").status_code == 403


def test_role_check_beyond_permission(login, enabled, monkeypatch):
    # Defense in depth: even a role granted CONFIG_MANAGE must be 'admin'.
    monkeypatch.setitem(P.MATRIX, "manager", P.MATRIX["manager"] | {P.CONFIG_MANAGE})
    client = login("manager")
    assert client.get("/api/v1/onboarding/consent/start").status_code == 403
    assert callback(client, error="x").status_code == 403


def test_disabled_returns_404(admin, anon):
    assert admin.get("/api/v1/onboarding/consent/start").status_code == 404
    assert callback(admin, code="c", state="s").status_code == 404
    assert anon.get("/api/v1/onboarding/consent/start").status_code == 401
