"""Links between tickets and close-as-duplicate."""

from fastapi import APIRouter, Response

from app import permissions as P
from app import ticket_links as svc
from app.deps import Ctx, require
from app.routers.tickets import _view
from app.schemas import CloseDuplicateIn, ErrorOut, TicketLinkIn, TicketLinkOut, TicketOut

router = APIRouter(tags=["tickets"])
ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}


@router.get(
    "/tickets/{ticket_id}/links",
    response_model=list[TicketLinkOut],
    responses=ERR,
    summary="Tickets linked to this one (related, duplicates, parent, children)",
)
def list_links(ticket_id: int, ctx: Ctx = require(P.TICKET_READ)):
    return svc.list_links(ctx, ticket_id)


@router.post(
    "/tickets/{ticket_id}/links",
    response_model=list[TicketLinkOut],
    status_code=201,
    responses=ERR,
    summary="Link another ticket of the same client by its number",
)
def add_link(ticket_id: int, body: TicketLinkIn, ctx: Ctx = require(P.TICKET_WRITE)):
    svc.add_link(ctx, ticket_id, body.relation, body.other_number)
    return svc.list_links(ctx, ticket_id)


@router.delete(
    "/tickets/{ticket_id}/links/{link_id}",
    status_code=204,
    responses=ERR,
    summary="Remove a link (the tickets themselves are untouched)",
)
def remove_link(ticket_id: int, link_id: int, ctx: Ctx = require(P.TICKET_WRITE)):
    svc.remove_link(ctx, ticket_id, link_id)
    return Response(status_code=204)


@router.post(
    "/tickets/{ticket_id}/close-as-duplicate",
    response_model=TicketOut,
    responses=ERR,
    summary="Link to the original, leave pointer notes and close; notes and time stay put",
)
def close_as_duplicate(ticket_id: int, body: CloseDuplicateIn, ctx: Ctx = require(P.TICKET_WRITE)):
    ticket = svc.close_as_duplicate(ctx, ticket_id, body.original_number)
    return _view(ctx)(ticket)
