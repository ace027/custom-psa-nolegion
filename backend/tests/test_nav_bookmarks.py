"""Per-user rail bookmarks: GET/PUT /api/v1/me/bookmarks (own row only, staff sessions only)."""

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from tests.conftest import RouteRecorder

URL = "/api/v1/me/bookmarks"


def test_default_is_null_then_round_trip_keeps_order(login):
    c = login("tech")
    r = c.get(URL)
    assert r.status_code == 200, r.text
    assert r.json() == {"items": None}
    order = ["tickets", "dispatch", "timesheet", "organizations"]
    r = c.put(URL, json={"items": order})
    assert r.status_code == 200, r.text
    assert r.json() == {"items": order}
    assert c.get(URL).json() == {"items": order}


def test_reorder_replaces_order_and_empty_list_is_kept(login):
    c = login("billing")
    c.put(URL, json={"items": ["invoices", "receivables", "runs"]})
    assert c.put(URL, json={"items": ["runs", "invoices", "receivables"]}).status_code == 200
    assert c.get(URL).json() == {"items": ["runs", "invoices", "receivables"]}
    # an empty rail is a real choice, distinct from "never set"
    assert c.put(URL, json={"items": []}).status_code == 200
    assert c.get(URL).json() == {"items": []}


def test_invalid_lists_are_rejected(login):
    c = login("admin")
    c.put(URL, json={"items": ["tickets"]})
    bad = [
        [f"page-{i}" for i in range(9)],  # more than 8
        ["tickets", "tickets"],  # duplicate
        ["Tickets"],  # upper case
        ["-tickets"],  # must start with a letter or digit
        ["a" * 65],  # too long
        ["../admin"],
        [""],
    ]
    for items in bad:
        assert c.put(URL, json={"items": items}).status_code == 422, items
    assert c.put(URL, json={}).status_code == 422
    assert c.get(URL).json() == {"items": ["tickets"]}  # nothing changed
    assert c.put(URL, json={"items": [f"page-{i}" for i in range(8)]}).status_code == 200


def test_each_user_reaches_only_their_own_row(login, owner_engine):
    a = login("tech", "a@example.com")
    b = login("tech", "b@example.com")
    a.put(URL, json={"items": ["tickets", "dispatch"]})
    assert b.get(URL).json() == {"items": None}
    b.put(URL, json={"items": ["projects"]})
    assert a.get(URL).json() == {"items": ["tickets", "dispatch"]}
    with owner_engine.connect() as conn:
        rows = dict(conn.execute(text("SELECT email, nav_bookmarks FROM users")).all())
    assert rows == {"a@example.com": ["tickets", "dispatch"], "b@example.com": ["projects"]}


def test_api_keys_get_403_and_anonymous_gets_401(admin, anon):
    r = admin.post("/api/v1/api-keys", json={"name": "n8n", "permissions": ["ticket:read"]})
    assert r.status_code == 201, r.text
    key = TestClient(RouteRecorder(app), headers={"Authorization": f"Bearer {r.json()['token']}"})
    assert key.get(URL).status_code == 403
    assert key.put(URL, json={"items": ["tickets"]}).status_code == 403
    assert anon.get(URL).status_code == 401
    assert anon.put(URL, json={"items": ["tickets"]}).status_code == 401
    assert admin.get(URL).json() == {"items": None}
