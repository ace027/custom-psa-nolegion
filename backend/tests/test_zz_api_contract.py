"""API contract: every route is documented, permission-guarded and exercised by the suite."""

import pytest
from fastapi.routing import APIRoute

from app.main import app
from tests.conftest import HIT_ROUTES

PUBLIC = {  # deliberately unauthenticated
    ("GET", "/healthz"),
    ("GET", "/readyz"),
    ("GET", "/api/auth/login"),
    ("GET", "/api/auth/callback"),
    ("POST", "/api/auth/dev-login"),
    ("POST", "/api/portal/login-link"),
    ("POST", "/api/portal/verify"),
}


def api_routes():
    for route in app.routes:
        if isinstance(route, APIRoute):
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


def test_every_route_is_exercised_by_the_suite(request):
    if request.config.args not in ([], ["tests"], ["tests/"]):
        pytest.skip("only meaningful when the whole suite runs")
    missing = {(m, r.path) for m, r in api_routes()} - HIT_ROUTES
    assert not missing, f"routes never called by any test: {sorted(missing)}"
