"""Poll NinjaOne for active alerts and keep tickets in step. Read-only toward the vendor.

Guarantees (each covered by tests):
- One open ticket per alert condition: polling the same alert again never makes a second ticket.
- A vendor failure changes nothing except the integration's last-error and last-polled stamps.
- One alert that cannot be saved never stops the others (each runs in its own savepoint).
- When an alert clears, the ticket is resolved or noted per the configured rule; a ticket a
  technician has touched is never resolved behind their back under the default rule.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app import audit, ticket_links
from app import repositories as repo
from app import ticket_services as tsvc
from app.asset_sync import safe_error
from app.deps import Ctx
from app.errors import Conflict
from app.integrations import registry
from app.integrations.base import SEVERITIES, RemoteAlert
from app.models import (
    Asset,
    AssetSource,
    Integration,
    IntegrationClientMap,
    Priority,
    RmmAlert,
    Ticket,
    TicketNote,
    TimeEntry,
)

log = logging.getLogger("psa.alerts")

SEVERITY_ORDER = {s: i for i, s in enumerate(SEVERITIES)}
CLEAR_RULES = ("resolve_if_untouched", "always_resolve", "note_only")
DEFAULTS = {
    "alerts_enabled": False,
    "alert_min_severity": "MODERATE",
    "alert_clear_rule": "resolve_if_untouched",
    "alert_poll_minutes": 5,
}
DONE = ("resolved", "closed")
CLEAR_AFTER_MISSES = 2
CLEAR_AFTER_EMPTY_POLLS = 3
MAX_NEW_TICKETS_PER_POLL = 25
MESSAGE_MAX = 1000


@dataclass
class PollResult:
    created: int = 0
    repeated: int = 0
    cleared: int = 0
    resolved: int = 0
    noted: int = 0
    skipped_unmapped: int = 0
    skipped_severity: int = 0
    failed: int = 0
    deferred: int = 0
    suspicious: bool = False
    error: str | None = None


def settings(integration: Integration) -> dict:
    config = integration.config if isinstance(integration.config, dict) else {}
    return {**DEFAULTS, **config}


def _now() -> datetime:
    return datetime.now(UTC)


def due(ctx: Ctx, now: datetime) -> list[Integration]:
    """Enabled NinjaOne integrations with alerts on that were asked to poll or are past due."""
    out = []
    for i in ctx.db.scalars(
        select(Integration)
        .where(Integration.kind == "ninjaone", Integration.enabled.is_(True))
        .order_by(Integration.id)
    ):
        s = settings(i)
        if s["alerts_enabled"] is not True or not i.credentials:
            continue
        minutes = s["alert_poll_minutes"]
        if isinstance(minutes, bool) or not isinstance(minutes, int) or not 1 <= minutes <= 60:
            minutes = DEFAULTS["alert_poll_minutes"]
        if (
            i.alerts_requested_at is not None
            or i.alerts_polled_at is None
            or i.alerts_polled_at <= now - timedelta(minutes=minutes)
        ):
            out.append(i)
    return out


def priority_for(ctx: Ctx, severity: str) -> Priority:
    """CRITICAL -> most urgent priority, MAJOR -> second most urgent (or the first when only one
    exists), everything else -> the default priority."""
    active = list(
        ctx.db.scalars(
            select(Priority).where(Priority.archived_at.is_(None)).order_by(Priority.rank)
        )
    )
    if severity == "CRITICAL" and active:
        return active[0]
    if severity == "MAJOR" and active:
        return active[1] if len(active) > 1 else active[0]
    chosen = repo.get_default(ctx.db, Priority) or (active[0] if active else None)
    if chosen is None:
        raise Conflict("No ticket priority is configured")
    return chosen


def _description(alert: RemoteAlert, asset: Asset, first_seen: datetime, message: str) -> str:
    return "\n".join(
        [
            f"Severity: {alert.severity}",
            f"Device: {asset.name}",
            f"NinjaOne device id: {alert.device_external_id}",
            f"Condition: {alert.condition_key}",
            f"Message: {message}",
            f"First seen: {first_seen.isoformat(timespec='seconds')}",
        ]
    )


def _create(
    ctx: Ctx,
    integration: Integration,
    alert: RemoteAlert,
    asset: Asset,
    now: datetime,
    previous_ticket: Ticket | None,
) -> RmmAlert:
    first_seen = alert.created_at or now
    message = alert.message[:MESSAGE_MAX]
    subject = " ".join(f"[RMM] {asset.name}: {message}".split())[:200]
    ticket = tsvc.create_ticket(
        ctx,
        {
            "organization_id": asset.organization_id,
            "subject": subject,
            "description": _description(alert, asset, first_seen, message),
            "priority_id": priority_for(ctx, alert.severity).id,
        },
        source="rmm",
    )
    ticket.asset_id = asset.id
    ctx.db.flush()
    row = RmmAlert(
        organization_id=asset.organization_id,
        integration_id=integration.id,
        external_id=alert.external_id,
        condition_key=alert.condition_key,
        device_external_id=alert.device_external_id,
        asset_id=asset.id,
        ticket_id=ticket.id,
        severity=alert.severity,
        message=message,
        state="open",
        first_seen_at=now,
        last_seen_at=now,
    )
    ctx.db.add(row)
    ctx.db.flush()
    if previous_ticket is not None and previous_ticket.organization_id == ticket.organization_id:
        ticket_links.link_related(ctx, ticket.organization_id, ticket, previous_ticket)
    audit.record(
        ctx.db,
        None,
        "rmm_alert.ticket_created",
        row,
        organization_id=row.organization_id,
        detail={"ticket_id": ticket.id, "ticket_number": ticket.number, "severity": row.severity},
    )
    return row


def _previous_ticket(ctx: Ctx, integration: Integration, condition_key: str) -> Ticket | None:
    row = ctx.db.scalar(
        select(RmmAlert)
        .where(
            RmmAlert.integration_id == integration.id,
            RmmAlert.condition_key == condition_key,
            RmmAlert.ticket_id.is_not(None),
        )
        .order_by(RmmAlert.id.desc())
        .limit(1)
    )
    return ctx.db.get(Ticket, row.ticket_id) if row is not None else None


def _apply_alert(
    ctx: Ctx, integration: Integration, alert: RemoteAlert, now: datetime, minimum: int, res
) -> None:
    open_row = ctx.db.scalar(
        select(RmmAlert).where(
            RmmAlert.integration_id == integration.id,
            RmmAlert.condition_key == alert.condition_key,
            RmmAlert.state == "open",
        )
    )
    if open_row is not None:
        open_row.missed_polls = 0  # still active in the vendor, whatever happens below
    if SEVERITY_ORDER.get(alert.severity, 0) < minimum:
        res.skipped_severity += 1
        return
    asset = ctx.db.scalar(
        select(Asset)
        .join(AssetSource, AssetSource.asset_id == Asset.id)
        .join(
            IntegrationClientMap,
            (IntegrationClientMap.integration_id == integration.id)
            & (IntegrationClientMap.psa_organization_id == Asset.organization_id)
            & (IntegrationClientMap.ignored.is_(False)),
        )
        .where(
            AssetSource.integration_id == integration.id,
            AssetSource.external_id == alert.device_external_id,
            Asset.retired_at.is_(None),
        )
        .limit(1)
    )
    if asset is None:
        res.skipped_unmapped += 1
        return
    superseding = False
    if open_row is not None:
        if open_row.external_id == alert.external_id:
            open_row.last_seen_at = now
            return
        ticket = ctx.db.get(Ticket, open_row.ticket_id) if open_row.ticket_id else None
        if ticket is None or ticket.status not in DONE:
            open_row.last_seen_at = now
            open_row.occurrences += 1
            open_row.external_id = alert.external_id
            res.repeated += 1
            audit.record(
                ctx.db,
                None,
                "rmm_alert.repeated",
                open_row,
                organization_id=open_row.organization_id,
                detail={"occurrences": open_row.occurrences, "external_id": alert.external_id},
            )
            return
        superseding = True
    if res.created >= MAX_NEW_TICKETS_PER_POLL:
        res.deferred += 1
        return
    if superseding:
        open_row.last_seen_at = now
        open_row.state, open_row.cleared_at, open_row.resolution = "cleared", now, "superseded"
        ctx.db.flush()
    _create(
        ctx, integration, alert, asset, now, _previous_ticket(ctx, integration, alert.condition_key)
    )
    res.created += 1


def _untouched(ctx: Ctx, ticket: Ticket) -> bool:
    if ticket.assignee_id is not None:
        return False
    human_note = ctx.db.scalar(
        select(TicketNote.id)
        .where(TicketNote.ticket_id == ticket.id, TicketNote.author_user_id.is_not(None))
        .limit(1)
    )
    if human_note is not None:
        return False
    time = ctx.db.scalar(
        select(TimeEntry.id)
        .where(TimeEntry.ticket_id == ticket.id, TimeEntry.voided_at.is_(None))
        .limit(1)
    )
    return time is None


def _clear(ctx: Ctx, row: RmmAlert, rule: str, now: datetime, res: PollResult) -> None:
    row.state, row.cleared_at = "cleared", now
    res.cleared += 1
    ticket = ctx.db.get(Ticket, row.ticket_id) if row.ticket_id else None
    stamp = now.isoformat(timespec="seconds")
    if ticket is None or ticket.status in DONE:
        row.resolution = "none"
    else:
        resolve = rule == "always_resolve" or (
            rule == "resolve_if_untouched" and _untouched(ctx, ticket)
        )
        if resolve:
            tsvc.system_note(
                ctx, ticket, f"Alert cleared in NinjaOne at {stamp}; resolved automatically."
            )
            tsvc.resolve_by_system(ctx, ticket)
            row.resolution = "resolved"
            res.resolved += 1
        else:
            why = (
                "ticket left open"
                if rule == "note_only"
                else "a technician has worked this ticket, so it was left open"
            )
            tsvc.system_note(ctx, ticket, f"Alert cleared in NinjaOne at {stamp}; {why}.")
            row.resolution = "noted"
            res.noted += 1
    ctx.db.flush()
    audit.record(
        ctx.db,
        None,
        "rmm_alert.cleared",
        row,
        organization_id=row.organization_id,
        detail={"rule": rule, "resolution": row.resolution},
    )


def _set_error(ctx: Ctx, integration: Integration, error: str | None, now: datetime) -> bool:
    """Store the poll's error text; True when it differs from what was already stored."""
    changed = error is not None and error != integration.alerts_last_error
    integration.alerts_last_error = error
    integration.alerts_polled_at = now
    integration.alerts_requested_at = None
    return changed


def poll(
    ctx: Ctx, integration: Integration, adapter=None, now: datetime | None = None
) -> PollResult:
    """One poll of one integration. Never raises for a vendor problem."""
    now = now or _now()
    res = PollResult()
    try:
        adapter = adapter or registry.build_adapter(integration)
        alerts = adapter.list_alerts()
    except Exception as exc:  # noqa: BLE001 - any adapter failure is a failed poll, not a crash
        res.error = safe_error(exc)[:2000]
        if _set_error(ctx, integration, res.error, now):
            audit.record(
                ctx.db,
                None,
                "integration.alerts_failed",
                integration,
                detail={"integration": integration.name, "error": res.error},
            )
        ctx.db.flush()
        return res

    s = settings(integration)
    minimum = SEVERITY_ORDER.get(s["alert_min_severity"], SEVERITY_ORDER["MODERATE"])
    rule = (
        s["alert_clear_rule"]
        if s["alert_clear_rule"] in CLEAR_RULES
        else DEFAULTS["alert_clear_rule"]
    )

    active: dict[str, RemoteAlert] = {}
    floor = datetime.min.replace(tzinfo=UTC)
    for a in alerts:
        kept = active.get(a.condition_key)
        if kept is None or (a.created_at or floor) > (kept.created_at or floor):
            active[a.condition_key] = a

    for alert in active.values():
        try:
            with ctx.db.begin_nested():
                _apply_alert(ctx, integration, alert, now, minimum, res)
        except Exception:  # noqa: BLE001 - one bad alert must not stop the rest
            log.exception("alert %s could not be processed", alert.condition_key)
            res.failed += 1

    open_rows = list(
        ctx.db.scalars(
            select(RmmAlert)
            .where(RmmAlert.integration_id == integration.id, RmmAlert.state == "open")
            .order_by(RmmAlert.id)
        )
    )
    # An empty list while alerts are open is more likely a vendor hiccup than a mass clear, so it
    # needs one more miss than usual. A real "everything cleared" still resolves a poll later.
    needed = CLEAR_AFTER_EMPTY_POLLS if not alerts else CLEAR_AFTER_MISSES
    for row in [r for r in open_rows if r.condition_key not in active]:
        row.missed_polls += 1
        if row.missed_polls < needed:
            continue
        counts = (res.cleared, res.resolved, res.noted)
        try:
            with ctx.db.begin_nested():
                _clear(ctx, row, rule, now, res)
        except Exception:  # noqa: BLE001
            log.exception("clearing alert %s failed", row.condition_key)
            res.cleared, res.resolved, res.noted = counts
            res.failed += 1
            ctx.db.refresh(row)
    suspicious_text = None
    if not alerts and open_rows:
        res.suspicious = True
        suspicious_text = (
            f"NinjaOne returned no active alerts while {len(open_rows)} are open; "
            f"clears wait for {CLEAR_AFTER_EMPTY_POLLS} empty polls in a row"
        )

    parts = []
    if suspicious_text:
        parts.append(suspicious_text)
    if res.failed:
        parts.append(f"{res.failed} alert(s) could not be processed; see the server log")
    if res.deferred:
        parts.append(
            f"{res.deferred} new alert(s) deferred to the next poll "
            f"(limit {MAX_NEW_TICKETS_PER_POLL} per poll)"
        )
    error = "; ".join(parts) or None
    changed = _set_error(ctx, integration, error, now)
    if res.suspicious and changed:
        audit.record(
            ctx.db,
            None,
            "integration.alerts_suspicious",
            integration,
            detail={"integration": integration.name, "open": len(open_rows)},
        )
    ctx.db.flush()
    return res
