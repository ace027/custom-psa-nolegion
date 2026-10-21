"""Outbound webhook delivery: signing, retries, SSRF guard, redirects, Teams cards."""

import hashlib
import hmac
import json
import os
import socket
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import text

from app import crypto, webhooks
from app import db as dbmod
from app.config import get_settings
from app.errors import Conflict
from app.events import EVENT_TYPES
from app.models import WebhookDelivery, WebhookEndpoint

SECRET = "s3cret-for-tests"
NOW = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)
PUBLIC_IP = "93.184.216.34"


REAL_GETADDRINFO = socket.getaddrinfo
LOCAL = {"localhost", "127.0.0.1", "::1", os.environ.get("PSA_TEST_DB_HOST", "localhost")}


def addrinfo(*ips):
    def fake(host, port, *a, **kw):
        if host in LOCAL:  # the database connection must keep working
            return REAL_GETADDRINFO(host, port, *a, **kw)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in ips]

    return fake


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", addrinfo(PUBLIC_IP))


def add_endpoint(
    user_id, *, events=EVENT_TYPES, kind="generic", enabled=True, url=None, name="n8n"
):
    with dbmod.new_session() as db:
        dbmod.set_org_scope(db, "all")
        ep = WebhookEndpoint(
            name=name,
            kind=kind,
            url=url or "https://hooks.example.com/in/abcdef123456789",
            secret=crypto.encrypt_credentials({"secret": SECRET}),
            events=list(events),
            enabled=enabled,
            created_by_id=user_id,
        )
        db.add(ep)
        db.commit()
        return ep.id


def sample_body(event_type="ticket.created", **extra):
    event_id = uuid.uuid4()
    return {
        "version": 1,
        "id": str(event_id),
        "type": event_type,
        "occurred_at": "2030-01-01T12:00:00+00:00",
        "ticket": {
            "id": 7,
            "number": 10007,
            "subject": "Printer down",
            "status": "open",
            "priority": "High",
            "organization": "Acme Corp",
            "assignee": None,
            "source": "ui",
            "url": "http://localhost:8000/tickets/7",
        },
        "changes": {},
        **extra,
    }


def queue(endpoint_id, body=None, *, at=NOW, status="pending", attempts=0):
    body = body or sample_body()
    with dbmod.new_session() as db:
        dbmod.set_org_scope(db, "all")
        row = WebhookDelivery(
            endpoint_id=endpoint_id,
            event_id=uuid.UUID(body["id"]),
            event_type=body["type"],
            payload=body,
            status=status,
            attempts=attempts,
            next_attempt_at=at,
        )
        db.add(row)
        db.commit()
        return row.id


def deliver(now=NOW, handler=None, **kw):
    transport = httpx.MockTransport(handler or (lambda r: httpx.Response(200)))
    with dbmod.new_session() as db:
        dbmod.set_org_scope(db, "all")
        return webhooks.deliver_due(db, now=now, transport=transport, **kw)


def row(owner, delivery_id):
    return owner.execute(
        text("SELECT * FROM webhook_deliveries WHERE id = :i"), {"i": delivery_id}
    ).one()


def endpoint_row(owner, endpoint_id):
    return owner.execute(
        text("SELECT * FROM webhook_endpoints WHERE id = :i"), {"i": endpoint_id}
    ).one()


# ---- signing ----
def test_signature_matches_an_independent_hmac(admin, owner):
    ep = add_endpoint(admin.user["id"])
    body = sample_body()
    queue(ep, body)
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(204)

    assert deliver(handler=handler)["delivered"] == 1
    [req] = seen
    ts = req.headers["x-psa-timestamp"]
    assert ts == str(int(NOW.timestamp()))
    expected = hmac.new(
        SECRET.encode(), ts.encode() + b"." + req.content, hashlib.sha256
    ).hexdigest()
    assert req.headers["x-psa-signature"] == "v1=" + expected
    assert webhooks.sign(SECRET, int(ts), req.content) == req.headers["x-psa-signature"]
    assert req.headers["x-psa-event"] == "ticket.created"
    assert req.headers["x-psa-delivery"] == body["id"]
    assert req.headers["user-agent"] == "PSA-Webhooks/1"
    assert req.headers["content-type"] == "application/json"
    assert req.method == "POST" and str(req.url) == "https://hooks.example.com/in/abcdef123456789"
    assert json.loads(req.content) == body
    assert req.content == json.dumps(body, separators=(",", ":"), sort_keys=True).encode()


def test_success_updates_delivery_and_endpoint(admin, owner):
    ep = add_endpoint(admin.user["id"])
    owner.execute(text("UPDATE webhook_endpoints SET consecutive_failures = 3"))
    d = queue(ep)
    assert deliver() == {"delivered": 1, "retried": 0, "failed": 0}
    r, e = row(owner, d), endpoint_row(owner, ep)
    assert r.status == "delivered" and r.delivered_at == NOW and r.last_error is None
    assert e.consecutive_failures == 0 and e.last_success_at == NOW
    assert deliver() == {"delivered": 0, "retried": 0, "failed": 0}  # nothing is sent twice


# ---- retries ----
def test_full_backoff_walk_to_failed(admin, owner):
    ep = add_endpoint(admin.user["id"])
    d = queue(ep)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(500, text="secret internal detail")

    now = NOW
    for attempt, wait in enumerate(webhooks.BACKOFF, start=1):
        assert deliver(now=now, handler=handler)["retried"] == 1
        r = row(owner, d)
        assert (r.status, r.attempts, r.last_status_code) == ("pending", attempt, 500)
        assert r.next_attempt_at == now + timedelta(seconds=wait)
        assert deliver(now=now + timedelta(seconds=wait - 1), handler=handler)["retried"] == 0
        now = now + timedelta(seconds=wait)
    assert deliver(now=now, handler=handler) == {"delivered": 0, "retried": 0, "failed": 1}
    r = row(owner, d)
    assert (r.status, r.attempts) == ("failed", webhooks.MAX_ATTEMPTS) == ("failed", 6)
    assert len(calls) == 6
    assert r.last_error == "HTTP 500" and "secret internal detail" not in r.last_error
    e = endpoint_row(owner, ep)
    assert e.consecutive_failures == 6 and e.last_failure_at == now
    assert deliver(now=now + timedelta(days=1), handler=handler)["failed"] == 0


@pytest.mark.parametrize(
    "response, error",
    [
        (httpx.Response(404), "HTTP 404"),
        (httpx.Response(503), "HTTP 503"),
        (httpx.Response(301, headers={"Location": "https://evil.example/x"}), "redirects"),
        (httpx.ConnectError("boom"), "Connection error"),
        (httpx.ReadTimeout("slow"), "Timed out"),
    ],
)
def test_failures_are_retried(admin, owner, response, error):
    ep = add_endpoint(admin.user["id"])
    d = queue(ep)
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if isinstance(response, Exception):
            raise response
        return response

    assert deliver(handler=handler)["retried"] == 1
    r = row(owner, d)
    assert r.status == "pending" and r.attempts == 1 and error in r.last_error
    assert hosts == ["hooks.example.com"]  # the redirect target was never contacted


def test_redirect_is_not_followed_and_counts_as_failure(admin, owner):
    ep = add_endpoint(admin.user["id"])
    d = queue(ep)
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://other.example.com/"})

    deliver(handler=handler)
    assert calls == ["https://hooks.example.com/in/abcdef123456789"]
    r = row(owner, d)
    assert r.status == "pending" and r.last_status_code == 302


def test_dns_failure_at_send_retries_with_message(admin, owner, monkeypatch):
    ep = add_endpoint(admin.user["id"])
    d = queue(ep)

    def broken(host, *a, **kw):
        if host in LOCAL:
            return REAL_GETADDRINFO(host, *a, **kw)
        raise socket.gaierror("no such host")

    monkeypatch.setattr(socket, "getaddrinfo", broken)
    assert deliver()["retried"] == 1
    r = row(owner, d)
    assert r.last_error == "DNS lookup failed" and r.attempts == 1 and r.last_status_code is None


def test_host_that_now_resolves_privately_is_a_failed_attempt(admin, owner, monkeypatch):
    ep = add_endpoint(admin.user["id"])
    d = queue(ep)
    monkeypatch.setattr(socket, "getaddrinfo", addrinfo("10.0.0.5"))
    sent = []
    assert deliver(handler=lambda r: sent.append(r) or httpx.Response(200))["retried"] == 1
    assert sent == [] and "private" in row(owner, d).last_error


# ---- enabled / disabled ----
def test_disabled_endpoint_rows_stay_pending_until_enabled(admin, owner):
    ep = add_endpoint(admin.user["id"], enabled=False)
    d = queue(ep)
    assert deliver() == {"delivered": 0, "retried": 0, "failed": 0}
    assert row(owner, d).status == "pending" and row(owner, d).attempts == 0
    owner.execute(text("UPDATE webhook_endpoints SET enabled = true"))
    assert deliver()["delivered"] == 1


def test_limit_and_order(admin, owner):
    ep = add_endpoint(admin.user["id"])
    late = queue(ep, at=NOW - timedelta(minutes=1))
    early = queue(ep, at=NOW - timedelta(hours=1))
    future = queue(ep, at=NOW + timedelta(minutes=5))
    order = []
    deliver(limit=1, handler=lambda r: order.append(r) or httpx.Response(200))
    assert row(owner, early).status == "delivered" and row(owner, late).status == "pending"
    deliver()
    assert row(owner, late).status == "delivered" and row(owner, future).status == "pending"


# ---- SSRF guard ----
@pytest.mark.parametrize(
    "url",
    [
        "http://hooks.example.com/x",
        "ftp://hooks.example.com/x",
        "https:///nohost",
        "https://user:pw@hooks.example.com/x",
        "https://user@hooks.example.com/x",
        "https://hooks.example.com/x#frag",
        "https://10.0.0.1/x",
        "https://127.0.0.1/x",
        "https://169.254.169.254/latest/meta-data",
        "https://192.168.1.10/x",
        "https://100.64.0.1/x",
        "https://0.0.0.0/x",
        "https://[::1]/x",
        "https://[fe80::1]/x",
        "https://[fd00::1]/x",
        "https://[::ffff:10.0.0.1]/x",
        "",
    ],
)
def test_check_url_rejects(url):
    with pytest.raises(Conflict):
        webhooks.check_url(url)


def test_check_url_accepts_public_https():
    assert (
        webhooks.check_url("https://hooks.example.com/a?b=1") == "https://hooks.example.com/a?b=1"
    )
    assert webhooks.check_url("https://93.184.216.34:8443/x")


@pytest.mark.parametrize("ip", ["10.1.2.3", "127.0.0.1", "169.254.169.254", "::1", "192.168.0.9"])
def test_name_resolving_to_private_address_is_rejected(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", addrinfo(PUBLIC_IP, ip))  # any bad address blocks
    with pytest.raises(Conflict, match="private"):
        webhooks.check_url("https://sneaky.example.com/x")
    with pytest.raises(webhooks.WebhookBlocked):
        webhooks.resolve_public("sneaky.example.com")


def test_unresolvable_name_is_rejected(monkeypatch):
    def broken(host, *a, **kw):
        if host in LOCAL:
            return REAL_GETADDRINFO(host, *a, **kw)
        raise socket.gaierror("nope")

    monkeypatch.setattr(socket, "getaddrinfo", broken)
    with pytest.raises(Conflict, match="DNS lookup failed"):
        webhooks.check_url("https://gone.example.com/x")


def test_private_hosts_opt_in(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", addrinfo("10.0.0.5"))
    with pytest.raises(Conflict):
        webhooks.check_url("https://n8n.lan/webhook/x")
    monkeypatch.setattr(get_settings(), "webhook_allow_private_hosts", True)
    assert webhooks.check_url("https://n8n.lan/webhook/x")
    assert webhooks.check_url("https://10.0.0.5/webhook/x")
    with pytest.raises(Conflict):  # the other rules still apply
        webhooks.check_url("http://10.0.0.5/webhook/x")


def test_private_opt_in_delivers_to_lan_host(admin, owner, monkeypatch):
    monkeypatch.setattr(get_settings(), "webhook_allow_private_hosts", True)
    ep = add_endpoint(admin.user["id"], url="https://10.0.0.5/webhook/x")
    queue(ep)
    assert deliver()["delivered"] == 1


# ---- rendering ----
def test_teams_card_shape():
    ep = WebhookEndpoint(kind="teams")
    card = json.loads(webhooks.render(ep, sample_body("ticket.status_changed")))
    assert card["type"] == "message"
    [att] = card["attachments"]
    assert att["contentType"] == "application/vnd.microsoft.card.adaptive"
    c = att["content"]
    assert c["type"] == "AdaptiveCard" and c["version"] == "1.4" and "$schema" in c
    title, headline, facts = c["body"]
    assert title["text"] == "#10007 Printer down" and title["weight"] == "Bolder" and title["wrap"]
    assert headline["text"] == "Status changed"
    assert facts["type"] == "FactSet"
    assert {f["title"]: f["value"] for f in facts["facts"]} == {
        "Client": "Acme Corp",
        "Priority": "High",
        "Status": "open",
        "Assignee": "Unassigned",
    }
    [action] = c["actions"]
    assert action == {
        "type": "Action.OpenUrl",
        "title": "Open ticket",
        "url": "http://localhost:8000/tickets/7",
    }


def test_teams_and_generic_ping():
    ping = {"version": 1, "id": str(uuid.uuid4()), "type": "ping", "message": "PSA webhook test"}
    card = json.loads(webhooks.render(WebhookEndpoint(kind="teams"), ping))
    assert "PSA webhook test" in json.dumps(card) and card["type"] == "message"
    assert json.loads(webhooks.render(WebhookEndpoint(kind="generic"), ping))["type"] == "ping"


def test_teams_delivery_is_signed_over_the_card(admin, owner):
    ep = add_endpoint(admin.user["id"], kind="teams")
    queue(ep)
    seen = []
    deliver(handler=lambda r: seen.append(r) or httpx.Response(202))
    [req] = seen
    assert json.loads(req.content)["type"] == "message"
    mac = hmac.new(
        SECRET.encode(),
        req.headers["x-psa-timestamp"].encode() + b"." + req.content,
        hashlib.sha256,
    ).hexdigest()
    assert req.headers["x-psa-signature"] == f"v1={mac}"


def test_enqueue_filters_by_subscription_and_enabled(admin):
    from app.deps import Ctx
    from app.scope import Scope

    a = add_endpoint(admin.user["id"], events=["ticket.created"], name="a")
    b = add_endpoint(admin.user["id"], events=["ticket.assigned"], name="b")
    c = add_endpoint(admin.user["id"], events=["ticket.created"], enabled=False, name="c")
    with dbmod.new_session() as db:
        dbmod.set_org_scope(db, "all")
        ctx = Ctx(db=db, user=None, scope=Scope.all())
        eid = uuid.uuid4()
        assert webhooks.enqueue(ctx, "ticket.created", eid, sample_body()) == 1
        db.commit()
        assert [r.endpoint_id for r in db.query(WebhookDelivery)] == [a]
        # an explicit endpoint list ignores subscriptions but never reaches a disabled endpoint
        assert webhooks.enqueue(ctx, "ping", uuid.uuid4(), {"type": "ping"}, [b, c]) == 1
        db.commit()
        assert sorted(r.endpoint_id for r in db.query(WebhookDelivery)) == [a, b]
