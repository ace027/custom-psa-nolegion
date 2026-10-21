"""API keys: admins create (token shown once), list and revoke. Cookie sessions only."""

from fastapi import APIRouter

from app import api_keys as svc
from app import permissions as P
from app.deps import Ctx, require
from app.models import ApiKey
from app.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyOut, ErrorOut

router = APIRouter(prefix="/api-keys", tags=["api-keys"])
ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}
M = P.APIKEY_MANAGE


def view(k: ApiKey) -> ApiKeyOut:
    return ApiKeyOut(
        id=k.id,
        name=k.name,
        prefix=k.prefix,
        permissions=list(k.permissions),
        owner_id=k.user_id,
        owner_name=k.user.display_name,
        expires_at=k.expires_at,
        revoked_at=k.revoked_at,
        last_used_at=k.last_used_at,
        created_at=k.created_at,
        state=svc.state(k),  # type: ignore[arg-type]
    )


@router.get("", response_model=list[ApiKeyOut], summary="List API keys (never the secret)")
def list_keys(ctx: Ctx = require(M)):
    return [view(k) for k in svc.list_keys(ctx)]


@router.post(
    "",
    response_model=ApiKeyCreated,
    status_code=201,
    responses=ERR,
    summary="Create an API key; the token is returned only in this response",
)
def create(body: ApiKeyCreate, ctx: Ctx = require(M)):
    key, token = svc.create(ctx, body.name, body.permissions, body.expires_in_days)
    return ApiKeyCreated(key=view(key), token=token)


@router.post(
    "/{key_id}/revoke", response_model=ApiKeyOut, responses=ERR, summary="Revoke an API key"
)
def revoke(key_id: int, ctx: Ctx = require(M)):
    return view(svc.revoke(ctx, key_id))
