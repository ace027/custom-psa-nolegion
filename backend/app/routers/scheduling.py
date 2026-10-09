"""Working hours, time off, appointments and availability."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app import permissions as P
from app import scheduling as svc
from app.deps import Ctx, require
from app.scheduling_schemas import (
    AppointmentCancel,
    AppointmentIn,
    AppointmentOut,
    AppointmentPatch,
    AvailabilityOut,
    ScheduleOut,
    SchedulePut,
    TimeOffDecision,
    TimeOffIn,
    TimeOffOut,
    TimeOffStatus,
)
from app.schemas import ErrorOut

router = APIRouter(tags=["scheduling"])
ERR = {code: {"model": ErrorOut} for code in (403, 404, 409, 422)}


def _invalid(exc: svc.InvalidSchedule) -> HTTPException:
    return HTTPException(422, str(exc))


# ---- schedule ----
@router.get(
    "/users/{user_id}/schedule",
    response_model=ScheduleOut,
    responses=ERR,
    summary="A user's timezone and weekly working hours (yourself, or anyone for admins)",
)
def get_schedule(user_id: int, ctx: Ctx = require(P.SCHEDULE_READ)):
    return svc.get_schedule(ctx, user_id)


@router.put(
    "/users/{user_id}/schedule",
    response_model=ScheduleOut,
    responses=ERR,
    summary="Set a user's timezone and weekly working hours (null = the org defaults)",
)
def put_schedule(user_id: int, body: SchedulePut, ctx: Ctx = require(P.SCHEDULE_WRITE)):
    try:
        return svc.put_schedule(ctx, user_id, body.model_dump())
    except svc.InvalidSchedule as exc:
        raise _invalid(exc) from exc


# ---- time off ----
@router.get(
    "/time-off",
    response_model=list[TimeOffOut],
    responses=ERR,
    summary="Time off overlapping a range, by start (reasons only for the owner and admins)",
)
def list_time_off(
    user_id: int | None = None,
    status: TimeOffStatus | None = None,
    start: datetime | None = Query(None, alias="from"),
    end: datetime | None = Query(None, alias="to"),
    ctx: Ctx = require(P.SCHEDULE_READ),
):
    try:
        rows = svc.list_time_off(ctx, user_id=user_id, status=status, start=start, end=end)
    except svc.InvalidSchedule as exc:
        raise _invalid(exc) from exc
    return [svc.time_off_view(ctx, t) for t in rows]


@router.post(
    "/time-off",
    response_model=TimeOffOut,
    status_code=201,
    responses=ERR,
    summary="Request time off (pending until an admin approves; an admin's entry is approved)",
)
def create_time_off(body: TimeOffIn, ctx: Ctx = require(P.SCHEDULE_WRITE)):
    try:
        return svc.time_off_view(ctx, svc.create_time_off(ctx, body.model_dump()))
    except svc.InvalidSchedule as exc:
        raise _invalid(exc) from exc


@router.post(
    "/time-off/{time_off_id}/approve",
    response_model=TimeOffOut,
    responses=ERR,
    summary="Approve a pending time-off request",
)
def approve_time_off(
    time_off_id: int, body: TimeOffDecision, ctx: Ctx = require(P.TIMEOFF_APPROVE)
):
    return svc.time_off_view(ctx, svc.decide_time_off(ctx, time_off_id, True, body.note))


@router.post(
    "/time-off/{time_off_id}/reject",
    response_model=TimeOffOut,
    responses=ERR,
    summary="Reject a pending time-off request",
)
def reject_time_off(time_off_id: int, body: TimeOffDecision, ctx: Ctx = require(P.TIMEOFF_APPROVE)):
    return svc.time_off_view(ctx, svc.decide_time_off(ctx, time_off_id, False, body.note))


@router.post(
    "/time-off/{time_off_id}/cancel",
    response_model=TimeOffOut,
    responses=ERR,
    summary="Cancel time off: pending, or approved and not yet over (owner or admin)",
)
def cancel_time_off(time_off_id: int, ctx: Ctx = require(P.SCHEDULE_WRITE)):
    return svc.time_off_view(ctx, svc.cancel_time_off(ctx, time_off_id))


# ---- appointments ----
@router.get(
    "/appointments",
    response_model=list[AppointmentOut],
    responses=ERR,
    summary="Appointments overlapping from/to (required unless ticket_id is given)",
)
def list_appointments(
    tech_id: int | None = None,
    ticket_id: int | None = None,
    start: datetime | None = Query(None, alias="from"),
    end: datetime | None = Query(None, alias="to"),
    include_cancelled: bool = False,
    ctx: Ctx = require(P.SCHEDULE_READ),
):
    try:
        rows = svc.list_appointments(
            ctx,
            tech_id=tech_id,
            ticket_id=ticket_id,
            start=start,
            end=end,
            include_cancelled=include_cancelled,
        )
    except svc.InvalidSchedule as exc:
        raise _invalid(exc) from exc
    return [svc.appointment_view(ctx, a) for a in rows]


@router.post(
    "/appointments",
    response_model=AppointmentOut,
    status_code=201,
    responses=ERR,
    summary="Book a tech on a ticket; conflicts are returned as warnings, never blocking",
)
def create_appointment(body: AppointmentIn, ctx: Ctx = require(P.SCHEDULE_WRITE)):
    try:
        a = svc.create_appointment(ctx, body.model_dump())
    except svc.InvalidSchedule as exc:
        raise _invalid(exc) from exc
    return svc.appointment_view(ctx, a, with_conflicts=True)


@router.get(
    "/appointments/{appointment_id}",
    response_model=AppointmentOut,
    responses=ERR,
    summary="One appointment, with its current conflicts",
)
def get_appointment(appointment_id: int, ctx: Ctx = require(P.SCHEDULE_READ)):
    return svc.appointment_view(ctx, svc.get_appointment(ctx, appointment_id), with_conflicts=True)


@router.patch(
    "/appointments/{appointment_id}",
    response_model=AppointmentOut,
    responses=ERR,
    summary="Move, reassign or annotate a scheduled appointment (conflicts recomputed)",
)
def update_appointment(
    appointment_id: int, body: AppointmentPatch, ctx: Ctx = require(P.SCHEDULE_WRITE)
):
    try:
        a = svc.update_appointment(ctx, appointment_id, body.model_dump(exclude_unset=True))
    except svc.InvalidSchedule as exc:
        raise _invalid(exc) from exc
    return svc.appointment_view(ctx, a, with_conflicts=True)


@router.post(
    "/appointments/{appointment_id}/cancel",
    response_model=AppointmentOut,
    responses=ERR,
    summary="Cancel a scheduled appointment (kept for the record)",
)
def cancel_appointment(
    appointment_id: int, body: AppointmentCancel, ctx: Ctx = require(P.SCHEDULE_WRITE)
):
    return svc.appointment_view(ctx, svc.cancel_appointment(ctx, appointment_id, body.reason))


# ---- availability ----
@router.get(
    "/availability",
    response_model=list[AvailabilityOut],
    responses=ERR,
    summary="Working hours, approved time off, appointments and free windows per tech "
    "(user_ids is comma-separated; omit for every active admin and tech)",
)
def get_availability(
    start: datetime = Query(alias="from"),
    end: datetime = Query(alias="to"),
    user_ids: str | None = Query(None, max_length=2000),
    ctx: Ctx = require(P.SCHEDULE_READ),
):
    try:
        ids = [int(x) for x in user_ids.split(",") if x.strip()] if user_ids else None
    except ValueError as exc:
        raise HTTPException(422, "user_ids must be comma-separated numbers") from exc
    try:
        return svc.availability_for(ctx, ids, start, end)
    except svc.InvalidSchedule as exc:
        raise _invalid(exc) from exc
