"""Holiday calendar used by SLA clocks. New and resumed clocks use it; due dates already on
tickets are not rewritten until something recomputes them (priority change, resume)."""

from fastapi import APIRouter, Query
from sqlalchemy import select

from app import config_services as svc
from app import permissions as P
from app.deps import Ctx, require
from app.models import Holiday
from app.schemas import ErrorOut, HolidayIn, HolidayOut

router = APIRouter(tags=["configuration"])
ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}


@router.get("/holidays", response_model=list[HolidayOut], summary="List holidays, soonest first")
def list_holidays(
    year: int | None = Query(default=None, ge=2000, le=2100), ctx: Ctx = require(P.TICKET_READ)
):
    stmt = select(Holiday).order_by(Holiday.on_date)
    if year is not None:
        from datetime import date

        stmt = stmt.where(
            Holiday.on_date >= date(year, 1, 1), Holiday.on_date <= date(year, 12, 31)
        )
    return list(ctx.db.execute(stmt).scalars())


@router.post(
    "/holidays",
    response_model=HolidayOut,
    status_code=201,
    responses=ERR,
    summary="Add a closed day or a shortened day",
)
def create_holiday(body: HolidayIn, ctx: Ctx = require(P.CONFIG_MANAGE)):
    return svc.create_holiday(ctx, body.model_dump())


@router.put(
    "/holidays/{holiday_id}",
    response_model=HolidayOut,
    responses=ERR,
    summary="Change a holiday",
)
def update_holiday(holiday_id: int, body: HolidayIn, ctx: Ctx = require(P.CONFIG_MANAGE)):
    return svc.update_holiday(ctx, holiday_id, body.model_dump())


@router.delete(
    "/holidays/{holiday_id}",
    status_code=204,
    responses=ERR,
    summary="Remove a holiday (calendar data only; audited)",
)
def delete_holiday(holiday_id: int, ctx: Ctx = require(P.CONFIG_MANAGE)):
    svc.delete_holiday(ctx, holiday_id)
