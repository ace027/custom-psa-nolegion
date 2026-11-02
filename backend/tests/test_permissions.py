"""Every role x every endpoint. Default is deny."""

import pytest

from app import permissions as P

ROLES = ["admin", "tech", "billing", "read_only"]


def test_matrix_shape():
    assert set(P.MATRIX) == set(P.ROLES)
    assert P.has_permission("admin", P.AUDIT_READ)
    assert not P.has_permission("tech", P.AUDIT_READ)
    assert not P.has_permission("unknown-role", P.ORG_READ)


def test_automation_permissions_admin_only():
    for perm in (P.APIKEY_MANAGE, P.AUTOMATION_MANAGE):
        assert P.has_permission("admin", perm)
        for role in ("tech", "billing", "read_only"):
            assert not P.has_permission(role, perm)
    assert P.APIKEY_MANAGE == "apikey:manage"
    assert P.AUTOMATION_MANAGE == "automation:manage"
    assert frozenset({P.USER_MANAGE, P.APIKEY_MANAGE, P.PORTAL_MANAGE}) == P.KEY_FORBIDDEN


def test_project_write_admin_and_tech_only():
    assert P.PROJECT_WRITE == "project:write"
    for role in ("admin", "tech"):
        assert P.has_permission(role, P.PROJECT_WRITE)
    for role in ("billing", "read_only"):
        assert not P.has_permission(role, P.PROJECT_WRITE)
    assert P.PROJECT_WRITE not in P.KEY_FORBIDDEN


def test_crm_permissions():
    assert P.CRM_READ == "crm:read"
    assert P.CRM_WRITE == "crm:write"
    for role in ROLES:
        assert P.has_permission(role, P.CRM_READ)
    for role in ("admin", "tech"):
        assert P.has_permission(role, P.CRM_WRITE)
    for role in ("billing", "read_only"):
        assert not P.has_permission(role, P.CRM_WRITE)
    assert not {P.CRM_READ, P.CRM_WRITE} & P.KEY_FORBIDDEN


def test_procurement_permissions():
    assert P.PROCUREMENT_READ == "procurement:read"
    assert P.PROCUREMENT_WRITE == "procurement:write"
    for role in ROLES:
        assert P.has_permission(role, P.PROCUREMENT_READ)
    for role in ("admin", "tech", "billing"):
        assert P.has_permission(role, P.PROCUREMENT_WRITE)
    assert not P.has_permission("read_only", P.PROCUREMENT_WRITE)
    assert not {P.PROCUREMENT_READ, P.PROCUREMENT_WRITE} & P.KEY_FORBIDDEN


@pytest.fixture
def seeded(admin, make_org):
    org = make_org()
    site = admin.post(f"/api/v1/organizations/{org['id']}/sites", json={"name": "HQ"}).json()
    contact = admin.post(f"/api/v1/organizations/{org['id']}/contacts", json={"name": "Pat"}).json()
    ticket = admin.post(
        "/api/v1/tickets", json={"organization_id": org["id"], "subject": "T"}
    ).json()
    wt = admin.get("/api/v1/work-types").json()[0]["id"]
    entry = admin.post(
        f"/api/v1/tickets/{ticket['id']}/time", json={"work_type_id": wt, "minutes": 5}
    ).json()
    extras = {
        path: admin.post(f"/api/v1/{path}", json=body).json()["id"]
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
        ("GET", "/api/v1/organizations", None, "read"),
        ("GET", f"/api/v1/organizations/{o}", None, "read"),
        ("GET", f"/api/v1/organizations/{o}/sites", None, "read"),
        ("GET", f"/api/v1/organizations/{o}/contacts", None, "read"),
        ("GET", "/api/v1/users", None, "read"),
        ("GET", "/api/v1/auth/me", None, "any"),
        ("POST", "/api/v1/organizations", {"name": "New"}, "write"),
        ("PATCH", f"/api/v1/organizations/{o}", {"notes": "n"}, "write"),
        ("POST", f"/api/v1/organizations/{o}/archive", None, "write"),
        ("POST", f"/api/v1/organizations/{o}/unarchive", None, "write"),
        ("POST", f"/api/v1/organizations/{o}/sites", {"name": "S2"}, "write"),
        ("PATCH", f"/api/v1/sites/{s}", {"city": "x"}, "write"),
        ("POST", f"/api/v1/sites/{s}/archive", None, "write"),
        ("POST", f"/api/v1/sites/{s}/unarchive", None, "write"),
        ("POST", f"/api/v1/organizations/{o}/contacts", {"name": "C2"}, "write"),
        ("PATCH", f"/api/v1/contacts/{c}", {"title": "x"}, "write"),
        ("POST", f"/api/v1/contacts/{c}/archive", None, "write"),
        ("POST", f"/api/v1/contacts/{c}/unarchive", None, "write"),
        (
            "POST",
            "/api/v1/users",
            {"email": "n@example.com", "display_name": "N", "role": "tech"},
            "admin",
        ),
        ("PATCH", "/api/v1/users/1", {"display_name": "Z"}, "admin"),
        ("GET", "/api/v1/audit", None, "admin"),
        # Phase 2
        ("GET", "/api/v1/tickets", None, "read"),
        ("GET", f"/api/v1/tickets/{t}", None, "read"),
        ("GET", f"/api/v1/tickets/{t}/notes", None, "read"),
        ("GET", f"/api/v1/tickets/{t}/time", None, "read"),
        ("GET", f"/api/v1/tickets/{t}/attachments", None, "read"),
        ("GET", "/api/v1/attachments/1/download", None, "file"),
        ("GET", "/api/v1/dashboard", None, "read"),
        ("GET", "/api/v1/settings", None, "read"),
        ("GET", "/api/v1/queues", None, "read"),
        ("GET", "/api/v1/categories", None, "read"),
        ("GET", "/api/v1/priorities", None, "read"),
        ("GET", "/api/v1/work-types", None, "read"),
        ("POST", "/api/v1/tickets", {"organization_id": o, "subject": "N"}, "write"),
        ("PATCH", f"/api/v1/tickets/{t}", {"subject": "S2"}, "write"),
        ("POST", f"/api/v1/tickets/{t}/notes", {"body": "n"}, "write"),
        (
            "POST",
            f"/api/v1/tickets/{t}/time",
            {"work_type_id": x["work-types"], "minutes": 5},
            "write",
        ),
        ("PATCH", f"/api/v1/time-entries/{e}", {"minutes": 6}, "write"),
        ("POST", f"/api/v1/time-entries/{e}/void", None, "write"),
        ("PATCH", "/api/v1/settings", {"sla_at_risk_percent": 30}, "admin"),
        ("GET", "/api/v1/mail/status", None, "admin"),
        ("POST", "/api/v1/queues", {"name": "Q2"}, "admin"),
        ("PATCH", f"/api/v1/queues/{x['queues']}", {"name": "Q3"}, "admin"),
        ("POST", f"/api/v1/queues/{x['queues']}/archive", None, "admin"),
        ("POST", f"/api/v1/queues/{x['queues']}/unarchive", None, "admin"),
        ("POST", "/api/v1/categories", {"name": "C2"}, "admin"),
        ("PATCH", f"/api/v1/categories/{x['categories']}", {"name": "C3"}, "admin"),
        ("POST", f"/api/v1/categories/{x['categories']}/archive", None, "admin"),
        ("POST", f"/api/v1/categories/{x['categories']}/unarchive", None, "admin"),
        ("POST", "/api/v1/work-types", {"name": "W2"}, "admin"),
        ("PATCH", f"/api/v1/work-types/{x['work-types']}", {"name": "W3"}, "admin"),
        ("POST", f"/api/v1/work-types/{x['work-types']}/archive", None, "admin"),
        ("POST", f"/api/v1/work-types/{x['work-types']}/unarchive", None, "admin"),
        ("POST", "/api/v1/priorities", {"name": "P2", "rank": 7}, "admin"),
        ("PATCH", f"/api/v1/priorities/{x['priorities']}", {"rank": 6}, "admin"),
        ("POST", f"/api/v1/priorities/{x['priorities']}/archive", None, "admin"),
        ("POST", f"/api/v1/priorities/{x['priorities']}/unarchive", None, "admin"),
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
            f"/api/v1/tickets/{seeded['ticket']}/time", json={"work_type_id": wt, "minutes": 5}
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
    assert ro.post("/api/v1/organizations", json={"name": "x"}).status_code == 403
    items = admin.get("/api/v1/audit", params={"action": "auth.denied"}).json()["items"]
    assert len(items) == 1
    assert items[0]["actor_id"] == ro.user["id"]
    assert items[0]["detail"]["permission"] == "org:write"


def test_missing_csrf_header_is_rejected(admin):
    admin.headers.pop("X-Requested-With")
    assert admin.post("/api/v1/organizations", json={"name": "x"}).status_code == 403
    assert admin.get("/api/v1/organizations").status_code == 200  # safe methods unaffected
