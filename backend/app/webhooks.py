"""Outbound webhooks: an outbox of signed deliveries sent by the worker with retries.

Safety rules (each covered by tests):
- Destinations must be https with no credentials or fragment, and must not be (or resolve to) a
  private, loopback, link-local or reserved address unless WEBHOOK_ALLOW_PRIVATE_HOSTS is set.
  The check runs when saving AND again at every send. It cannot fully stop DNS rebinding between
  the check and the connection (see docs/WEBHOOKS.md).
- Redirects are never followed; a 3xx is a failed attempt.
- Every request is signed (HMAC-SHA256 over "<timestamp>.<body>") with the endpoint's secret.
- The secret and the URL are write-only: neither is ever returned or audited.
- Responses are never stored beyond the status code and a short fixed error text.
"""

import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import socket
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, crypto
from app.config import get_settings
from app.deps import Ctx
from app.errors import Conflict, NotFound
from app.events import EVENT_TYPES
from app.models import WebhookDelivery, WebhookEndpoint
from app.schemas import WebhookOut

log = logging.getLogger("psa.webhooks")

BACKOFF = (60, 300, 1800, 7200, 21600)  # seconds before attempts 2..6
MAX_ATTEMPTS = 6
KINDS = ("generic", "teams")
MAX_URL = 2000


class WebhookBlocked(Exception):
    """The destination is not allowed (private address) or could not be resolved."""


def _now() -> datetime:
    return datetime.now(UTC)


# ---- SSRF guard ----------------------------------------------------------------------------
def _check_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if not ip.is_global or ip.is_multicast:
        raise WebhookBlocked("Host is a private or reserved address")


def resolve_public(host: str) -> None:
    """Raise WebhookBlocked unless `host` (IP literal or name) only has public addresses."""
    host = host.strip("[]")
    try:
        _check_ip(ipaddress.ip_address(host))
        return
    except ValueError:
        pass  # not an IP literal: resolve it
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError) as exc:
        raise WebhookBlocked("DNS lookup failed") from exc
    if not infos:
        raise WebhookBlocked("DNS lookup failed")
    for info in infos:
        try:
            _check_ip(ipaddress.ip_address(info[4][0].split("%")[0]))
        except ValueError as exc:
            raise WebhookBlocked("DNS lookup failed") from exc


def check_url(url: str) -> str:
    """Validate a destination URL; returns it unchanged or raises Conflict."""
    url = (url or "").strip()
    if not url or len(url) > MAX_URL:
        raise Conflict("Enter the webhook URL")
    try:
        parts = urlsplit(url)
        host, _ = parts.hostname, parts.port  # .port raises ValueError when malformed
    except ValueError as exc:
        raise Conflict("That URL is not valid") from exc
    if parts.scheme != "https":
        raise Conflict("Webhook URLs must start with https://")
    if not host:
        raise Conflict("That URL has no host")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise Conflict("Webhook URLs cannot contain a username or password")
    if parts.fragment or "#" in url:
        raise Conflict("Webhook URLs cannot contain a # fragment")
    if not get_settings().webhook_allow_private_hosts:
        try:
            resolve_public(host)
        except WebhookBlocked as exc:
            raise Conflict(str(exc)) from exc
    return url


# ---- signing and rendering -----------------------------------------------------------------
def sign(secret: str, timestamp: int, raw: bytes) -> str:
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + raw, hashlib.sha256)
    return "v1=" + mac.hexdigest()


HEADLINES = {
    "ticket.created": "New ticket",
    "ticket.assigned": "Ticket assigned",
    "ticket.status_changed": "Status changed",
    "ticket.priority_changed": "Priority changed",
    "ticket.customer_reply": "Customer replied",
    "ticket.sla_breached": "SLA breached",
    "rmm_alert.opened": "Monitoring alert opened",
    "rmm_alert.cleared": "Monitoring alert cleared",
}


def _dumps(obj: dict) -> bytes:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True).encode()


def _teams_card(body: dict) -> dict:
    if body.get("type") == "ping":
        card_body: list = [
            {"type": "TextBlock", "text": "PSA webhook test", "weight": "Bolder", "wrap": True},
            {"type": "TextBlock", "text": "This endpoint is connected.", "wrap": True},
        ]
        actions: list = []
    else:
        t = body["ticket"]
        headline = HEADLINES.get(body["type"], body["type"])
        alert = body.get("alert")
        if alert:
            headline = f"{headline} ({alert['severity']})"
        facts = [
            {"title": "Client", "value": t.get("organization") or "Not yet matched"},
            {"title": "Priority", "value": t.get("priority") or "-"},
            {"title": "Status", "value": t.get("status") or "-"},
            {"title": "Assignee", "value": t.get("assignee") or "Unassigned"},
        ]
        card_body = [
            {
                "type": "TextBlock",
                "text": f"#{t['number']} {t['subject']}",
                "weight": "Bolder",
                "size": "Medium",
                "wrap": True,
            },
            {"type": "TextBlock", "text": headline, "wrap": True},
            {"type": "FactSet", "facts": facts},
        ]
        actions = [{"type": "Action.OpenUrl", "title": "Open ticket", "url": t["url"]}]
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": card_body,
                    "actions": actions,
                },
            }
        ],
    }


def render(endpoint: WebhookEndpoint, body: dict) -> bytes:
    if endpoint.kind == "teams":
        return _dumps(_teams_card(body))
    return _dumps(body)


# ---- outbox --------------------------------------------------------------------------------
def enqueue(
    ctx: Ctx,
    event_type: str,
    event_id: uuid.UUID,
    body: dict,
    endpoint_ids: list[int] | None = None,
) -> int:
    """Queue `body` for every enabled endpoint that subscribes to `event_type` (or only for
    `endpoint_ids`, ignoring subscriptions). Returns the number of deliveries queued."""
    q = (
        select(WebhookEndpoint)
        .where(WebhookEndpoint.enabled.is_(True))
        .order_by(WebhookEndpoint.id)
    )
    if endpoint_ids is not None:
        q = q.where(WebhookEndpoint.id.in_(endpoint_ids))
    n = 0
    t = _now()
    for ep in ctx.db.scalars(q):
        if endpoint_ids is None and event_type not in ep.events:
            continue
        ctx.db.add(
            WebhookDelivery(
                endpoint_id=ep.id,
                event_id=event_id,
                event_type=event_type,
                payload=body,
                status="pending",
                attempts=0,
                next_attempt_at=t,
            )
        )
        n += 1
    ctx.db.flush()
    return n


def _attempt(ep: WebhookEndpoint, row: WebhookDelivery, now: datetime, transport) -> tuple:
    """Send once. Returns (status_code or None, error text or None)."""
    try:
        secret = crypto.decrypt_credentials(ep.secret)["secret"]
        url = check_url(ep.url)
        raw = render(ep, row.payload)
        ts = int(now.timestamp())
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "PSA-Webhooks/1",
            "X-PSA-Event": row.event_type,
            "X-PSA-Delivery": str(row.event_id),
            "X-PSA-Timestamp": str(ts),
            "X-PSA-Signature": sign(secret, ts, raw),
        }
        with httpx.Client(timeout=10, follow_redirects=False, transport=transport) as client:
            resp = client.post(url, content=raw, headers=headers)
    except Conflict as exc:  # the destination is no longer allowed
        return None, str(exc)[:300]
    except crypto.CredentialsKeyError:
        return None, "The signing secret cannot be decrypted with the configured key"
    except httpx.TimeoutException:
        return None, "Timed out"
    except httpx.HTTPError as exc:
        return None, f"Connection error ({type(exc).__name__})"
    except Exception as exc:  # malformed payload, bad URL, missing secret: a failed attempt
        return None, f"Delivery error ({type(exc).__name__})"
    if 200 <= resp.status_code < 300:
        return resp.status_code, None
    if 300 <= resp.status_code < 400:
        return resp.status_code, f"HTTP {resp.status_code} (redirects are not followed)"
    return resp.status_code, f"HTTP {resp.status_code}"


def deliver_due(
    db: Session,
    now: datetime | None = None,
    transport: httpx.BaseTransport | None = None,
    limit: int = 50,
) -> dict:
    """Send pending deliveries that are due, one commit per row. Rows of disabled endpoints are
    left pending. Returns counts: delivered, retried, failed."""
    now = now or _now()
    counts = {"delivered": 0, "retried": 0, "failed": 0}
    due = (
        select(WebhookDelivery.id)
        .join(WebhookEndpoint, WebhookEndpoint.id == WebhookDelivery.endpoint_id)
        .where(
            WebhookDelivery.status == "pending",
            WebhookDelivery.next_attempt_at <= now,
            WebhookEndpoint.enabled.is_(True),
        )
        .order_by(WebhookDelivery.next_attempt_at, WebhookDelivery.id)
        .limit(limit)
    )
    ids = list(db.scalars(due))
    db.rollback()  # end the read transaction; each row is locked and committed on its own
    failed_endpoints: set[int] = set()  # endpoints that failed this cycle; skip their other rows
    for delivery_id in ids:
        try:
            _deliver_one(db, delivery_id, now, transport, counts, failed_endpoints)
        except Exception:
            db.rollback()
            log.exception("webhook delivery %s crashed", delivery_id)
    return counts


def _deliver_one(
    db: Session,
    delivery_id: int,
    now: datetime,
    transport: httpx.BaseTransport | None,
    counts: dict,
    failed_endpoints: set[int],
) -> None:
    row = db.scalar(
        select(WebhookDelivery)
        .where(WebhookDelivery.id == delivery_id, WebhookDelivery.status == "pending")
        .with_for_update(skip_locked=True)
    )
    if row is None:  # another worker has it, or it was settled meanwhile
        db.rollback()
        return
    ep = db.get(WebhookEndpoint, row.endpoint_id)
    if ep is None or not ep.enabled or ep.id in failed_endpoints:
        db.rollback()
        return
    code, error = _attempt(ep, row, now, transport)
    row.last_status_code = code
    if error is None:
        row.status, row.delivered_at, row.last_error = "delivered", now, None
        ep.consecutive_failures, ep.last_success_at = 0, now
        counts["delivered"] += 1
    else:
        row.attempts += 1
        row.last_error = error[:300]
        ep.consecutive_failures += 1
        ep.last_failure_at = now
        failed_endpoints.add(ep.id)
        if row.attempts >= MAX_ATTEMPTS:
            row.status = "failed"
            counts["failed"] += 1
        else:
            row.next_attempt_at = now + timedelta(seconds=BACKOFF[row.attempts - 1])
            counts["retried"] += 1
    db.commit()


# ---- management ----------------------------------------------------------------------------
def view(ep: WebhookEndpoint) -> WebhookOut:
    parts = urlsplit(ep.url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return WebhookOut(
        id=ep.id,
        name=ep.name,
        kind=ep.kind,  # type: ignore[arg-type]
        url_host=host,
        url_preview=f"https://{host}/" + parts.path.lstrip("/")[:12] + "…",
        events=list(ep.events),
        enabled=ep.enabled,
        consecutive_failures=ep.consecutive_failures,
        last_success_at=ep.last_success_at,
        last_failure_at=ep.last_failure_at,
        created_at=ep.created_at,
    )


def _get(ctx: Ctx, endpoint_id: int) -> WebhookEndpoint:
    ep = ctx.db.get(WebhookEndpoint, endpoint_id)
    if ep is None:
        raise NotFound("Webhook not found")
    return ep


def _events(events: list[str]) -> list[str]:
    unknown = [e for e in events if e not in EVENT_TYPES]
    if unknown:
        raise Conflict(f"Unknown event type: {unknown[0]}")
    chosen = [e for e in EVENT_TYPES if e in events]  # de-duplicated, canonical order
    if not chosen:
        raise Conflict("Choose at least one event")
    return chosen


def _name(name: str | None) -> str:
    name = (name or "").strip()
    if not name or len(name) > 100:
        raise Conflict("Give the webhook a name of 1 to 100 characters")
    return name


def _new_secret() -> tuple[str, str]:
    secret = secrets.token_urlsafe(32)
    try:
        return secret, crypto.encrypt_credentials({"secret": secret})
    except crypto.CredentialsKeyError as exc:
        raise Conflict(str(exc)) from exc


def list_endpoints(ctx: Ctx) -> list[WebhookEndpoint]:
    return list(ctx.db.scalars(select(WebhookEndpoint).order_by(WebhookEndpoint.id)))


def create(ctx: Ctx, data: dict) -> tuple[WebhookEndpoint, str]:
    name = _name(data.get("name"))
    if data.get("kind") not in KINDS:
        raise Conflict("Kind must be generic or teams")
    events = _events(data.get("events") or [])
    url = check_url(data.get("url", ""))
    secret, token = _new_secret()
    ep = WebhookEndpoint(
        name=name,
        kind=data["kind"],
        url=url,
        secret=token,
        events=events,
        created_by_id=ctx.user.id,
    )
    ctx.db.add(ep)
    ctx.db.flush()
    ctx.db.refresh(ep)
    audit.record(
        ctx.db,
        ctx.user,
        "webhook.created",
        ep,
        after={"name": ep.name, "kind": ep.kind, "events": ep.events, "enabled": ep.enabled},
    )
    return ep, secret


def update(ctx: Ctx, endpoint_id: int, data: dict) -> WebhookEndpoint:
    ep = _get(ctx, endpoint_id)
    before = {"name": ep.name, "events": list(ep.events), "enabled": ep.enabled}
    changed: list[str] = []
    if "name" in data and data["name"] is not None:
        ep.name = _name(data["name"])
        changed.append("name")
    if "events" in data and data["events"] is not None:
        ep.events = _events(data["events"])
        changed.append("events")
    if "enabled" in data and data["enabled"] is not None:
        ep.enabled = bool(data["enabled"])
        changed.append("enabled")
    if "url" in data and data["url"] is not None:
        ep.url = check_url(data["url"])
        changed.append("url")  # the value itself is never audited
    ep.updated_at = _now()
    ctx.db.flush()
    audit.record(
        ctx.db,
        ctx.user,
        "webhook.updated",
        ep,
        before=before,
        after={"name": ep.name, "events": list(ep.events), "enabled": ep.enabled},
        detail={"changed": changed},
    )
    return ep


def rotate_secret(ctx: Ctx, endpoint_id: int) -> tuple[WebhookEndpoint, str]:
    ep = _get(ctx, endpoint_id)
    secret, ep.secret = _new_secret()
    ep.updated_at = _now()
    ctx.db.flush()
    audit.record(ctx.db, ctx.user, "webhook.secret_rotated", ep)
    return ep, secret


def test(ctx: Ctx, endpoint_id: int) -> int:
    """Queue a 'ping' for this endpoint only (subscriptions are ignored)."""
    ep = _get(ctx, endpoint_id)
    if not ep.enabled:
        raise Conflict("Enable the webhook before sending a test")
    event_id = uuid.uuid4()
    body = {
        "version": 1,
        "id": str(event_id),
        "type": "ping",
        "occurred_at": _now().isoformat(timespec="seconds"),
        "message": "PSA webhook test",
    }
    return enqueue(ctx, "ping", event_id, body, [ep.id])


def deliveries(
    ctx: Ctx, endpoint_id: int, status: str | None = None, limit: int = 50
) -> list[WebhookDelivery]:
    _get(ctx, endpoint_id)
    if status is not None and status not in ("pending", "delivered", "failed"):
        raise Conflict("Status must be pending, delivered or failed")
    q = select(WebhookDelivery).where(WebhookDelivery.endpoint_id == endpoint_id)
    if status:
        q = q.where(WebhookDelivery.status == status)
    return list(
        ctx.db.scalars(q.order_by(WebhookDelivery.id.desc()).limit(max(1, min(limit, 200))))
    )


def retry(ctx: Ctx, delivery_id: int) -> WebhookDelivery:
    row = ctx.db.get(WebhookDelivery, delivery_id)
    if row is None:
        raise NotFound("Delivery not found")
    if row.status == "delivered":
        raise Conflict("That delivery already succeeded")
    row.status, row.attempts, row.next_attempt_at = "pending", 0, _now()
    ctx.db.flush()
    audit.record(
        ctx.db,
        ctx.user,
        "webhook.delivery_retried",
        row,
        detail={"endpoint_id": row.endpoint_id, "event_type": row.event_type},
    )
    return row
