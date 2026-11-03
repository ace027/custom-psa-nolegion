"""Plain-English text for audit rows. Pure functions, no DB."""

import json
from decimal import Decimal

_LABELS = {
    "time_entries": "time entry",
    "credit_memos": "credit memo",
    "billing_runs": "billing run",
    "purchase_orders": "purchase order",
    "settings": "settings",
    "email_messages": "email",
    "organizations": "client",
}

_VERBS = {
    "create": "created",
    "update": "updated",
    "delete": "deleted",
    "archive": "archived",
    "unarchive": "restored",
    "void": "voided",
    "apply": "applied",
    "refund": "refunded",
    "write_off": "wrote off",
    "finalize": "finalized",
    "approve": "approved",
    "reject": "rejected",
    "send": "sent",
    "dismiss": "dismissed",
    "receive": "received",
    "send_failed": "could not send",
    "login": "signed in",
    "logout": "signed out",
    "role_changed": "changed the role of",
    "created": "created",
    "updated": "updated",
    "deleted": "deleted",
    "credentials_changed": "changed the credentials of",
    "email_reply": "emailed a reply on",
}

_SKIP = {"id", "created_at", "updated_at"}
_HIDDEN = ("secret", "token", "password")


def _human(s: str) -> str:
    return s.replace("_", " ")


def record_label(entity_type: str) -> str:
    if entity_type in _LABELS:
        return _LABELS[entity_type]
    s = entity_type
    if s.endswith("ies"):
        s = s[:-3] + "y"
    elif s.endswith("sses"):
        s = s[:-2]
    elif s.endswith("s"):
        s = s[:-1]
    return _human(s)


def _verb(action: str) -> str:
    seg = action.rsplit(".", 1)[-1]
    return _VERBS.get(seg, _human(seg))


def summary(entry, actor_name: str | None, organization_name: str | None) -> str:
    if actor_name:
        actor = actor_name
    elif entry.actor_type == "system":
        actor = "System"
    elif entry.actor_type == "anonymous":
        actor = "Someone (not signed in)"
    else:
        actor = f"User #{entry.actor_id}"
    verb = _verb(entry.action)
    if not entry.entity_type:
        return f"{actor} {verb} ({_human(entry.action.split('.', 1)[0])})"
    text = f"{actor} {verb} {record_label(entry.entity_type)}"
    if entry.entity_id is not None:
        text += f" #{entry.entity_id}"
    if organization_name:
        text += f" for {organization_name}"
    return text


def _cut(s: str) -> str:
    return s[:200]


def _fmt(key: str, v) -> str:
    if v is None:
        return "(empty)"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if key.endswith("_cents") and isinstance(v, int | str | float):
        try:
            return f"{Decimal(v) / 100:,.2f}"
        except ArithmeticError:
            pass
    if key.endswith("_minutes") and isinstance(v, int):
        return f"{v // 60} h {v % 60} min"
    if isinstance(v, list | dict):
        return _cut(json.dumps(v, separators=(",", ":"), default=str))
    return _cut(str(v))


def changes(before: dict | None, after: dict | None) -> list[dict]:
    before, after = before or {}, after or {}
    out = []
    for key in sorted(set(before) | set(after)):
        if key in _SKIP or before.get(key) == after.get(key):
            continue
        label = key
        for suffix in ("_cents", "_minutes"):
            label = label.removesuffix(suffix)
        if any(w in key for w in _HIDDEN):
            b = a = "(changed)"
        else:
            b, a = _fmt(key, before.get(key)), _fmt(key, after.get(key))
        out.append({"field": key, "label": _human(label), "before": b, "after": a})
    return out
