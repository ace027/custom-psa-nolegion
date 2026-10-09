from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app import repositories as repo
from app.auth import oidc
from app.db import new_session


def auth_events(admin, prefix="auth."):
    return admin.get("/api/audit", params={"action": prefix, "limit": 200}).json()["items"]


# ---- sessions & dev login ----
def test_login_me_logout(admin):
    me = admin.get("/api/auth/me").json()
    assert me["email"] == "admin@example.com" and "audit:read" in me["permissions"]
    assert me["last_login_at"]
    assert admin.post("/api/auth/logout").status_code == 204
    assert admin.get("/api/auth/me").status_code == 401


def test_session_token_is_stored_hashed(admin, owner):
    cookie = admin.cookies.get("psa_session")
    stored = [r[0] for r in owner.execute(text("SELECT token_hash FROM sessions"))]
    assert cookie and cookie not in stored and len(stored[0]) == 64


def test_expired_session_is_rejected(admin, owner):
    owner.execute(
        text("UPDATE sessions SET expires_at = :t"), {"t": datetime.now(UTC) - timedelta(minutes=1)}
    )
    assert admin.get("/api/auth/me").status_code == 401


def test_garbage_cookie_is_rejected(anon):
    anon.cookies.set("psa_session", "nope")
    assert anon.get("/api/auth/me").status_code == 401


def test_login_and_failure_events_are_recorded(admin, anon):
    r = anon.post("/api/auth/dev-login", json={"email": "ghost@example.com"})
    assert r.status_code == 403
    events = auth_events(admin)
    actions = [e["action"] for e in events]
    assert "auth.login" in actions and "auth.login_failed" in actions
    failed = next(e for e in events if e["action"] == "auth.login_failed")
    assert failed["actor_type"] == "anonymous" and failed["detail"]["email"] == "ghost@example.com"


def test_inactive_user_cannot_dev_login(admin, make_user, anon):
    u = make_user("tech", "gone@example.com", active=False)
    assert anon.post("/api/auth/dev-login", json={"email": u["email"]}).status_code == 403


def test_logout_is_audited(admin):
    admin.post("/api/auth/logout")
    from tests.conftest import RouteRecorder  # noqa: F401  (import keeps recorder wired)

    with new_session() as db:
        assert (
            db.execute(
                text("SELECT count(*) FROM audit_log WHERE action='auth.logout'")
            ).scalar_one()
            == 1
        )


def test_dev_login_disabled_in_production_or_when_flag_off(anon, make_user, monkeypatch):
    from app.config import get_settings

    user = make_user("admin", "p@example.com")
    s = get_settings()
    monkeypatch.setattr(s, "environment", "production")
    assert anon.post("/api/auth/dev-login", json={"email": user["email"]}).status_code == 404
    monkeypatch.setattr(s, "environment", "development")
    monkeypatch.setattr(s, "dev_login_enabled", False)
    assert anon.post("/api/auth/dev-login", json={"email": user["email"]}).status_code == 404


# ---- OIDC claim mapping ----
CLAIMS = {"tid": "tenant-1", "oid": "oid-1", "email": "Tech@Example.com"}


@pytest.fixture
def db():
    with new_session() as s:
        yield s
        s.rollback()


def test_claims_bind_oid_to_preprovisioned_user(make_user, db):
    make_user("tech", "tech@example.com")
    user = oidc.resolve_user_from_claims(db, CLAIMS)
    assert user.entra_oid == "oid-1" and user.role == "tech"
    db.commit()
    # subsequent logins match on oid even if the email changed in Entra
    again = oidc.resolve_user_from_claims(db, {**CLAIMS, "email": "renamed@example.com"})
    assert again.id == user.id


def test_claims_fall_back_to_preferred_username(make_user, db):
    make_user("tech", "tech@example.com")
    claims = {"tid": "tenant-1", "oid": "o2", "preferred_username": "tech@example.com"}
    assert oidc.resolve_user_from_claims(db, claims).entra_oid == "o2"


@pytest.mark.parametrize(
    "claims,reason",
    [
        ({**CLAIMS, "tid": "other-tenant"}, "wrong_tenant"),
        ({"tid": "tenant-1", "email": "x@example.com"}, "missing_oid"),
        ({"tid": "tenant-1", "oid": "o"}, "missing_email"),
        ({**CLAIMS, "email": "stranger@example.com"}, "not_provisioned"),
    ],
)
def test_claims_denied(make_user, db, claims, reason):
    make_user("tech", "tech@example.com")
    with pytest.raises(oidc.LoginDenied) as e:
        oidc.resolve_user_from_claims(db, claims)
    assert e.value.reason == reason


def test_claims_denied_for_inactive_and_mismatched_oid(make_user, owner_engine, db):
    make_user("tech", "tech@example.com", active=False)
    with pytest.raises(oidc.LoginDenied) as e:
        oidc.resolve_user_from_claims(db, CLAIMS)
    assert e.value.reason == "inactive"
    assert db.execute(text("SELECT entra_oid FROM users")).scalar_one() is None  # not bound
    db.rollback()
    with owner_engine.begin() as c:  # committed, so it cannot block the app session
        c.execute(text("UPDATE users SET is_active = true, entra_oid = 'someone-else'"))
    with pytest.raises(oidc.LoginDenied) as e:
        oidc.resolve_user_from_claims(db, CLAIMS)
    assert e.value.reason == "oid_mismatch"


# ---- OIDC callback route (token exchange mocked) ----
class FakeEntra:
    def __init__(self, claims=None, boom=False):
        self.claims, self.boom = claims, boom

    async def authorize_access_token(self, request):
        if self.boom:
            raise RuntimeError("bad state")
        return {"userinfo": self.claims}


class FakeOAuth:
    def __init__(self, entra):
        self.entra = entra


def test_callback_success_creates_session_and_audit(anon, admin, make_user, monkeypatch):
    make_user("tech", "tech@example.com")
    monkeypatch.setattr(oidc, "get_oauth", lambda: FakeOAuth(FakeEntra(CLAIMS)))
    r = anon.get("/api/auth/callback", follow_redirects=False)
    assert r.status_code == 303 and "psa_session" in r.cookies
    assert anon.get("/api/auth/me").json()["email"] == "tech@example.com"
    assert any(
        e["detail"] is None and e["action"] == "auth.login" and e["actor_id"]
        for e in auth_events(admin)
    )


def test_callback_denied_logs_failure(anon, admin, monkeypatch):
    monkeypatch.setattr(oidc, "get_oauth", lambda: FakeOAuth(FakeEntra(CLAIMS)))
    r = anon.get("/api/auth/callback", follow_redirects=False)
    assert r.status_code == 403 and "psa_session" not in r.cookies
    failed = [e for e in auth_events(admin) if e["action"] == "auth.login_failed"]
    assert failed[0]["detail"]["reason"] == "not_provisioned"


def test_callback_token_exchange_failure(anon, admin, monkeypatch):
    monkeypatch.setattr(oidc, "get_oauth", lambda: FakeOAuth(FakeEntra(boom=True)))
    assert anon.get("/api/auth/callback", follow_redirects=False).status_code == 403
    failed = [e for e in auth_events(admin) if e["action"] == "auth.login_failed"]
    assert failed[0]["detail"]["reason"] == "token_exchange"


def test_login_redirects_to_entra(anon, monkeypatch):
    from starlette.responses import RedirectResponse

    class E:
        async def authorize_redirect(self, request, redirect_uri):
            assert redirect_uri.endswith("/api/auth/callback")
            return RedirectResponse("https://login.microsoftonline.com/x", status_code=302)

    monkeypatch.setattr(oidc, "get_oauth", lambda: FakeOAuth(E()))
    r = anon.get("/api/auth/login", follow_redirects=False)
    assert r.status_code == 302 and "login.microsoftonline.com" in r.headers["location"]


def test_login_and_callback_503_when_entra_unconfigured(anon, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "entra_tenant_id", "")
    assert anon.get("/api/auth/login", follow_redirects=False).status_code == 503
    assert anon.get("/api/auth/callback", follow_redirects=False).status_code == 503


def test_repo_user_lookup_helpers(make_user, db):
    u = make_user("tech", "look@example.com")
    assert repo.get_user_by_email(db, "LOOK@example.com").id == u["id"]
    assert repo.get_user_by_oid(db, "none") is None
