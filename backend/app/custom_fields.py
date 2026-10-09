"""Custom fields on tickets: definitions per ticket type, values validated on the way in.

Values are stored on the ticket as JSON keyed by the field id (as a string), so renaming a field
never loses data. Fields that are archived, or that belong to a different type than the ticket's
current one, keep their stored values but are neither shown nor validated."""

import re
from datetime import date
from typing import Any

from sqlalchemy import select

from app.deps import Ctx
from app.errors import Conflict
from app.models import CustomField

MAX_TEXT = 2000
MAX_OPTIONS = 50
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def active_fields(ctx: Ctx, type_id: int | None) -> list[CustomField]:
    if type_id is None:
        return []
    return list(
        ctx.db.execute(
            select(CustomField)
            .where(CustomField.ticket_type_id == type_id, CustomField.archived_at.is_(None))
            .order_by(CustomField.position, CustomField.id)
        ).scalars()
    )


def validate_options(field_type: str, options: list[str] | None) -> list[str] | None:
    if field_type != "dropdown":
        if options:
            raise Conflict("Only dropdown fields have options")
        return None
    cleaned = [o.strip() for o in (options or []) if o and o.strip()]
    if not cleaned:
        raise Conflict("A dropdown needs at least one option")
    if len(cleaned) > MAX_OPTIONS or len({o.lower() for o in cleaned}) != len(cleaned):
        raise Conflict(f"Options must be unique, at most {MAX_OPTIONS}")
    if any(len(o) > 100 for o in cleaned):
        raise Conflict("Options are limited to 100 characters")
    return cleaned


def _check(field: CustomField, value: Any) -> Any:
    t = field.field_type
    bad = Conflict(f"'{field.name}' has an invalid value")
    if t == "text":
        if not isinstance(value, str) or len(value) > MAX_TEXT:
            raise Conflict(f"'{field.name}' must be text up to {MAX_TEXT} characters")
        return value.strip()
    if t == "number":
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise Conflict(f"'{field.name}' must be a number")
        return value
    if t == "date":
        if not isinstance(value, str) or not _ISO_DATE.match(value):
            raise Conflict(f"'{field.name}' must be a date (YYYY-MM-DD)")
        try:
            date.fromisoformat(value)
        except ValueError:
            raise Conflict(f"'{field.name}' is not a real date") from None
        return value
    if t == "dropdown":
        if value not in (field.options or []):
            raise Conflict(f"'{field.name}' must be one of: {', '.join(field.options or [])}")
        return value
    if t == "checkbox":
        if not isinstance(value, bool):
            raise Conflict(f"'{field.name}' must be true or false")
        return value
    raise bad


def _empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def merge_values(
    ctx: Ctx,
    type_id: int | None,
    existing: dict,
    incoming: dict | None,
    *,
    enforce_required: bool,
) -> dict:
    """Return the new stored dict. `incoming` keys are field ids; a null/blank value clears."""
    fields = {str(f.id): f for f in active_fields(ctx, type_id)}
    merged = dict(existing or {})
    for key, value in (incoming or {}).items():
        field = fields.get(str(key))
        if field is None:
            raise Conflict(f"Unknown field {key} for this ticket type")
        if _empty(value):
            merged.pop(str(key), None)
        else:
            merged[str(key)] = _check(field, value)
    if enforce_required:
        for key, field in fields.items():
            value = merged.get(key)
            missing = _empty(value) or (field.field_type == "checkbox" and value is not True)
            if field.required and missing:
                what = "must be ticked" if field.field_type == "checkbox" else "is required"
                raise Conflict(f"'{field.name}' {what}")
    return merged


def definitions_with_values(ctx: Ctx, type_id: int | None, values: dict) -> list[dict]:
    return [
        dict(
            field_id=f.id,
            name=f.name,
            field_type=f.field_type,
            options=f.options,
            required=f.required,
            client_visible=f.client_visible,
            value=(values or {}).get(str(f.id)),
        )
        for f in active_fields(ctx, type_id)
    ]
