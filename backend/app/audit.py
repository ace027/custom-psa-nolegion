"""Audit logging. `record` writes in the caller's transaction, so a change cannot commit
without its audit row (and vice versa)."""

import logging
from datetime import date, datetime
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app import db as dbmod
from app.context import client_ip_var, request_id_var
from app.models import AuditLog, User

auth_logger = logging.getLogger("psa.auth")  # separate logger so it can be shipped to a SIEM

REDACTED_KEYS = {"token_hash", "password", "password_hash", "secret", "token"}


def snapshot(obj: Any) -> dict[str, Any]:
    """JSON-safe column values of an ORM object, with sensitive keys redacted."""
    out: dict[str, Any] = {}
    for col in inspect(obj).mapper.column_attrs:
        value = getattr(obj, col.key)
        if col.key in REDACTED_KEYS:
            value = "[redacted]"
        elif isinstance(value, datetime | date):
            value = value.isoformat()
        out[col.key] = value
    return out


def record(
    db: Session,
    actor: User | None,
    action: str,
    entity: Any = None,
    *,
    before: dict | None = None,
    after: dict | None = None,
    organization_id: int | None = None,
    detail: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_type="user" if actor else "system",
            actor_id=actor.id if actor else None,
            action=action,
            entity_type=type(entity).__tablename__ if entity is not None else None,
            entity_id=getattr(entity, "id", None),
            organization_id=organization_id,
            before=before,
            after=after,
            detail=detail,
            request_id=request_id_var.get(),
            ip=client_ip_var.get(),
        )
    )


def record_auth_event(
    action: str,
    *,
    user_id: int | None = None,
    detail: dict | None = None,
) -> None:
    """Auth events (login, failure, denial...) commit in their OWN transaction so they are kept
    even when the request itself fails or rolls back."""
    auth_logger.info(
        "auth_event action=%s user_id=%s detail=%s request_id=%s ip=%s",
        action,
        user_id,
        detail,
        request_id_var.get(),
        client_ip_var.get(),
    )
    with dbmod.new_session() as s:
        s.add(
            AuditLog(
                actor_type="user" if user_id else "anonymous",
                actor_id=user_id,
                action=action,
                detail=detail,
                request_id=request_id_var.get(),
                ip=client_ip_var.get(),
            )
        )
        s.commit()
