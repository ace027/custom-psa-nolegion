"""On-call rotations, overrides and who is on call now (REQ-05)."""

from datetime import datetime

from fastapi import APIRouter, HTTPException

from app import oncall_service as svc
from app import permissions as P
from app.deps import Ctx, require
from app.oncall_schemas import (
    OnCallNowOut,
    OverrideCreate,
    OverrideOut,
    RotationCreate,
    RotationOut,
    RotationPatch,
    ShiftOut,
)
from app.schemas import ErrorOut

router = APIRouter(prefix="/oncall", tags=["oncall"])
ERR = {code: {"model": ErrorOut} for code in (403, 404, 422)}


def _invalid(exc: svc.InvalidOncall) -> HTTPException:
    return HTTPException(422, str(exc))


@router.get(
    "/rotations", response_model=list[RotationOut], responses=ERR, summary="On-call rotations"
)
def list_rotations(ctx: Ctx = require(P.SCHEDULE_READ)):
    return svc.list_rotations(ctx)


@router.post(
    "/rotations",
    response_model=RotationOut,
    status_code=201,
    responses=ERR,
    summary="Create a weekly on-call rotation with its ordered members",
)
def create_rotation(body: RotationCreate, ctx: Ctx = require(P.SCHEDULE_WRITE)):
    try:
        return svc.create_rotation(ctx, body.model_dump())
    except svc.InvalidOncall as exc:
        raise _invalid(exc) from exc


@router.patch(
    "/rotations/{rotation_id}",
    response_model=RotationOut,
    responses=ERR,
    summary="Edit a rotation; member_ids replaces the ordered member list",
)
def update_rotation(rotation_id: int, body: RotationPatch, ctx: Ctx = require(P.SCHEDULE_WRITE)):
    try:
        return svc.update_rotation(ctx, rotation_id, body.model_dump(exclude_unset=True))
    except svc.InvalidOncall as exc:
        raise _invalid(exc) from exc


@router.get(
    "/rotations/{rotation_id}/overrides",
    response_model=list[OverrideOut],
    responses=ERR,
    summary="Overrides of a rotation, by start",
)
def list_overrides(rotation_id: int, ctx: Ctx = require(P.SCHEDULE_READ)):
    return svc.list_overrides(ctx, rotation_id)


@router.post(
    "/rotations/{rotation_id}/overrides",
    response_model=OverrideOut,
    status_code=201,
    responses=ERR,
    summary="Cover a period with someone else; wins over the rotation",
)
def create_override(rotation_id: int, body: OverrideCreate, ctx: Ctx = require(P.SCHEDULE_WRITE)):
    try:
        return svc.create_override(ctx, rotation_id, body.model_dump())
    except svc.InvalidOncall as exc:
        raise _invalid(exc) from exc


@router.delete(
    "/overrides/{override_id}",
    status_code=204,
    responses=ERR,
    summary="Remove an on-call override",
)
def delete_override(override_id: int, ctx: Ctx = require(P.SCHEDULE_WRITE)):
    svc.delete_override(ctx, override_id)


@router.get(
    "/now",
    response_model=list[OnCallNowOut],
    responses=ERR,
    summary="Who is on call right now, per active rotation",
)
def on_call_now(ctx: Ctx = require(P.SCHEDULE_READ)):
    return svc.now(ctx)


@router.get(
    "/schedule",
    response_model=list[ShiftOut],
    responses=ERR,
    summary="On-call shifts between start and end (at most 31 days)",
)
def schedule(start: datetime, end: datetime, ctx: Ctx = require(P.SCHEDULE_READ)):
    try:
        return svc.schedule(ctx, start, end)
    except svc.InvalidOncall as exc:
        raise _invalid(exc) from exc
