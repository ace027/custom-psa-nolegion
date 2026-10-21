# Outbound webhooks

The PSA can tell other tools when something happens: a ticket is created, assigned, changes
status or priority, gets a customer reply, breaches its SLA, or a monitoring alert opens or clears.
Messages are queued in an outbox, signed, and sent by the worker with retries. Manage them under
**Webhooks** in the sidebar (admins, permission `automation:manage`).

Messages carry facts and a link. They never contain the ticket description, notes or email text.

## Event types

| Type | When |
| --- | --- |
| `ticket.created` | A ticket is created (UI, API, email, alert) |
| `ticket.assigned` | A ticket gets a (new) assignee. `changes.assignee_id = [old, new]` |
| `ticket.status_changed` | The status behaviour changes. `changes.status = [old, new]` |
| `ticket.priority_changed` | The priority changes. `changes.priority_id = [old, new]` |
| `ticket.customer_reply` | A customer replied by email |
| `ticket.sla_breached` | The SLA was breached (sent once per ticket, assigned or not) |
| `rmm_alert.opened` | A NinjaOne alert opened a ticket (sent after `ticket.created`) |
| `rmm_alert.cleared` | The alert cleared |

Each endpoint chooses which events it receives. A `ping` event is sent by **Send test**.

## Payload (version 1)

```json
{
  "version": 1,
  "id": "7b0b4a3e-5c0e-4a53-9d58-0b9a3a3c1d11",
  "type": "ticket.status_changed",
  "occurred_at": "2026-10-21T09:30:00+00:00",
  "ticket": {
    "id": 42,
    "number": 10042,
    "subject": "Printer down",
    "status": "open",
    "priority": "High",
    "organization": "Acme Corp",
    "assignee": "Una Tech",
    "source": "ui",
    "url": "https://psa.example.com/tickets/42"
  },
  "changes": { "status": ["new", "open"] },
  "alert": { "id": 5, "severity": "CRITICAL", "state": "open", "message": "Disk low",
             "device_external_id": "17", "resolution": null }
}
```

`alert` appears only on `rmm_alert.*` events. The body is compact JSON with sorted keys.
Endpoints of kind **Microsoft Teams** receive an Adaptive Card message instead (title, facts for
client, priority, status and assignee, and an **Open ticket** button).

## Headers

| Header | Meaning |
| --- | --- |
| `X-PSA-Event` | Event type |
| `X-PSA-Delivery` | The event id (the same on every retry) |
| `X-PSA-Timestamp` | Unix seconds when this attempt was signed |
| `X-PSA-Signature` | `v1=` + hex HMAC-SHA256 of `"<timestamp>.<raw body>"` with the endpoint secret |
| `User-Agent` | `PSA-Webhooks/1` |

The secret is shown once when you create the webhook or rotate its secret. Store it where your
receiver can read it.

## Verifying the signature

Always verify against the **raw bytes** of the request body, reject timestamps more than 5 minutes
old, and compare in constant time.

Python:

```python
import hashlib, hmac, time

def verify(secret: str, headers: dict, raw: bytes) -> bool:
    ts = int(headers["X-PSA-Timestamp"])
    if abs(time.time() - ts) > 300:
        return False
    expected = "v1=" + hmac.new(secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, headers["X-PSA-Signature"])
```

Node:

```js
const crypto = require("crypto");

function verify(secret, headers, raw /* Buffer */) {
  const ts = Number(headers["x-psa-timestamp"]);
  if (!Number.isFinite(ts) || Math.abs(Date.now() / 1000 - ts) > 300) return false;
  const expected = "v1=" + crypto.createHmac("sha256", secret)
    .update(`${ts}.`).update(raw).digest("hex");
  const a = Buffer.from(expected), b = Buffer.from(headers["x-psa-signature"] || "");
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}
```

## Retries and idempotency

A delivery succeeds on any 2xx response. Anything else (3xx, 4xx, 5xx, timeout, connection or DNS
error) is retried. Redirects are never followed. Waits between attempts: 1 min, 5 min, 30 min,
2 h, 6 h. After the 6th failed attempt the delivery is marked **failed**; use **Retry** in the
delivery log to send it again (it starts over). The response body is never stored; only the status
code and a short error text.

A retry is the same event: `X-PSA-Delivery` is identical every time, so use it to ignore
duplicates. Deliveries to a disabled webhook wait and are sent after you enable it again.

## Microsoft Teams

1. In Teams, open the channel, then Workflows, and create the template
   **Post to a channel when a webhook request is received**.
2. Copy the workflow URL it shows.
3. In the PSA, add a webhook of type **Microsoft Teams**, paste the URL, choose events, and press
   **Send test**.

Teams does not check our signature; it is still sent.

## n8n

1. In n8n add a **Webhook** node (method POST, "Raw Body" on) and copy its production URL.
2. In the PSA add a webhook of type **Generic** with that URL.
3. Add a **Code** node after the Webhook node that verifies `X-PSA-Signature` as in the Node snippet
   above, using the raw body, and stops the workflow when it does not match.

If n8n runs on your LAN, the PSA refuses private addresses by default. Set
`WEBHOOK_ALLOW_PRIVATE_HOSTS=true` in the backend and worker environment to allow them. The URL must
still be `https://`.

## Network safety

URLs must be `https://`, with no username/password and no `#fragment`. IP addresses and host names
that resolve to private, loopback, link-local or reserved ranges (for example `10.x`, `127.0.0.1`,
`169.254.169.254`, `::1`) are refused when you save and again on every send.

Caveat: the check resolves the host name, then the HTTP client resolves it again to connect. An
attacker who controls a DNS server could answer differently between the two (DNS rebinding). Only
register URLs you trust, and keep `WEBHOOK_ALLOW_PRIVATE_HOSTS` off unless you need it.
