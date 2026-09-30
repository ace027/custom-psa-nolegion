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
    ticket = admin.post("/api/tickets", json={"organization_id": org["id"], "subject": "T"}).json()
    wt = admin.get("/api/work-types").json()[0]["id"]
    entry = admin.post(
        f"/api/tickets/{ticket['id']}/time", json={"work_type_id": wt, "minutes": 5}
    ).json()
    extras = {
        path: admin.post(f"/api/{path}", json=body).json()["id"]
        for path, body in (
            ("queues", {"name": "Extra"}),
            ("categories", {"name": "Extra"}),
            ("work-types", {"name": "Extra"}),
            ("priorities", {"name": "Extra", "rank": 8}),
        )
    }
    return {
        "org": org["id"],
        "site": site["id"],
        "contact": contact["id"],
        "ticket": ticket["id"],
        "entry": entry["id"],
        "extras": extras,
    }


def calls(ids):
    o, s, c = ids["org"], ids["site"], ids["contact"]
    t, e, x = ids["ticket"], ids["entry"], ids["extras"]
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
        # Phase 2
        ("GET", "/api/tickets", None, "read"),
        ("GET", f"/api/tickets/{t}", None, "read"),
        ("GET", f"/api/tickets/{t}/notes", None, "read"),
        ("GET", f"/api/tickets/{t}/time", None, "read"),
        ("GET", f"/api/tickets/{t}/attachments", None, "read"),
        ("GET", "/api/attachments/1/download", None, "file"),
        ("GET", "/api/dashboard", None, "read"),
        ("GET", "/api/settings", None, "read"),
        ("GET", "/api/queues", None, "read"),
        ("GET", "/api/categories", None, "read"),
        ("GET", "/api/priorities", None, "read"),
        ("GET", "/api/work-types", None, "read"),
        ("POST", "/api/tickets", {"organization_id": o, "subject": "N"}, "write"),
        ("PATCH", f"/api/tickets/{t}", {"subject": "S2"}, "write"),
        ("POST", f"/api/tickets/{t}/notes", {"body": "n"}, "write"),
        (
            "POST",
            f"/api/tickets/{t}/time",
            {"work_type_id": x["work-types"], "minutes": 5},
            "write",
        ),
        ("PATCH", f"/api/time-entries/{e}", {"minutes": 6}, "write"),
        ("POST", f"/api/time-entries/{e}/void", None, "write"),
        ("PATCH", "/api/settings", {"sla_at_risk_percent": 30}, "admin"),
        ("GET", "/api/mail/status", None, "admin"),
        ("POST", "/api/queues", {"name": "Q2"}, "admin"),
        ("PATCH", f"/api/queues/{x['queues']}", {"name": "Q3"}, "admin"),
        ("POST", f"/api/queues/{x['queues']}/archive", None, "admin"),
        ("POST", f"/api/queues/{x['queues']}/unarchive", None, "admin"),
        ("POST", "/api/categories", {"name": "C2"}, "admin"),
        ("PATCH", f"/api/categories/{x['categories']}", {"name": "C3"}, "admin"),
        ("POST", f"/api/categories/{x['categories']}/archive", None, "admin"),
        ("POST", f"/api/categories/{x['categories']}/unarchive", None, "admin"),
        ("POST", "/api/work-types", {"name": "W2"}, "admin"),
        ("PATCH", f"/api/work-types/{x['work-types']}", {"name": "W3"}, "admin"),
        ("POST", f"/api/work-types/{x['work-types']}/archive", None, "admin"),
        ("POST", f"/api/work-types/{x['work-types']}/unarchive", None, "admin"),
        ("POST", "/api/priorities", {"name": "P2", "rank": 7}, "admin"),
        ("PATCH", f"/api/priorities/{x['priorities']}", {"rank": 6}, "admin"),
        ("POST", f"/api/priorities/{x['priorities']}/archive", None, "admin"),
        ("POST", f"/api/priorities/{x['priorities']}/unarchive", None, "admin"),
    ]


ALLOWED = {
    "any": set(ROLES),
    "read": set(ROLES),
    "write": {"admin", "tech"},
    "admin": {"admin"},
    "file": set(ROLES),
}


@pytest.mark.parametrize("role", ROLES)
def test_role_matrix(role, login, seeded):
    client = login(role)
    if role in ("admin", "tech"):  # editing time is limited to your own entries (or admin)
        wt = seeded["extras"]["work-types"]
        seeded["entry"] = client.post(
            f"/api/tickets/{seeded['ticket']}/time", json={"work_type_id": wt, "minutes": 5}
        ).json()["id"]
    for method, path, body, need in calls(seeded):
        r = client.request(method, path, json=body)
        if need == "file":  # everyone may try; the file itself does not exist in this test
            assert r.status_code == 404, (role, path, r.status_code)
        elif role in ALLOWED[need]:
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
