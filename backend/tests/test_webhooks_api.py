"""Webhook management API: CRUD, write-only url/secret, rotate, test ping, deliveries, retry."""

import hashlib
import hmac
import json

import httpx
import pytest
from sqlalchemy import text

from tests.test_webhooks import NOW, deliver, public_dns, queue, sample_body  # noqa: F401

URL = "https://hooks.example.com/services/T000/B000/abcdefXYZ-secret-path"
BODY = {"name": "Teams ops", "kind": "teams", "url": URL, "events": ["ticket.created"]}


@pytest.fixture
def made(admin):
    r = admin.post("/api/webhooks", json=BODY)
    assert r.status_code == 201, r.text
    return r.json()


def audit_rows(owner, action):
    return owner.execute(
        text(
            "SELECT detail::text AS d, after::text AS a, before::text AS b FROM audit_log "
            "WHERE action = :a ORDER BY id"
        ),
        {"a": action},
    ).all()


def test_create_returns_secret_once_and_never_the_url(admin, made, owner):
    ep, secret = made["endpoint"], made["secret"]
    assert len(secret) >= 40
    assert ep["name"] == "Teams ops" and ep["kind"] == "teams" and ep["enabled"] is True
    assert ep["events"] == ["ticket.created"] and ep["consecutive_failures"] == 0
    assert ep["url_host"] == "hooks.example.com"
    assert ep["url_preview"] == "https://hooks.example.com/services/T00…"
    assert set(ep) == {
        "id", "name", "kind", "url_host", "url_preview", "events", "enabled",
        "consecutive_failures", "last_success_at", "last_failure_at", "created_at",
    }  # fmt: skip
    listed = admin.get("/api/webhooks")
    assert listed.status_code == 200 and listed.json() == [ep]
    assert secret not in listed.text and "abcdefXYZ" not in listed.text
    stored = owner.execute(text("SELECT secret, url FROM webhook_endpoints")).one()
    assert secret not in stored.secret and stored.url == URL
    for action in ("webhook.created",):
        [row] = audit_rows(owner, action)
        assert secret not in (row.d or "") + (row.a or "") and "abcdefXYZ" not in str(row)


def test_create_validation(admin):
    def post(**kw):
        return admin.post("/api/webhooks", json={**BODY, **kw})

    assert post(kind="slack").status_code == 409
    assert post(events=[]).status_code == 409
    assert post(events=["ticket.exploded"]).status_code == 409
    assert post(name="  ").status_code in (409, 422)
    assert post(name="").status_code == 422
    assert admin.post("/api/webhooks", json={"name": "x"}).status_code == 422
    assert admin.get("/api/webhooks").json() == []


@pytest.mark.parametrize(
    "url",
    [
        "http://hooks.example.com/x",
        "https://10.0.0.1/x",
        "https://127.0.0.1/x",
        "https://169.254.169.254/latest",
        "https://[::1]/x",
        "https://user:pw@hooks.example.com/x",
        "https://hooks.example.com/x#f",
    ],
)
def test_ssrf_and_bad_urls_are_409_on_create_and_update(admin, made, url):
    assert admin.post("/api/webhooks", json={**BODY, "url": url}).status_code == 409
    r = admin.patch(f"/api/webhooks/{made['endpoint']['id']}", json={"url": url})
    assert r.status_code == 409


def test_hostname_resolving_privately_is_409(admin, made, monkeypatch):
    import socket

    from tests.test_webhooks import addrinfo

    monkeypatch.setattr(socket, "getaddrinfo", addrinfo("10.9.9.9"))
    assert (
        admin.post("/api/webhooks", json={**BODY, "url": "https://evil.example.com/x"}).status_code
        == 409
    )
    r = admin.patch(
        f"/api/webhooks/{made['endpoint']['id']}", json={"url": "https://evil.example.com/x"}
    )
    assert r.status_code == 409


def test_patch_fields_and_audit(admin, made, owner):
    wid = made["endpoint"]["id"]
    new_url = "https://n8n.example.com/webhook/zzz-secret-token"
    r = admin.patch(
        f"/api/webhooks/{wid}",
        json={"name": "Renamed", "enabled": False, "events": ["ticket.assigned", "ticket.created"],
              "url": new_url},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    ep = r.json()
    assert ep["name"] == "Renamed" and ep["enabled"] is False
    assert ep["events"] == ["ticket.created", "ticket.assigned"]  # canonical order
    assert ep["url_host"] == "n8n.example.com" and "zzz-secret-token" not in json.dumps(ep)
    assert owner.execute(text("SELECT url FROM webhook_endpoints")).scalar() == new_url
    [row] = audit_rows(owner, "webhook.updated")
    assert "zzz-secret-token" not in str(row) and '"url"' in row.d
    assert admin.patch(f"/api/webhooks/{wid}", json={"events": []}).status_code == 409
    assert admin.patch(f"/api/webhooks/{wid}", json={"events": ["nope"]}).status_code == 409
    assert admin.patch("/api/webhooks/9999", json={"name": "x"}).status_code == 404
    assert admin.patch(f"/api/webhooks/{wid}", json={"name": ""}).status_code == 422


def test_rotate_secret_changes_the_signature(admin, made, owner):
    wid, old = made["endpoint"]["id"], made["secret"]
    body = sample_body()
    queue(wid, body)
    seen = []
    deliver(handler=lambda r: seen.append(r) or httpx.Response(200))
    r = admin.post(f"/api/webhooks/{wid}/rotate-secret")
    assert r.status_code == 200, r.text
    new = r.json()["secret"]
    assert new != old and r.json()["endpoint"]["id"] == wid
    queue(wid, sample_body())
    deliver(handler=lambda r: seen.append(r) or httpx.Response(200))
    first, second = seen

    def mac(secret, req):
        ts = req.headers["x-psa-timestamp"].encode()
        return (
            "v1=" + hmac.new(secret.encode(), ts + b"." + req.content, hashlib.sha256).hexdigest()
        )

    assert first.headers["x-psa-signature"] == mac(old, first)
    assert second.headers["x-psa-signature"] == mac(new, second)
    assert second.headers["x-psa-signature"] != mac(old, second)
    [row] = audit_rows(owner, "webhook.secret_rotated")
    assert new not in str(row) and old not in str(row)
    assert admin.post("/api/webhooks/9999/rotate-secret").status_code == 404


def test_test_ping_enqueues_for_this_endpoint_only(admin, made, owner):
    other = admin.post("/api/webhooks", json={**BODY, "name": "other"}).json()["endpoint"]["id"]
    wid = made["endpoint"]["id"]
    r = admin.post(f"/api/webhooks/{wid}/test")
    assert r.status_code == 202 and r.json() == {"queued": 1}
    rows = owner.execute(
        text("SELECT endpoint_id, event_type, payload FROM webhook_deliveries")
    ).all()
    assert [(x.endpoint_id, x.event_type) for x in rows] == [(wid, "ping")]
    assert other not in [x.endpoint_id for x in rows]
    seen = []
    deliver(now=None, handler=lambda req: seen.append(req) or httpx.Response(200))
    assert "PSA webhook test" in seen[0].content.decode()  # the teams card
    assert admin.post("/api/webhooks/9999/test").status_code == 404
    admin.patch(f"/api/webhooks/{wid}", json={"enabled": False})
    assert admin.post(f"/api/webhooks/{wid}/test").status_code == 409


def test_deliveries_list_filter_limit(admin, made):
    wid = made["endpoint"]["id"]
    for _ in range(3):
        queue(wid)
    deliver(handler=lambda r: httpx.Response(500))
    admin.post(f"/api/webhooks/{wid}/test")
    r = admin.get(f"/api/webhooks/{wid}/deliveries")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 4 and [i["id"] for i in items] == sorted(
        (i["id"] for i in items), reverse=True
    )
    first = items[-1]
    assert set(first) == {
        "id", "endpoint_id", "event_id", "event_type", "status", "attempts", "next_attempt_at",
        "last_status_code", "last_error", "delivered_at", "created_at",
    }  # fmt: skip
    assert first["attempts"] == 1 and first["last_status_code"] == 500
    assert "payload" not in first
    assert len(admin.get(f"/api/webhooks/{wid}/deliveries", params={"limit": 2}).json()) == 2
    assert (
        len(admin.get(f"/api/webhooks/{wid}/deliveries", params={"status": "pending"}).json()) == 4
    )
    assert admin.get(f"/api/webhooks/{wid}/deliveries", params={"status": "delivered"}).json() == []
    assert (
        admin.get(f"/api/webhooks/{wid}/deliveries", params={"status": "bogus"}).status_code == 422
    )
    assert admin.get(f"/api/webhooks/{wid}/deliveries", params={"limit": 0}).status_code == 422
    assert admin.get("/api/webhooks/9999/deliveries").status_code == 404


def test_retry_rules(admin, made, owner):
    wid = made["endpoint"]["id"]
    done = queue(wid)
    failed = queue(wid, status="failed", attempts=6)
    deliver()  # sends `done`
    r = admin.post(f"/api/webhooks/deliveries/{done}/retry")
    assert r.status_code == 409
    r = admin.post(f"/api/webhooks/deliveries/{failed}/retry")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending" and r.json()["attempts"] == 0
    assert len(audit_rows(owner, "webhook.delivery_retried")) == 1
    assert admin.post("/api/webhooks/deliveries/9999/retry").status_code == 404
    assert deliver()["delivered"] == 1


def test_tech_and_anonymous_are_refused(login, anon, made):
    tech = login("tech")
    wid = made["endpoint"]["id"]
    checks = [
        ("get", "/api/webhooks", None),
        ("post", "/api/webhooks", BODY),
        ("patch", f"/api/webhooks/{wid}", {"name": "x"}),
        ("post", f"/api/webhooks/{wid}/rotate-secret", None),
        ("post", f"/api/webhooks/{wid}/test", None),
        ("get", f"/api/webhooks/{wid}/deliveries", None),
        ("post", "/api/webhooks/deliveries/1/retry", None),
    ]
    for method, path, body in checks:
        assert getattr(tech, method)(path, **({"json": body} if body else {})).status_code == 403, (
            path
        )
        assert getattr(anon, method)(path, **({"json": body} if body else {})).status_code in (
            401,
            403,
        )


def test_api_key_without_permission_cannot_manage_webhooks(admin):
    r = admin.post("/api/api-keys", json={"name": "k", "permissions": ["ticket:read"]})
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app, headers={"Authorization": f"Bearer {r.json()['token']}"})
    assert c.get("/api/webhooks").status_code == 403
