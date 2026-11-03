from datetime import date

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app import audit, audit_text, services
from app import permissions as P
from app import repositories as repo
from app.deps import Ctx, require
from app.errors import NotFound
from app.models import AuditLog, Organization, User
from app.report_metrics import _bounds, _zone
from app.report_schemas import CostRateIn, CostRateOut
from app.schemas import (
    AuditChangeOut,
    AuditEntityTypeOut,
    AuditOut,
    ErrorOut,
    Page,
    UserIn,
    UserOut,
    UserPatch,
)

router = APIRouter(tags=["users"])
ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}


@router.get("/users", response_model=list[UserOut], summary="List staff users")
def list_users(ctx: Ctx = require(P.USER_READ)):
    return repo.list_users(ctx.db)


@router.post(
    "/users",
    response_model=UserOut,
    status_code=201,
    responses=ERR,
    summary="Pre-provision a staff user (admin only)",
)
def create_user(body: UserIn, ctx: Ctx = require(P.USER_MANAGE)):
    return services.create_user(ctx, body.model_dump())


@router.patch(
    "/users/{user_id}",
    response_model=UserOut,
    responses={**ERR, 403: {"model": ErrorOut}},
    summary="Change a user's role, name or active flag (admin only)",
)
def update_user(user_id: int, body: UserPatch, ctx: Ctx = require(P.USER_MANAGE)):
    return services.update_user(ctx, user_id, body.model_dump(exclude_unset=True))


@router.get(
    "/users/{user_id}/cost-rate",
    response_model=CostRateOut,
    responses=ERR,
    summary="A person's hourly internal cost rate in cents (admin only)",
)
def get_cost_rate(user_id: int, ctx: Ctx = require(P.USER_MANAGE)):
    user = repo.get_user(ctx.db, user_id)
    if user is None:
        raise NotFound("User not found")
    return CostRateOut(user_id=user.id, cost_rate_cents=user.cost_rate_cents)


@router.put(
    "/users/{user_id}/cost-rate",
    response_model=CostRateOut,
    responses=ERR,
    summary="Set or clear a person's hourly internal cost rate in cents (admin only)",
)
def put_cost_rate(user_id: int, body: CostRateIn, ctx: Ctx = require(P.USER_MANAGE)):
    user = repo.get_user(ctx.db, user_id)
    if user is None:
        raise NotFound("User not found")
    before = user.cost_rate_cents
    if before != body.cost_rate_cents:
        user.cost_rate_cents = body.cost_rate_cents
        ctx.db.flush()
        audit.record(
            ctx.db,
            ctx.user,
            "user.cost_rate",
            user,
            detail={"from": before, "to": body.cost_rate_cents},
        )
    return CostRateOut(user_id=user.id, cost_rate_cents=user.cost_rate_cents)


@router.get("/audit", response_model=Page[AuditOut], summary="Query the audit log (admin only)")
def list_audit(
    entity_type: str | None = None,
    entity_id: int | None = None,
    organization_id: int | None = None,
    actor_id: int | None = None,
    action: str | None = Query(None, description="Action prefix, e.g. 'auth.' or 'contact.'"),
    date_from: date | None = Query(None, description="First local date, inclusive"),
    date_to: date | None = Query(None, description="Last local date, inclusive"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: Ctx = require(P.AUDIT_READ),
):
    if date_from and date_to and date_to < date_from:
        raise HTTPException(422, "date_to is before date_from")
    tz = _zone(None, repo.get_settings_row(ctx.db).timezone)
    lo = _bounds(date_from, date_from, tz)[0] if date_from else None
    hi = _bounds(date_to, date_to, tz)[1] if date_to else None
    items, total = repo.list_audit(
        ctx.db,
        occurred_from=lo,
        occurred_before=hi,
        entity_type=entity_type,
        entity_id=entity_id,
        organization_id=organization_id,
        actor_id=actor_id,
        action=action,
        limit=limit,
        offset=offset,
    )
    actors = _names(ctx.db, User.id, User.display_name, {i.actor_id for i in items})
    orgs = _names(ctx.db, Organization.id, Organization.name, {i.organization_id for i in items})
    out = []
    for i in items:
        row = AuditOut.model_validate(i)
        row.actor_name = actors.get(i.actor_id) if i.actor_type == "user" else None
        row.organization_name = orgs.get(i.organization_id)
        row.summary = audit_text.summary(i, row.actor_name, row.organization_name)
        row.changes = [AuditChangeOut(**c) for c in audit_text.changes(i.before, i.after)]
        out.append(row)
    return Page(items=out, total=total, limit=limit, offset=offset)


def _names(db, id_col, name_col, ids) -> dict[int, str]:
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    return dict(db.execute(select(id_col, name_col).where(id_col.in_(ids))).all())


@router.get(
    "/audit/entity-types",
    response_model=list[AuditEntityTypeOut],
    summary="Record types that appear in the audit log (admin only)",
)
def audit_entity_types(ctx: Ctx = require(P.AUDIT_READ)):
    types = ctx.db.execute(
        select(AuditLog.entity_type).where(AuditLog.entity_type.is_not(None)).distinct()
    ).scalars()
    rows = [{"value": t, "label": audit_text.record_label(t)} for t in types]
    return sorted(rows, key=lambda r: r["label"])
