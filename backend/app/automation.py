"""Automation rules: "when this event happens and these conditions hold, do these actions".

Safety rules (each covered by tests):
- Rules only run at automation depth 0. While a rule's actions run the depth is raised, so a
  change made by a rule never triggers another rule (webhooks still fire at any depth).
- A rule runs at most once per event (unique run row), and never more than RATE_CAP times an
  hour; past that it is switched off and an audit row says so.
- Every action runs in its own savepoint: one failing action is recorded as 'failed' in the
  trace and never undoes the ticket change or the other actions.
- Dry runs evaluate and describe, and write nothing.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app import audit, events, notifications, ticket_links, webhooks
from app import repositories as repo
from app import ticket_services as tsvc
from app.deps import Ctx
from app.errors import Conflict, NotFound
from app.models import (
    AutomationRule,
    AutomationRun,
    Category,
    Priority,
    Queue,
    RmmAlert,
    Ticket,
    TicketType,
    User,
    WebhookEndpoint,
)

log = logging.getLogger("psa.automation")

RATE_CAP = 200  # runs of one rule per rolling hour
DISABLED_REASON = f"Fired more than {RATE_CAP} times in an hour"
ACTIONS = (
    "assign",
    "set_queue",
    "set_priority",
    "escalate",
    "notify",
    "webhook",
    "create_ticket",
)
MAX_CONDITIONS = 20
MAX_ACTIONS = 10
MAX_LIST = 50
STATUSES = ("new", "open", "waiting_on_customer", "resolved", "closed")
SOURCES = ("manual", "email", "portal", "rmm", "api", "rule")
SEVERITIES = ("NONE", "MINOR", "MODERATE", "MAJOR", "CRITICAL")

_ID_OPS = ("eq", "ne", "in", "not_in")
_NULLABLE_ID_OPS = _ID_OPS + ("is_empty", "is_not_empty")
# field -> allowed ops and value type. Types: id:<lookup>, choice, text.
FIELDS: dict[str, dict] = {
    "organization_id": {"ops": _NULLABLE_ID_OPS, "type": "id", "ref": "organization"},
    "queue_id": {"ops": _ID_OPS, "type": "id", "ref": "queue"},
    "category_id": {"ops": _NULLABLE_ID_OPS, "type": "id", "ref": "category"},
    "priority_id": {"ops": _ID_OPS, "type": "id", "ref": "priority"},
    "ticket_type_id": {"ops": _NULLABLE_ID_OPS, "type": "id", "ref": "ticket_type"},
    "assignee_id": {"ops": _NULLABLE_ID_OPS, "type": "id", "ref": "user"},
    "status": {"ops": _ID_OPS, "type": "choice", "choices": STATUSES},
    "source": {"ops": _ID_OPS, "type": "choice", "choices": SOURCES},
    "subject": {
        "ops": ("eq", "ne", "contains", "is_empty", "is_not_empty"),
        "type": "text",
    },
    "alert_severity": {"ops": _ID_OPS, "type": "choice", "choices": SEVERITIES},
}
NO_VALUE_OPS = ("is_empty", "is_not_empty")
ACTION_PARAMS = {
    "assign": ("user_id",),
    "set_queue": ("queue_id",),
    "set_priority": ("priority_id",),
    "escalate": (),
    "notify": ("user_id",),
    "webhook": ("endpoint_id",),
    "create_ticket": ("subject", "queue_id", "priority_id"),
}


def _now() -> datetime:
    return datetime.now(UTC)


# ---- facts and evaluation (pure) ------------------------------------------------------------
def facts(ticket: Ticket, alert: RmmAlert | None = None) -> dict:
    return {
        "organization_id": ticket.organization_id,
        "queue_id": ticket.queue_id,
        "category_id": ticket.category_id,
        "priority_id": ticket.priority_id,
        "ticket_type_id": ticket.type_id,
        "status": ticket.status,
        "source": ticket.source,
        "assignee_id": ticket.assignee_id,
        "subject": ticket.subject,
        "alert_severity": alert.severity if alert is not None else None,
    }


def _test(op: str, actual: Any, value: Any) -> bool:
    if op == "eq":
        return actual == value
    if op == "ne":
        return actual != value
    if op == "in":
        return isinstance(value, list) and actual in value
    if op == "not_in":
        return isinstance(value, list) and actual not in value
    if op == "contains":
        return (
            isinstance(actual, str) and isinstance(value, str) and value.lower() in actual.lower()
        )
    if op == "is_empty":
        return actual is None or actual == ""
    if op == "is_not_empty":
        return not (actual is None or actual == "")
    return False


def evaluate(conditions: list[dict], fact_values: dict) -> tuple[bool, list[dict]]:
    """AND of all conditions (none = always). Returns (matched, per-condition trace)."""
    trace = []
    for cond in conditions:
        field, op, value = cond.get("field"), cond.get("op"), cond.get("value")
        actual = fact_values.get(field)
        ok = field in FIELDS and op in FIELDS[field]["ops"] and _test(op, actual, value)
        trace.append(
            {"field": field, "op": op, "value": value, "actual": actual, "matched": bool(ok)}
        )
    return all(t["matched"] for t in trace), trace


# ---- validation -----------------------------------------------------------------------------
def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _check_ref(ctx: Ctx, ref: str, obj_id: Any) -> None:
    if not _is_int(obj_id):
        raise Conflict(f"{ref.replace('_', ' ').capitalize()} must be an id")
    if ref == "organization":
        ok = repo.get_organization(ctx.db, ctx.scope, obj_id) is not None
    elif ref == "user":
        user = repo.get_user(ctx.db, obj_id)
        ok = user is not None
    else:
        model = {
            "queue": Queue,
            "category": Category,
            "priority": Priority,
            "ticket_type": TicketType,
        }[ref]
        ok = repo.get_lookup(ctx.db, model, obj_id) is not None
    if not ok:
        raise Conflict(f"Unknown {ref.replace('_', ' ')} ({obj_id})")


def _check_condition(ctx: Ctx, trigger: str, cond: Any) -> dict:
    if not isinstance(cond, dict):
        raise Conflict("Each condition must be an object")
    field, op, value = cond.get("field"), cond.get("op"), cond.get("value")
    spec = FIELDS.get(field) if isinstance(field, str) else None
    if spec is None:
        raise Conflict(f"Unknown condition field: {field}")
    if op not in spec["ops"]:
        if op == "contains":
            raise Conflict("'contains' only works on the subject")
        raise Conflict(f"'{op}' is not allowed for {field}")
    if field == "alert_severity" and not trigger.startswith("rmm_alert."):
        raise Conflict("alert_severity only applies to rmm_alert.* triggers")
    if op in NO_VALUE_OPS:
        return {"field": field, "op": op, "value": None}
    if op in ("in", "not_in"):
        if not isinstance(value, list) or not value or len(value) > MAX_LIST:
            raise Conflict(f"'{op}' needs a list of 1 to {MAX_LIST} values")
        items = value
    else:
        items = [value]
    for item in items:
        if spec["type"] == "id":
            _check_ref(ctx, spec["ref"], item)
        elif spec["type"] == "choice":
            if item not in spec["choices"]:
                raise Conflict(f"{field} must be one of: {', '.join(spec['choices'])}")
        else:  # text
            if not isinstance(item, str) or not item.strip() or len(item) > 200:
                raise Conflict("Subject values must be 1 to 200 characters")
    return {"field": field, "op": op, "value": value}


def _check_action(ctx: Ctx, act: Any) -> dict:
    if not isinstance(act, dict):
        raise Conflict("Each action must be an object")
    kind = act.get("type")
    if kind not in ACTIONS:
        raise Conflict(f"Unknown action type: {kind}")
    allowed = ACTION_PARAMS[kind]
    extra = [k for k in act if k != "type" and k not in allowed]
    if extra:
        raise Conflict(f"Unknown parameter for {kind}: {extra[0]}")
    out: dict = {"type": kind}
    if kind in ("assign", "notify"):
        uid = act.get("user_id")
        user = repo.get_user(ctx.db, uid) if _is_int(uid) else None
        if user is None or not user.is_active:
            raise Conflict("Choose an active user")
        if kind == "assign" and user.role not in tsvc.ASSIGNABLE_ROLES:
            raise Conflict("Assignee must be an active admin or tech")
        out["user_id"] = uid
    elif kind == "set_queue":
        _check_active(ctx, Queue, act.get("queue_id"), "queue")
        out["queue_id"] = act["queue_id"]
    elif kind == "set_priority":
        _check_active(ctx, Priority, act.get("priority_id"), "priority")
        out["priority_id"] = act["priority_id"]
    elif kind == "webhook":
        eid = act.get("endpoint_id")
        if not _is_int(eid) or ctx.db.get(WebhookEndpoint, eid) is None:
            raise Conflict("Unknown webhook endpoint")
        out["endpoint_id"] = eid
    elif kind == "create_ticket":
        subject = act.get("subject")
        if not isinstance(subject, str) or not 1 <= len(subject.strip()) <= 200:
            raise Conflict("The new ticket's subject must be 1 to 200 characters")
        out["subject"] = subject.strip()
        for key, model, label in (
            ("queue_id", Queue, "queue"),
            ("priority_id", Priority, "priority"),
        ):
            if act.get(key) is not None:
                _check_active(ctx, model, act[key], label)
                out[key] = act[key]
    return out


def _check_active(ctx: Ctx, model, obj_id: Any, label: str) -> None:
    obj = repo.get_lookup(ctx.db, model, obj_id) if _is_int(obj_id) else None
    if obj is None or obj.archived_at is not None:
        raise Conflict(f"Unknown or archived {label}")


def validate(ctx: Ctx, data: dict) -> dict:
    """Check a whole rule. Returns the normalised rule or raises Conflict."""
    name = (data.get("name") or "").strip() if isinstance(data.get("name"), str) else ""
    if not 1 <= len(name) <= 100:
        raise Conflict("Give the rule a name of 1 to 100 characters")
    trigger = data.get("trigger")
    if trigger not in events.RULE_TRIGGERS:
        raise Conflict(f"Unknown trigger: {trigger}")
    conditions = data.get("conditions") or []
    if not isinstance(conditions, list) or len(conditions) > MAX_CONDITIONS:
        raise Conflict(f"A rule can have up to {MAX_CONDITIONS} conditions")
    actions = data.get("actions")
    if not isinstance(actions, list) or not 1 <= len(actions) <= MAX_ACTIONS:
        raise Conflict(f"A rule needs 1 to {MAX_ACTIONS} actions")
    position = data.get("position", 0)
    if not _is_int(position) or not 0 <= position <= 10000:
        raise Conflict("Position must be a whole number from 0 to 10000")
    return {
        "name": name,
        "trigger": trigger,
        "enabled": bool(data.get("enabled", True)),
        "position": position,
        "conditions": [_check_condition(ctx, trigger, c) for c in conditions],
        "actions": [_check_action(ctx, a) for a in actions],
    }


# ---- actions --------------------------------------------------------------------------------
def _params(act: dict) -> dict:
    return {k: v for k, v in act.items() if k != "type"}


def _name_of(ctx: Ctx, model, obj_id: int | None) -> str:
    obj = ctx.db.get(model, obj_id) if obj_id is not None else None
    if obj is None:
        return f"#{obj_id}"
    return getattr(obj, "display_name", None) or getattr(obj, "name", None) or f"#{obj_id}"


def _next_higher_priority(ctx: Ctx, ticket: Ticket) -> Priority | None:
    return ctx.db.execute(
        select(Priority)
        .where(Priority.archived_at.is_(None), Priority.rank < ticket.priority.rank)
        .order_by(Priority.rank.desc())
        .limit(1)
    ).scalar_one_or_none()


def _run_action(
    ctx: Ctx,
    rule: AutomationRule,
    act: dict,
    event_type: str,
    event_id: uuid.UUID,
    ticket: Ticket,
    alert: RmmAlert | None,
    changes: dict | None,
) -> tuple[str, str]:
    kind = act["type"]
    if kind == "assign":
        if ticket.assignee_id == act["user_id"]:
            return "skipped", "already assigned to that user"
        tsvc.update_ticket(ctx, ticket.id, {"assignee_id": act["user_id"]})
        return "done", f"Assigned to {_name_of(ctx, User, act['user_id'])}"
    if kind == "set_queue":
        if ticket.queue_id == act["queue_id"]:
            return "skipped", "already in that queue"
        tsvc.update_ticket(ctx, ticket.id, {"queue_id": act["queue_id"]})
        return "done", f"Moved to queue {_name_of(ctx, Queue, act['queue_id'])}"
    if kind == "set_priority":
        if ticket.priority_id == act["priority_id"]:
            return "skipped", "already that priority"
        tsvc.update_ticket(ctx, ticket.id, {"priority_id": act["priority_id"]})
        return "done", f"Priority set to {_name_of(ctx, Priority, act['priority_id'])}"
    if kind == "escalate":
        higher = _next_higher_priority(ctx, ticket)
        if higher is None:
            return "skipped", "already most urgent"
        tsvc.update_ticket(ctx, ticket.id, {"priority_id": higher.id})
        tsvc.system_note(ctx, ticket, f"Escalated by rule {rule.name}")
        return "done", f"Priority raised to {higher.name}"
    if kind == "notify":
        sent = notifications.notify(
            ctx, act["user_id"], ticket, "rule_notify", f"rule:{rule.id}:{event_id}"
        )
        if not sent:
            return "skipped", "not sent (notifications off, mail not configured or duplicate)"
        return "done", f"Emailed {_name_of(ctx, User, act['user_id'])}"
    if kind == "webhook":
        body = events.payload(event_type, event_id, ticket, alert, changes)
        try:
            with ctx.db.begin_nested():
                queued = webhooks.enqueue(
                    ctx, event_type, event_id, body, endpoint_ids=[act["endpoint_id"]]
                )
        except IntegrityError:
            return "skipped", "that endpoint already receives this event"
        if not queued:
            return "skipped", "webhook is disabled"
        return "done", f"Queued for {_name_of(ctx, WebhookEndpoint, act['endpoint_id'])}"
    if kind == "create_ticket":
        if ticket.organization_id is None:
            return "skipped", "the ticket has no organization"
        data = {
            "organization_id": ticket.organization_id,
            "subject": act["subject"],
            "description": f"Created by automation rule {rule.name} from ticket #{ticket.number}.",
        }
        for key in ("queue_id", "priority_id"):
            if act.get(key) is not None:
                data[key] = act[key]
        new = tsvc.create_ticket(ctx, data, source="rule")
        ticket_links.link_related(ctx, ticket.organization_id, ticket, new)
        return "done", f"Created ticket #{new.number}"
    return "failed", f"Unknown action {kind}"


def _execute(
    ctx: Ctx,
    rule: AutomationRule,
    event_type: str,
    event_id: uuid.UUID,
    ticket: Ticket,
    alert: RmmAlert | None,
    changes: dict | None,
) -> list[dict]:
    out: list[dict] = []
    token = events.automation_depth.set(1)
    try:
        for act in rule.actions:
            try:
                with ctx.db.begin_nested():
                    status, detail = _run_action(
                        ctx, rule, act, event_type, event_id, ticket, alert, changes
                    )
            except Exception as exc:  # noqa: BLE001 - one bad action never stops the rest
                status, detail = "failed", f"{type(exc).__name__}: {exc}"[:200]
                log.warning("automation rule %s action %s failed: %s", rule.id, act["type"], detail)
            out.append(
                {"type": act["type"], "params": _params(act), "status": status, "detail": detail}
            )
    finally:
        events.automation_depth.reset(token)
    return out


# ---- the event hook -------------------------------------------------------------------------
def _runs_last_hour(ctx: Ctx, rule_id: int) -> int:
    return ctx.db.scalar(
        select(func.count())
        .select_from(AutomationRun)
        .where(
            AutomationRun.rule_id == rule_id,
            AutomationRun.dry_run.is_(False),
            AutomationRun.matched.is_(True),
            AutomationRun.created_at >= _now() - timedelta(hours=1),
        )
    )


def _check_rate_window_clear(ctx: Ctx, rule_id: int) -> None:
    """Refuse to re-enable a rule whose rate window is still full: it would be switched
    straight off again. Tells the admin when the window will have room."""
    count = _runs_last_hour(ctx, rule_id)
    if count < RATE_CAP:
        return
    # The run that must age out for the count to drop below the cap.
    pivot = ctx.db.scalar(
        select(AutomationRun.created_at)
        .where(
            AutomationRun.rule_id == rule_id,
            AutomationRun.dry_run.is_(False),
            AutomationRun.matched.is_(True),
            AutomationRun.created_at >= _now() - timedelta(hours=1),
        )
        .order_by(AutomationRun.created_at)
        .offset(count - RATE_CAP)
        .limit(1)
    )
    when = (pivot + timedelta(hours=1)).astimezone(UTC).strftime("%H:%M UTC") if pivot else "soon"
    raise Conflict(
        f"This rule fired {count} times in the last hour. It can be turned back on after {when}"
    )


def on_event(
    ctx: Ctx,
    type: str,
    event_id: uuid.UUID,
    ticket: Ticket,
    alert: RmmAlert | None,
    changes: dict | None,
) -> None:
    rules = list(
        ctx.db.scalars(
            select(AutomationRule)
            .where(
                AutomationRule.trigger == type,
                AutomationRule.enabled.is_(True),
                AutomationRule.archived_at.is_(None),
            )
            .order_by(AutomationRule.position, AutomationRule.id)
        )
    )
    for rule in rules:
        try:
            _process(ctx, rule, type, event_id, ticket, alert, changes)
        except Exception:  # noqa: BLE001 - a rules problem never undoes the ticket change
            log.exception("automation rule %s failed on %s", rule.id, type)


def purge_old(ctx: Ctx, runs_days: int = 30, deliveries_days: int = 90) -> tuple[int, int]:
    """Retention: delete old automation runs and finished webhook deliveries through the
    SECURITY DEFINER purge function (psa_app has no DELETE grant). Returns (runs, deliveries)."""
    row = ctx.db.execute(
        text("SELECT * FROM purge_automation_data(:r, :d)"),
        {"r": runs_days, "d": deliveries_days},
    ).one()
    return int(row[0]), int(row[1])


def _process(ctx, rule, type, event_id, ticket, alert, changes) -> None:
    if _runs_last_hour(ctx, rule.id) >= RATE_CAP:
        rule.enabled = False
        rule.disabled_reason = DISABLED_REASON
        ctx.db.flush()
        audit.record(
            ctx.db,
            ctx.user,
            "automation.rule_auto_disabled",
            rule,
            detail={"rule_id": rule.id, "reason": DISABLED_REASON},
        )
        return
    matched, cond_trace = evaluate(rule.conditions, facts(ticket, alert))
    run = AutomationRun(
        rule_id=rule.id,
        event_id=event_id,
        event_type=type,
        ticket_id=ticket.id,
        matched=matched,
        dry_run=False,
        trace={"conditions": cond_trace, "actions": []},
    )
    try:
        with ctx.db.begin_nested():
            ctx.db.add(run)
            ctx.db.flush()
    except IntegrityError:
        return  # this rule already ran for this event
    if not matched:
        return
    action_trace = _execute(ctx, rule, type, event_id, ticket, alert, changes)
    run.trace = {"conditions": cond_trace, "actions": action_trace}
    rule.fire_count += 1
    rule.last_fired_at = _now()
    ctx.db.flush()
    audit.record(
        ctx.db,
        ctx.user,
        "automation.rule_fired",
        rule,
        organization_id=ticket.organization_id,
        detail={
            "rule_id": rule.id,
            "event_id": str(event_id),
            "ticket_id": ticket.id,
            "actions": [a["status"] for a in action_trace],
        },
    )


# ---- dry run --------------------------------------------------------------------------------
def _alert_for(ctx: Ctx, ticket_id: int) -> RmmAlert | None:
    return ctx.db.scalars(
        select(RmmAlert)
        .where(RmmAlert.ticket_id == ticket_id)
        .order_by(RmmAlert.id.desc())
        .limit(1)
    ).first()


def _describe(ctx: Ctx, act: dict, ticket: Ticket) -> tuple[str, str]:
    kind = act["type"]
    if kind == "assign":
        return "would_run", f"Assign to {_name_of(ctx, User, act['user_id'])}"
    if kind == "set_queue":
        return "would_run", f"Move to queue {_name_of(ctx, Queue, act['queue_id'])}"
    if kind == "set_priority":
        return "would_run", f"Set priority to {_name_of(ctx, Priority, act['priority_id'])}"
    if kind == "escalate":
        higher = _next_higher_priority(ctx, ticket)
        if higher is None:
            return "would_skip", "already most urgent"
        return "would_run", f"Raise priority to {higher.name}"
    if kind == "notify":
        return "would_run", f"Email {_name_of(ctx, User, act['user_id'])}"
    if kind == "webhook":
        return "would_run", f"Send to {_name_of(ctx, WebhookEndpoint, act['endpoint_id'])}"
    if ticket.organization_id is None:
        return "would_skip", "the ticket has no organization"
    return "would_run", f"Create ticket '{act['subject']}'"


def dry_run(ctx: Ctx, rule_id: int | None, rule: dict | None, ticket_id: int) -> dict:
    """Evaluate a saved or unsaved rule against a ticket. Writes nothing."""
    if (rule_id is None) == (rule is None):
        raise Conflict("Give either rule_id or rule, not both")
    ticket = repo.get_ticket(ctx.db, ctx.scope, ticket_id)
    if ticket is None:
        raise NotFound("Ticket not found")
    if rule_id is not None:
        row = _get(ctx, rule_id)  # a saved rule is shown as it is, even if a reference has aged
        spec = {"trigger": row.trigger, "conditions": row.conditions, "actions": row.actions}
    else:
        spec = validate(ctx, rule or {})
    alert = _alert_for(ctx, ticket.id)
    matched, cond_trace = evaluate(spec["conditions"], facts(ticket, alert))
    actions = []
    if matched:
        for act in spec["actions"]:
            status, detail = _describe(ctx, act, ticket)
            actions.append(
                {"type": act["type"], "params": _params(act), "status": status, "detail": detail}
            )
    return {
        "matched": matched,
        "trigger": spec["trigger"],
        "conditions": cond_trace,
        "actions": actions,
    }


# ---- management -----------------------------------------------------------------------------
def _get(ctx: Ctx, rule_id: int) -> AutomationRule:
    rule = ctx.db.get(AutomationRule, rule_id)
    if rule is None:
        raise NotFound("Rule not found")
    return rule


def _snap(rule: AutomationRule) -> dict:
    return {
        "name": rule.name,
        "enabled": rule.enabled,
        "trigger": rule.trigger,
        "conditions": rule.conditions,
        "actions": rule.actions,
        "position": rule.position,
    }


def create(ctx: Ctx, data: dict) -> AutomationRule:
    spec = validate(ctx, data)
    rule = AutomationRule(**spec, created_by_id=ctx.user.id)
    ctx.db.add(rule)
    ctx.db.flush()
    ctx.db.refresh(rule)
    audit.record(ctx.db, ctx.user, "automation.rule_created", rule, after=_snap(rule))
    return rule


def update(ctx: Ctx, rule_id: int, data: dict) -> AutomationRule:
    rule = _get(ctx, rule_id)
    if rule.archived_at is not None:
        raise Conflict("An archived rule cannot be edited")
    before = _snap(rule)
    spec = validate(ctx, {**before, **data})
    for key, value in spec.items():
        setattr(rule, key, value)
    if rule.enabled and not before["enabled"]:
        _check_rate_window_clear(ctx, rule.id)
        rule.disabled_reason = None
    rule.updated_at = _now()
    ctx.db.flush()
    audit.record(
        ctx.db, ctx.user, "automation.rule_updated", rule, before=before, after=_snap(rule)
    )
    return rule


def archive(ctx: Ctx, rule_id: int) -> AutomationRule:
    rule = _get(ctx, rule_id)
    if rule.archived_at is not None:
        raise Conflict("That rule is already archived")
    before = _snap(rule)
    rule.archived_at = _now()
    rule.enabled = False
    rule.updated_at = _now()
    ctx.db.flush()
    audit.record(
        ctx.db, ctx.user, "automation.rule_archived", rule, before=before, after=_snap(rule)
    )
    return rule


def list_rules(ctx: Ctx, include_archived: bool = False) -> list[AutomationRule]:
    q = select(AutomationRule).order_by(AutomationRule.position, AutomationRule.id)
    if not include_archived:
        q = q.where(AutomationRule.archived_at.is_(None))
    return list(ctx.db.scalars(q))


def runs(ctx: Ctx, rule_id: int, limit: int = 50) -> list[AutomationRun]:
    _get(ctx, rule_id)
    return list(
        ctx.db.scalars(
            select(AutomationRun)
            .where(AutomationRun.rule_id == rule_id, AutomationRun.dry_run.is_(False))
            .order_by(AutomationRun.id.desc())
            .limit(max(1, min(limit, 200)))
        )
    )
