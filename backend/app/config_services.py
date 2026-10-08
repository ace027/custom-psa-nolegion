"""Editable configuration: queues, categories, priorities, work types, and global settings."""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import update

from app import audit
from app import repositories as repo
from app.deps import Ctx
from app.errors import Conflict, NotFound
from app.models import Priority, Queue
from app.sla import Calendar

HAS_DEFAULT = (Queue, Priority)


def _unset_other_defaults(ctx: Ctx, model, keep_id: int | None) -> None:
    stmt = update(model).where(model.is_default.is_(True))
    if keep_id is not None:
        stmt = stmt.where(model.id != keep_id)
    ctx.db.execute(stmt.values(is_default=False))


def _flush(ctx: Ctx, label: str) -> None:
    from sqlalchemy.exc import IntegrityError

    try:
        ctx.db.flush()
    except IntegrityError as exc:
        ctx.db.rollback()
        raise Conflict(f"An active {label} with that name already exists") from exc


def create_lookup(ctx: Ctx, model, label: str, data: dict):
    if model in HAS_DEFAULT and data.get("is_default"):
        _unset_other_defaults(ctx, model, None)
    obj = model(**data)
    ctx.db.add(obj)
    _flush(ctx, label)
    audit.record(ctx.db, ctx.user, f"{label}.create", obj, after=audit.snapshot(obj))
    return obj


def update_lookup(ctx: Ctx, model, label: str, obj_id: int, data: dict):
    obj = repo.get_lookup(ctx.db, model, obj_id)
    if obj is None:
        raise NotFound(f"{label} not found")
    before = audit.snapshot(obj)
    if model in HAS_DEFAULT and "is_default" in data:
        if data["is_default"]:
            _unset_other_defaults(ctx, model, obj.id)
        elif obj.is_default:
            raise Conflict(f"Choose another {label} as the default instead")
    for key, value in data.items():
        if key in ("name", "body") and value is None:
            continue
        setattr(obj, key, value)
    _flush(ctx, label)
    ctx.db.refresh(obj)
    audit.record(ctx.db, ctx.user, f"{label}.update", obj, before=before, after=audit.snapshot(obj))
    return obj


def set_lookup_archived(ctx: Ctx, model, label: str, obj_id: int, archived: bool):
    from datetime import UTC, datetime

    obj = repo.get_lookup(ctx.db, model, obj_id)
    if obj is None:
        raise NotFound(f"{label} not found")
    if archived and getattr(obj, "is_default", False):
        raise Conflict(f"The default {label} cannot be archived; choose another default first")
    before = audit.snapshot(obj)
    obj.archived_at = datetime.now(UTC) if archived else None
    _flush(ctx, label)
    ctx.db.refresh(obj)
    audit.record(
        ctx.db,
        ctx.user,
        f"{label}.{'archive' if archived else 'unarchive'}",
        obj,
        before=before,
        after=audit.snapshot(obj),
    )
    return obj


def update_settings(ctx: Ctx, data: dict):
    from app.notices import INVOICE_PLACEHOLDERS, validate_template

    for key in ("statement_subject", "statement_body"):
        if data.get(key) is not None:
            validate_template(data[key])
    for key in ("invoice_email_subject", "invoice_email_body"):
        if data.get(key) is not None:
            validate_template(data[key], INVOICE_PLACEHOLDERS)
    from app.autoreply import ACK_PLACEHOLDERS

    for key in ("auto_ack_subject", "auto_ack_body"):
        if data.get(key) is not None:
            validate_template(data[key], ACK_PLACEHOLDERS)
    row = repo.get_settings_row(ctx.db)
    before = audit.snapshot(row)
    for key, value in data.items():
        if value is not None:
            setattr(row, key, value)
    if data.get("escalation_email") == "":
        row.escalation_email = None
    try:
        ZoneInfo(row.timezone)
        Calendar.from_settings(row).validate()  # no query here: it would autoflush a bad row
    except (ZoneInfoNotFoundError, ValueError, KeyError) as exc:
        ctx.db.rollback()
        raise Conflict(f"Invalid settings: {exc}") from exc
    row.business_days = sorted(set(row.business_days))
    ctx.db.flush()
    ctx.db.refresh(row)
    audit.record(ctx.db, ctx.user, "settings.update", row, before=before, after=audit.snapshot(row))
    return row


# ---- holidays ----
def _holiday_flush(ctx: Ctx) -> None:
    from sqlalchemy.exc import IntegrityError

    try:
        ctx.db.flush()
    except IntegrityError as exc:
        ctx.db.rollback()
        raise Conflict("That date already has a holiday entry") from exc


def create_holiday(ctx: Ctx, data: dict):
    from app.models import Holiday

    obj = Holiday(**data)
    ctx.db.add(obj)
    _holiday_flush(ctx)
    audit.record(ctx.db, ctx.user, "holiday.create", obj, after=audit.snapshot(obj))
    return obj


def update_holiday(ctx: Ctx, holiday_id: int, data: dict):
    from app.models import Holiday

    obj = ctx.db.get(Holiday, holiday_id)
    if obj is None:
        raise NotFound("Holiday not found")
    before = audit.snapshot(obj)
    for key, value in data.items():
        setattr(obj, key, value)
    _holiday_flush(ctx)
    ctx.db.refresh(obj)
    audit.record(ctx.db, ctx.user, "holiday.update", obj, before=before, after=audit.snapshot(obj))
    return obj


def delete_holiday(ctx: Ctx, holiday_id: int) -> None:
    from app.models import Holiday

    obj = ctx.db.get(Holiday, holiday_id)
    if obj is None:
        raise NotFound("Holiday not found")
    audit.record(ctx.db, ctx.user, "holiday.delete", obj, before=audit.snapshot(obj))
    ctx.db.delete(obj)
    ctx.db.flush()
