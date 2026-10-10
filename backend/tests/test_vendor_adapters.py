"""The NinjaOne and Hudu adapters, against fake HTTP servers (httpx.MockTransport)."""

import json
from datetime import date

import httpx
import pytest

from app.integrations.base import VendorError
from app.integrations.hudu import HuduClient
from app.integrations.ninjaone import NinjaOneClient


def ninja(handler):
    return NinjaOneClient("https://ninja.test", "cid", "csecret", httpx.MockTransport(handler))


def test_ninjaone_signs_in_with_client_credentials_and_maps_devices():
    seen = []

    def handler(req: httpx.Request):
        seen.append(req)
        if req.url.path == "/ws/oauth/token":
            form = dict(x.split("=") for x in req.content.decode().split("&"))
            assert form["grant_type"] == "client_credentials" and form["scope"] == "monitoring"
            return httpx.Response(200, json={"access_token": "tok"})
        assert req.headers["authorization"] == "Bearer tok"
        assert req.method == "GET"  # read-only
        if req.url.path == "/v2/organizations":
            return httpx.Response(200, json=[{"id": 7, "name": "Acme"}])
        return httpx.Response(
            200,
            json=[
                {
                    "id": 11,
                    "nodeClass": "WINDOWS_SERVER",
                    "systemName": "DC01",
                    "lastContact": 1790000000,
                    "system": {"manufacturer": "Dell", "model": "R740", "serialNumber": "ABC123"},
                    "warranty": {"startDate": "2024-01-01", "endDate": "2027-01-01"},
                }
            ],
        )

    c = ninja(handler)
    assert [(x.external_id, x.name) for x in c.list_clients()] == [("7", "Acme")]
    (a,) = c.list_assets("7")
    assert (a.name, a.kind, a.serial, a.manufacturer) == ("DC01", "server", "ABC123", "Dell")
    assert a.warranty_end == date(2027, 1, 1) and a.last_seen is not None
    assert [r.method for r in seen] == ["POST", "GET", "GET"] and seen[-1].url.params[
        "df"
    ] == "org = 7"


def test_ninjaone_paginates_until_a_short_page():
    pages = []

    def handler(req):
        if req.url.path == "/ws/oauth/token":
            return httpx.Response(200, json={"access_token": "t"})
        after = req.url.params.get("after")
        pages.append(after)
        if after is None:
            return httpx.Response(200, json=[{"id": i, "name": f"o{i}"} for i in range(1, 201)])
        return httpx.Response(200, json=[{"id": 201, "name": "last"}])

    assert len(ninja(handler).list_clients()) == 201 and pages == [None, "200"]


def test_ninjaone_failures_are_vendor_errors_without_secrets():
    c = ninja(lambda r: httpx.Response(401, json={"error": "csecret leaked?"}))
    with pytest.raises(VendorError) as e:
        c.test_connection()
    assert "401" in str(e.value) and "csecret" not in str(e.value)

    def boom(req):
        raise httpx.ConnectError("no route to host csecret")

    with pytest.raises(VendorError) as e2:
        ninja(boom).test_connection()
    assert "csecret" not in str(e2.value)


def hudu(handler, **cfg):
    config = {
        "layouts": {"Switches": "network"},
        "warranty_end_field": "Warranty Expiration",
        **cfg,
    }
    return HuduClient("https://hudu.test", "key", config, httpx.MockTransport(handler))


def hudu_handler(req: httpx.Request):
    assert req.headers["x-api-key"] == "key" and req.method == "GET"
    path, page = req.url.path, int(req.url.params.get("page", 1))
    if path == "/api/v1/companies":
        return httpx.Response(
            200, json={"companies": [{"id": 3, "name": "Acme"}] if page == 1 else []}
        )
    if path == "/api/v1/asset_layouts":
        lay = [{"id": 5, "name": "Switches"}, {"id": 6, "name": "Passwords"}]
        return httpx.Response(200, json={"asset_layouts": lay if page == 1 else []})
    assert req.url.params["company_id"] == "3"
    assets = [
        {
            "id": 1,
            "name": "Core",
            "asset_layout_id": 5,
            "primary_serial": "SW-1",
            "primary_model": "C9300",
            "primary_manufacturer": "Cisco",
            "archived": False,
            "fields": [{"label": "Warranty Expiration", "value": "03/15/2027"}],
        },
        {"id": 2, "name": "Old", "asset_layout_id": 5, "archived": True, "fields": []},
        {"id": 3, "name": "Secret doc", "asset_layout_id": 6, "fields": []},
    ]
    return httpx.Response(200, json={"assets": assets if page == 1 else []})


def test_hudu_imports_only_configured_layouts_and_parses_warranty():
    c = hudu(hudu_handler)
    assert [x.name for x in c.list_clients()] == ["Acme"]
    (a,) = c.list_assets("3")  # archived and unlisted layouts are skipped
    assert (a.name, a.kind, a.serial, a.model) == ("Core", "network", "SW-1", "C9300")
    assert a.warranty_end == date(2027, 3, 15)


def test_hudu_without_a_warranty_field_leaves_warranty_unknown():
    (a,) = hudu(hudu_handler, warranty_end_field=None).list_assets("3")
    assert a.warranty_end is None


def test_hudu_error_status_is_a_vendor_error():
    with pytest.raises(VendorError):
        hudu(lambda r: httpx.Response(403, text=json.dumps({"error": "nope"}))).test_connection()
