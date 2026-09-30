"""Every role x every endpoint. Default is deny."""

import pytest

from app import permissions as P

ROLES = ["admin", "tech", "billing", "read_only"]


def test_matrix_shape():
    assert set(P.MATRIX) == set(P.ROLES)
    assert P.has_permission("admin", P.AUDIT_READ)
    assert not P.has_permission("tech", P.AUDIT_READ)
    assert not P.has_permission("unknown-role", P.ORG_READ)


@pytest.fixture
def seeded(admin, make_org):
    org = make_org()
    site = admin.post(f"/api/organizations/{org['id']}/sites", json={"name": "HQ"}).json()
    contact = admin.post(f"/api/organizations/{org['id']}/contacts", json={"name": "Pat"}).json()
    return {"org": org["id"], "site": site["id"], "contact": contact["id"]}


def calls(ids):
    o, s, c = ids["org"], ids["site"], ids["contact"]
    # (method, path, json, permission needed)
    return [
        ("GET", "/api/organizations", None, "read"),
        ("GET", f"/api/organizations/{o}", None, "read"),
        ("GET", f"/api/organizations/{o}/sites", None, "read"),
        ("GET", f"/api/organizations/{o}/contacts", None, "read"),
        ("GET", "/api/users", None, "read"),
        ("GET", "/api/auth/me", None, "any"),
        ("POST", "/api/organizations", {"name": "New"}, "write"),
        ("PATCH", f"/api/organizations/{o}", {"notes": "n"}, "write"),
        ("POST", f"/api/organizations/{o}/archive", None, "write"),
        ("POST", f"/api/organizations/{o}/unarchive", None, "write"),
        ("POST", f"/api/organizations/{o}/sites", {"name": "S2"}, "write"),
        ("PATCH", f"/api/sites/{s}", {"city": "x"}, "write"),
        ("POST", f"/api/sites/{s}/archive", None, "write"),
        ("POST", f"/api/sites/{s}/unarchive", None, "write"),
        ("POST", f"/api/organizations/{o}/contacts", {"name": "C2"}, "write"),
        ("PATCH", f"/api/contacts/{c}", {"title": "x"}, "write"),
        ("POST", f"/api/contacts/{c}/archive", None, "write"),
        ("POST", f"/api/contacts/{c}/unarchive", None, "write"),
        (
            "POST",
            "/api/users",
            {"email": "n@example.com", "display_name": "N", "role": "tech"},
            "admin",
        ),
        ("PATCH", "/api/users/1", {"display_name": "Z"}, "admin"),
        ("GET", "/api/audit", None, "admin"),
    ]


ALLOWED = {
    "any": set(ROLES),
    "read": set(ROLES),
    "write": {"admin", "tech"},
    "admin": {"admin"},
}


@pytest.mark.parametrize("role", ROLES)
def test_role_matrix(role, login, seeded):
    client = login(role)
    for method, path, body, need in calls(seeded):
        r = client.request(method, path, json=body)
        if role in ALLOWED[need]:
            assert r.status_code < 400, (role, method, path, r.status_code, r.text)
        else:
            assert r.status_code == 403, (role, method, path, r.status_code)


def test_unauthenticated_gets_401_everywhere(anon, seeded):
    for method, path, body, _ in calls(seeded):
        assert anon.request(method, path, json=body).status_code == 401, (method, path)


def test_denied_attempts_are_logged(admin, login):
    ro = login("read_only")
    assert ro.post("/api/organizations", json={"name": "x"}).status_code == 403
    items = admin.get("/api/audit", params={"action": "auth.denied"}).json()["items"]
    assert len(items) == 1
    assert items[0]["actor_id"] == ro.user["id"]
    assert items[0]["detail"]["permission"] == "org:write"


def test_missing_csrf_header_is_rejected(admin):
    admin.headers.pop("X-Requested-With")
    assert admin.post("/api/organizations", json={"name": "x"}).status_code == 403
    assert admin.get("/api/organizations").status_code == 200  # safe methods unaffected
