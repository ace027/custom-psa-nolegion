"""Everything is served under /api/v1 and the committed OpenAPI spec is fresh and complete."""

import json

from fastapi.routing import APIRoute

from app.main import app
from app.openapi_export import SPEC_PATH, generate

UNVERSIONED = {"/healthz", "/readyz"}


def _schemas() -> dict:
    return json.loads(SPEC_PATH.read_text())["components"]["schemas"]


def _props(name: str) -> dict:
    return _schemas()[name]["properties"]


def test_every_route_is_versioned():
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path not in UNVERSIONED:
            assert route.path.startswith("/api/v1/"), route.path


def test_unversioned_api_path_is_gone(admin):
    assert admin.get("/api/organizations").status_code == 404
    assert admin.get("/api/v1/organizations").status_code == 200


def test_committed_spec_is_fresh():
    assert SPEC_PATH.read_text() == generate(), (
        "docs/api/openapi.json is stale; run: python -m app.openapi_export"
    )


def test_spec_has_no_environment_values():
    text = SPEC_PATH.read_text()
    assert "localhost" not in text
    assert "psa_" not in text.replace("psa_app", "")


def test_spec_contains_integration_fields():
    for name in ("OrganizationOut", "SiteOut", "ContactOut"):
        assert "uuid" in _props(name), name
    assert "rmm_client_id" in _props("OrganizationOut")
    asset = _props("AssetOut")
    assert sorted(asset["source"]["enum"]) == ["import", "manual", "rmm"]
    assert "external_id" in asset
    ticket = _props("TicketOut")
    six = {"manual", "email", "portal", "rmm", "api", "rule"}
    assert six <= set(ticket["source"]["enum"])
    assert "external_ref" in ticket
    assert set(_props("NoteOut")["author_type"]["enum"]) == {"human", "system", "ai"}
    assert set(_props("TimeOut")["entry_type"]["enum"]) == {"labour", "automation"}
    assert "entra_tenant_id" in _props("UserOut")
    assert "automation_minutes" in _props("UtilisationRowOut")
