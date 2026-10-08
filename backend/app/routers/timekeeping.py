"""Timers, internal time and the weekly timesheet."""

from datetime import date

from fastapi import APIRouter, Query, Response

from app import permissions as P
from app import timekeeping as svc
from app.deps import Ctx, require
from app.schemas import (
    ErrorOut,
    InternalTimeIn,
    InternalTimeOut,
    InternalTimePatch,
    TimerOut,
    TimerStartIn,
    TimerStopOut,
    TimesheetOut,
)

router = APIRouter(tags=["time"])
ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}


@router.post(
    "/internal-time",
    response_model=InternalTimeOut,
    status_code=201,
    responses=ERR,
    summary="Log internal time (no client): administration, training, paid time off...",
)
def add_internal(body: InternalTimeIn, ctx: Ctx = require(P.TIME_WRITE)):
    return svc.add_internal(ctx, body.model_dump())


@router.patch(
    "/internal-time/{entry_id}",
    response_model=InternalTimeOut,
    responses=ERR,
    summary="Edit an internal time entry",
)
def update_internal(entry_id: int, body: InternalTimePatch, ctx: Ctx = require(P.TIME_WRITE)):
    return svc.update_internal(ctx, entry_id, body.model_dump(exclude_unset=True))


@router.post(
    "/internal-time/{entry_id}/void",
    response_model=InternalTimeOut,
    responses=ERR,
    summary="Void an internal time entry (kept for the audit trail)",
)
def void_internal(entry_id: int, ctx: Ctx = require(P.TIME_WRITE)):
    return svc.void_internal(ctx, entry_id)


@router.get(
    "/timer",
    response_model=TimerOut | None,
    summary="My running timer, if any",
)
def get_timer(ctx: Ctx = require(P.TIME_WRITE)):
    timer = svc.current_timer(ctx)
    return svc.timer_view(ctx, timer) if timer else None


@router.post(
    "/timer/start",
    response_model=TimerOut,
    status_code=201,
    responses=ERR,
    summary="Start a timer on a ticket (with a work type) or on an internal category",
)
def start_timer(body: TimerStartIn, ctx: Ctx = require(P.TIME_WRITE)):
    return svc.timer_view(ctx, svc.start_timer(ctx, body.model_dump()))


@router.post(
    "/timer/stop",
    response_model=TimerStopOut,
    responses=ERR,
    summary="Stop my timer and save the time (rounded up to the minute, then as usual)",
)
def stop_timer(ctx: Ctx = require(P.TIME_WRITE)):
    return svc.stop_timer(ctx)


@router.delete(
    "/timer",
    status_code=204,
    responses=ERR,
    summary="Discard my running timer without saving any time",
)
def discard_timer(ctx: Ctx = require(P.TIME_WRITE)):
    svc.discard_timer(ctx)
    return Response(status_code=204)


@router.get(
    "/timesheet",
    response_model=TimesheetOut,
    responses=ERR,
    summary="One week (Monday to Sunday) of ticket and internal time for a person",
)
def timesheet(
    week_start: date = Query(description="The Monday of the week"),
    user_id: int | None = Query(None, description="Admins only; defaults to you"),
    ctx: Ctx = require(P.TIME_WRITE),
):
    return svc.timesheet(ctx, week_start, user_id)
