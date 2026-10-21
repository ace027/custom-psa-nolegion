"""Service events: ticket and RMM alert facts, fanned out to the webhook outbox (and, at depth 0,
to automation rules registered in RULE_HOOK by plan 07-04).

Payloads carry facts and a link only: never the ticket description, notes or email text."""

import logging
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from datetime import UTC, datetime

from app.config import get_settings
from app.deps import Ctx
from app.models import RmmAlert, Ticket

log = logging.getLogger("psa.events")

EVENT_TYPES = (
    "ticket.created",
    "ticket.assigned",
    "ticket.status_changed",
    "ticket.priority_changed",
    "ticket.customer_reply",
    "ticket.sla_breached",
    "rmm_alert.opened",
    "rmm_alert.cleared",
)
RULE_TRIGGERS = EVENT_TYPES

# Automation depth: rule actions raise it while they run so their own changes do not re-trigger
# rules (webhooks still fire at any depth).
automation_depth: ContextVar[int] = ContextVar("automation_depth", default=0)

# Called as hook(ctx, type, event_id, ticket, alert, changes). Plan 07-04 registers into it.
RULE_HOOK: list[Callable] = []


def payload(
    type: str,
    event_id: uuid.UUID,
    ticket: Ticket,
    alert: RmmAlert | None = None,
    changes: dict | None = None,
) -> dict:
    base = get_settings().public_url.rstrip("/")
    body: dict = {
        "version": 1,
        "id": str(event_id),
        "type": type,
        "occurred_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "ticket": {
            "id": ticket.id,
            "number": ticket.number,
            "subject": ticket.subject,
            "status": ticket.status,
            "priority": ticket.priority.name if ticket.priority else None,
            "organization": ticket.organization.name if ticket.organization else None,
            "assignee": ticket.assignee.display_name if ticket.assignee else None,
            "source": ticket.source,
            "url": f"{base}/tickets/{ticket.id}",
        },
        "changes": changes or {},
    }
    if alert is not None:
        body["alert"] = {
            "id": alert.id,
            "severity": alert.severity,
            "state": alert.state,
            "message": alert.message,
            "device_external_id": alert.device_external_id,
            "resolution": alert.resolution,
        }
    return body


def emit(
    ctx: Ctx,
    type: str,
    ticket: Ticket,
    *,
    alert: RmmAlert | None = None,
    changes: dict | None = None,
) -> uuid.UUID:
    from app import webhooks

    event_id = uuid.uuid4()
    try:
        with ctx.db.begin_nested():  # an outbox problem must never undo the ticket change
            webhooks.enqueue(ctx, type, event_id, payload(type, event_id, ticket, alert, changes))
    except Exception:  # noqa: BLE001
        log.exception("could not queue webhook event %s", type)
    if automation_depth.get() == 0:
        for hook in list(RULE_HOOK):
            hook(ctx, type, event_id, ticket, alert, changes)
    return event_id
