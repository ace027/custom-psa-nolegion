"""API keys: creation rules, bearer authentication, rejection cases, audit attribution."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from tests.conftest import RouteRecorder


@pytest.fixture
def mk(admin):
    def _mk(perms=("ticket:read",), **kw):
        r = admin.post("/api/api-keys", json={"name": "n8n", "permissions": list(perms), **kw})
        assert r.status_code == 201, r.text
        return r.json()

    return _mk


def bearer(token: str) -> TestClient:
    # No X-Requested-With and no cookie: only the bearer header
    return TestClient(RouteRecorder(app), headers={"Authorization": f"Bearer {token}"})


def audit_rows(owner, action):
    return owner.execute(
        text("SELECT detail::text AS d, actor_id FROM audit_log WHERE action = :a ORDER BY id"),
        {"a": action},
    ).all()


def test_create_list_revoke_never_exposes_hash(admin, mk, owner):
    made = mk(("ticket:read", "ticket:write", "ticket:read"))
    key, token = made["key"], made["token"]
    assert token.startswith(f"psa_{key['prefix']}_")
    assert key["permissions"] == ["ticket:read", "ticket:write"]
    assert key["state"] == "active" and key["owner_id"] == admin.user["id"]
    assert "key_hash" not in key and "hash" not in str(key)
    listed = admin.get("/api/api-keys").json()
    assert [k["id"] for k in listed] == [key["id"]]
    assert token not in admin.get("/api/api-keys").text
    r = admin.post(f"/api/api-keys/{key['id']}/revoke")
    assert r.status_code == 200 and r.json()["state"] == "revoked"
    assert admin.post(f"/api/api-keys/{key['id']}/revoke").status_code == 409
    assert admin.post("/api/api-keys/9999/revoke").status_code == 404
    created = audit_rows(owner, "api_key.created")
    assert len(created) == 1 and token not in created[0].d and "key_hash" not in created[0].d
    assert len(audit_rows(owner, "api_key.revoked")) == 1
    stored = owner.execute(text("SELECT key_hash FROM api_keys")).scalar_one()
    assert len(stored) == 64 and stored != token


@pytest.mark.parametrize(
    "perms",
    [
        ["user:manage"],
        ["apikey:manage"],
        ["portal:manage"],
        ["nope:nothing"],
        [],
        ["ticket:read", "user:manage"],
    ],
)
def test_forbidden_or_invalid_permissions_409(admin, perms):
    r = admin.post("/api/api-keys", json={"name": "x", "permissions": perms})
    assert r.status_code == 409, r.text


@pytest.mark.parametrize("days", [0, 731])
def test_expiry_bounds_422(admin, days):
    r = admin.post(
        "/api/api-keys",
        json={"name": "x", "permissions": ["ticket:read"], "expires_in_days": days},
    )
    assert r.status_code == 422


def test_bearer_read_and_write_without_csrf_header(mk, org_ctx, owner):
    token = mk(("ticket:read", "ticket:write"))["token"]
    c = bearer(token)
    assert c.get("/api/tickets").status_code == 200
    r = c.post("/api/tickets", json={"organization_id": org_ctx["org"], "subject": "via key"})
    assert r.status_code == 201, r.text
    rows = audit_rows(owner, "ticket.create")
    assert rows and '"api_key_id"' in rows[-1].d


def test_scope_enforced_and_denial_audited(mk, org_ctx, owner):
    made = mk(("ticket:read",))
    c = bearer(made["token"])
    r = c.post("/api/tickets", json={"organization_id": org_ctx["org"], "subject": "nope"})
    assert r.status_code == 403
    rows = audit_rows(owner, "auth.denied")
    assert rows and f'"api_key_id": {made["key"]["id"]}' in rows[-1].d


def test_key_cannot_use_other_perms_even_if_owner_has_them(mk):
    c = bearer(mk(("ticket:read",))["token"])
    assert c.get("/api/users").status_code == 403


def test_bearer_to_authenticated_only_and_apikey_routes_403(mk):
    c = bearer(mk(("ticket:read",))["token"])
    assert c.get("/api/auth/me").status_code == 403
    assert c.get("/api/api-keys").status_code == 403
    assert (
        c.post("/api/api-keys", json={"name": "x", "permissions": ["ticket:read"]}).status_code
        == 403
    )


def test_unknown_malformed_tokens_401_and_audited_without_token(mk, owner):
    mk()
    unknown = "psa_deadbeef_" + "A" * 43
    for tok in (unknown, "psa_short", "psa_zzzzzzzz_" + "A" * 30):
        assert bearer(tok).get("/api/tickets").status_code == 401
    rows = audit_rows(owner, "auth.api_key_rejected")
    assert len(rows) == 3
    assert all(unknown not in r.d and "A" * 20 not in r.d for r in rows)


def test_revoked_expired_deactivated_demoted(admin, mk, owner):
    # revoked
    k = mk()
    admin.post(f"/api/api-keys/{k['key']['id']}/revoke")
    assert bearer(k["token"]).get("/api/tickets").status_code == 401
    # expired
    k = mk()
    owner.execute(
        text("UPDATE api_keys SET expires_at = now() - interval '1 day' WHERE id=:i"),
        {"i": k["key"]["id"]},
    )
    assert bearer(k["token"]).get("/api/tickets").status_code == 401
    assert admin.get("/api/api-keys").json()[0]["state"] in ("expired", "active")
    # demoted: loses ticket:write -> 403, still reads
    k = mk(("ticket:read", "ticket:write"))
    c = bearer(k["token"])
    assert c.get("/api/tickets").status_code == 200
    owner.execute(text("UPDATE users SET role='read_only' WHERE id=:i"), {"i": admin.user["id"]})
    assert c.post("/api/tickets", json={"organization_id": 1, "subject": "x"}).status_code == 403
    assert c.get("/api/tickets").status_code == 200
    # deactivated
    owner.execute(text("UPDATE users SET is_active=false WHERE id=:i"), {"i": admin.user["id"]})
    assert c.get("/api/tickets").status_code == 401


def test_cookie_post_still_needs_csrf_header(admin):
    bare = TestClient(RouteRecorder(app))
    bare.cookies.update(admin.cookies)
    r = bare.post("/api/api-keys", json={"name": "x", "permissions": ["ticket:read"]})
    assert r.status_code == 403
    assert "X-Requested-With" in r.text


def test_last_used_is_throttled(mk, owner):
    k = mk()
    c = bearer(k["token"])
    q = text("SELECT last_used_at FROM api_keys WHERE id=:i")
    assert c.get("/api/tickets").status_code == 200
    first = owner.execute(q, {"i": k["key"]["id"]}).scalar_one()
    assert first is not None
    assert c.get("/api/tickets").status_code == 200
    assert owner.execute(q, {"i": k["key"]["id"]}).scalar_one() == first
    owner.execute(
        text("UPDATE api_keys SET last_used_at = now() - interval '6 minutes' WHERE id=:i"),
        {"i": k["key"]["id"]},
    )
    old = owner.execute(q, {"i": k["key"]["id"]}).scalar_one()
    assert c.get("/api/tickets").status_code == 200
    assert owner.execute(q, {"i": k["key"]["id"]}).scalar_one() > old


def test_non_psa_authorization_falls_through_to_cookie(admin):
    r = admin.get("/api/tickets", headers={"Authorization": "Bearer something-else"})
    assert r.status_code == 200
