"""API contract: every route is documented, permission-guarded and exercised by the suite."""

import pytest
from fastapi.routing import APIRoute

from app.main import app
from tests.conftest import HIT_ROUTES

PUBLIC = {  # deliberately unauthenticated
    ("GET", "/healthz"),
    ("GET", "/readyz"),
    ("GET", "/api/v1/auth/login"),
    ("GET", "/api/v1/auth/callback"),
    ("POST", "/api/v1/auth/dev-login"),
    ("POST", "/api/v1/portal/login-link"),
    ("POST", "/api/v1/portal/verify"),
    ("GET", "/api/v1/portal/login-options"),
    ("GET", "/api/v1/portal/sso/login"),
    ("GET", "/api/v1/portal/sso/callback"),
    ("POST", "/api/v1/csat/respond"),
}


def _routes():
    """Every API route; FastAPI wraps included routers, so expand them (as test_role_matrix)."""
    for route in app.routes:
        if isinstance(route, APIRoute):
            yield route
        elif hasattr(route, "effective_route_contexts"):
            yield from route.effective_route_contexts()


def api_routes():
    for route in _routes():
        for method in route.methods - {"HEAD", "OPTIONS"}:
            yield method, route


def permission_of(route: APIRoute):
    for dep in route.dependant.dependencies:
        marker = getattr(dep.call, "__psa_permission__", None)
        if marker:
            return marker
    return None


def test_every_route_is_documented():
    for method, route in api_routes():
        assert route.summary, f"{method} {route.path} has no summary"
        assert route.tags, f"{method} {route.path} has no tag"


def test_every_non_public_route_declares_a_permission():
    for method, route in api_routes():
        if (method, route.path) in PUBLIC:
            assert permission_of(route) is None
        else:
            assert permission_of(route), f"{method} {route.path} has no permission dependency"


def test_openapi_schema_builds_and_lists_all_paths():
    spec = app.openapi()
    assert spec["info"]["title"] == "PSA API"
    for method, route in api_routes():
        assert method.lower() in spec["paths"][route.path]


# Routes no test called when the route recorder was fixed (Phase 16). Pre-existing debt: this set
# may only shrink. Never add a new route to it; write a test instead.
KNOWN_UNTESTED = {
    ("GET", "/api/v1/surveys"),
    ("GET", "/healthz"),
    ("GET", "/readyz"),
    ("PATCH", "/api/v1/expense-categories/{item_id}"),
    ("POST", "/api/v1/canned-responses/{item_id}/unarchive"),
    ("POST", "/api/v1/expense-categories/{item_id}/archive"),
    ("POST", "/api/v1/expense-categories/{item_id}/unarchive"),
    ("POST", "/api/v1/ticket-types/{item_id}/unarchive"),
}


def test_every_route_is_exercised_by_the_suite(request):
    if request.config.args not in ([], ["tests"], ["tests/"]):
        pytest.skip("only meaningful when the whole suite runs")
    missing = {
        (m, r.path)
        for m, r in api_routes()
        if (m, id(getattr(r, "original_route", r))) not in HIT_ROUTES
    }
    stale = KNOWN_UNTESTED - missing
    assert not stale, f"now tested, remove from KNOWN_UNTESTED: {sorted(stale)}"
    missing -= KNOWN_UNTESTED
    assert not missing, f"routes never called by any test: {sorted(missing)}"
