from fastapi import APIRouter, Query

from app import permissions as P
from app import repositories as repo
from app import services
from app.deps import Ctx, require
from app.schemas import AuditOut, ErrorOut, Page, UserIn, UserOut, UserPatch

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


@router.get("/audit", response_model=Page[AuditOut], summary="Query the audit log (admin only)")
def list_audit(
    entity_type: str | None = None,
    entity_id: int | None = None,
    organization_id: int | None = None,
    actor_id: int | None = None,
    action: str | None = Query(None, description="Action prefix, e.g. 'auth.' or 'contact.'"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: Ctx = require(P.AUDIT_READ),
):
    items, total = repo.list_audit(
        ctx.db,
        entity_type=entity_type,
        entity_id=entity_id,
        organization_id=organization_id,
        actor_id=actor_id,
        action=action,
        limit=limit,
        offset=offset,
    )
    return Page(items=items, total=total, limit=limit, offset=offset)
