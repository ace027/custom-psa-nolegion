"""Ticket statuses (and, in later parts, ticket types and custom fields)."""

from fastapi import APIRouter

from app import config_services as svc
from app import permissions as P
from app import repositories as repo
from app.deps import Ctx, require
from app.schemas import ErrorOut, TicketStatusIn, TicketStatusOut, TicketStatusPatch

router = APIRouter(tags=["configuration"])
ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}


@router.get(
    "/ticket-statuses",
    response_model=list[TicketStatusOut],
    summary="List ticket statuses in display order",
)
def list_statuses(include_archived: bool = False, ctx: Ctx = require(P.TICKET_READ)):
    return repo.list_ticket_statuses(ctx.db, include_archived)


@router.post(
    "/ticket-statuses",
    response_model=TicketStatusOut,
    status_code=201,
    responses=ERR,
    summary="Add a status that behaves like one of the five built-in states",
)
def create_status(body: TicketStatusIn, ctx: Ctx = require(P.CONFIG_MANAGE)):
    return svc.create_ticket_status(ctx, body.model_dump())


@router.patch(
    "/ticket-statuses/{status_id}",
    response_model=TicketStatusOut,
    responses=ERR,
    summary="Rename or reorder a status (its behaviour cannot change)",
)
def update_status(status_id: int, body: TicketStatusPatch, ctx: Ctx = require(P.CONFIG_MANAGE)):
    return svc.update_ticket_status(ctx, status_id, body.model_dump(exclude_unset=True))


@router.post(
    "/ticket-statuses/{status_id}/archive",
    response_model=TicketStatusOut,
    responses=ERR,
    summary="Hide a status from new choices (tickets that have it keep it)",
)
def archive_status(status_id: int, ctx: Ctx = require(P.CONFIG_MANAGE)):
    return svc.set_ticket_status_archived(ctx, status_id, True)


@router.post(
    "/ticket-statuses/{status_id}/unarchive",
    response_model=TicketStatusOut,
    responses=ERR,
    summary="Bring an archived status back",
)
def unarchive_status(status_id: int, ctx: Ctx = require(P.CONFIG_MANAGE)):
    return svc.set_ticket_status_archived(ctx, status_id, False)
