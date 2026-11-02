"""Role-by-endpoint matrix: which staff role reaches each finance, procurement, settings and admin
area (phase 16 decisions). Allowed means the permission check passed (any status but 401/403);
writes send an empty body, so an allowed write stops at validation and changes nothing."""

import re

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from tests.conftest import RouteRecorder

ROLES = ("admin", "billing", "manager", "tech", "read_only")
ALL = set(ROLES)
FINANCE = {"admin", "billing", "manager"}  # invoice:read
PROCUREMENT = {"admin", "billing"}
SERVICE = {"admin", "manager"}  # service:configure, audit, approvals
STAFF_WRITE = {"admin", "billing", "manager", "tech"}  # charge:write

# (area, method, path, roles allowed); {org} is a real organization id
CASES = [
    ("invoices", "GET", "/invoices", FINANCE),
    ("invoices", "POST", "/invoices", {"admin", "billing"}),
    ("invoice runs", "GET", "/billing-runs", FINANCE),
    ("finalize", "POST", "/invoices/1/finalize", {"admin", "billing"}),
    ("payments", "GET", "/payments", FINANCE),
    ("payments", "POST", "/payments", {"admin", "billing"}),
    ("receivables", "GET", "/receivables", FINANCE),
    ("notices", "GET", "/billing-notices", FINANCE),
    ("statements", "GET", "/organizations/{org}/statements", FINANCE),
    ("statements", "POST", "/organizations/{org}/statements", {"admin", "billing"}),
    ("client billing terms", "GET", "/organizations/{org}/billing", FINANCE),
    ("credit memos", "GET", "/credit-memos", FINANCE),
    ("credit memos", "POST", "/credit-memos", {"admin", "billing"}),
    ("late fees", "GET", "/late-fees/applied", FINANCE),
    ("aging report", "GET", "/reports/aging", FINANCE),
    ("profitability report", "GET", "/reports/profitability", FINANCE),
    ("vendors", "GET", "/procurement/vendors", PROCUREMENT),
    ("vendors", "POST", "/procurement/vendors", PROCUREMENT),
    ("purchase orders", "GET", "/procurement/purchase-orders", PROCUREMENT),
    ("purchase orders", "POST", "/procurement/purchase-orders", PROCUREMENT),
    ("inventory", "GET", "/procurement/inventory", PROCUREMENT),
    ("client inventory", "GET", "/procurement/organizations/{org}/inventory", PROCUREMENT),
    ("products", "GET", "/products", ALL),
    ("products", "POST", "/products", {"admin", "billing"}),
    ("rates", "GET", "/billing/work-types", ALL),
    ("agreements", "GET", "/agreements", ALL),
    ("ticket charges", "GET", "/product-charges", ALL),
    ("ticket charges", "POST", "/product-charges", STAFF_WRITE),
    ("queues", "GET", "/queues", ALL),
    ("queues", "POST", "/queues", SERVICE),
    ("work types", "POST", "/work-types", SERVICE),
    ("statuses", "POST", "/ticket-statuses", SERVICE),
    ("holidays", "POST", "/holidays", SERVICE),
    ("general settings", "PATCH", "/settings", {"admin"}),
    ("mail status", "GET", "/mail/status", {"admin"}),
    ("CRM stages", "POST", "/crm/stages", {"admin"}),
    ("users", "GET", "/users", ALL),
    ("users", "POST", "/users", {"admin"}),
    ("audit log", "GET", "/audit", SERVICE),
    ("timesheet approval", "GET", "/timesheets", SERVICE),
    ("timesheet approval", "POST", "/timesheet/approve", SERVICE),
    ("time-off approval", "POST", "/time-off/1/approve", SERVICE),
    ("API keys", "GET", "/api-keys", {"admin"}),
]


@pytest.fixture
def clients(login):
    return {role: login(role) for role in ROLES}


def call(client: TestClient, method: str, path: str):
    kw = {} if method in ("GET", "DELETE") else {"json": {}}
    return client.request(method, f"/api/v1{path}", **kw)


def test_role_matrix(clients, make_org):
    org = make_org()["id"]
    wrong = []
    for area, method, path, allowed in CASES:
        for role in ROLES:
            code = call(clients[role], method, path.format(org=org)).status_code
            assert code != 401, (role, method, path)
            if (code != 403) != (role in allowed):
                wrong.append(f"{role} {method} {path} ({area}): {code}")
    assert not wrong, "\n".join(wrong)


def _routes():
    """Every API route with its permission marker (FastAPI may wrap included routers)."""
    for r in app.routes:
        if isinstance(r, APIRoute):
            yield r
        elif hasattr(r, "effective_route_contexts"):
            yield from r.effective_route_contexts()


def _permission(route) -> str | None:
    for dep in route.dependant.dependencies:
        marker = getattr(dep.call, "__psa_permission__", None)
        if marker:
            return marker
    return None


def test_tech_and_read_only_denied_every_invoice_and_procurement_route(login):
    paths = app.openapi()["paths"]
    guarded = []
    for route in _routes():
        perm = _permission(route)
        if perm == "invoice:read" or (perm or "").startswith("procurement:"):
            for method in route.methods - {"HEAD", "OPTIONS"}:
                assert method.lower() in paths[route.path]  # the walk covers the published API
                guarded.append((method, route.path))
    # sanity: the walk found the finance and procurement routers
    assert ("GET", "/api/v1/invoices") in guarded
    assert ("GET", "/api/v1/procurement/vendors") in guarded
    assert len(guarded) > 30
    for role in ("tech", "read_only"):
        c = login(role)
        for method, path in guarded:
            url = re.sub(r"\{[^}]+\}", "1", path)
            r = c.request(method, url, **({} if method in ("GET", "DELETE") else {"json": {}}))
            assert r.status_code == 403, (role, method, path, r.status_code)


def test_api_key_capped_by_owner_role(admin, owner):
    """A key listing invoice:read (as migration 0039 adds) gets nothing its owner's role lacks."""
    r = admin.post(
        "/api/v1/api-keys",
        json={"name": "k", "permissions": ["ticket:read", "billing:read", "invoice:read"]},
    )
    assert r.status_code == 201, r.text
    key = TestClient(RouteRecorder(app), headers={"Authorization": f"Bearer {r.json()['token']}"})
    assert key.get("/api/v1/invoices").status_code == 200
    owner.execute(text("UPDATE users SET role = 'tech' WHERE id = :u"), {"u": admin.user["id"]})
    assert key.get("/api/v1/invoices").status_code == 403
    assert key.get("/api/v1/products").status_code == 200
    assert key.get("/api/v1/tickets").status_code == 200


def test_admin_can_assign_manager_role(admin, make_user):
    uid = make_user("tech", "promote@example.com")["id"]
    r = admin.patch(f"/api/v1/users/{uid}", json={"role": "manager"})
    assert r.status_code == 200 and r.json()["role"] == "manager", r.text
    assert admin.patch(f"/api/v1/users/{uid}", json={"role": "boss"}).status_code == 422
