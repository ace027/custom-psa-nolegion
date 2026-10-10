"""Ticket statuses, and the custom fields that hang off ticket types."""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app import config_services as svc
from app import custom_fields
from app import permissions as P
from app import repositories as repo
from app.deps import Ctx, require
from app.models import CustomField, TicketType
from app.schemas import (
    CustomFieldIn,
    CustomFieldOut,
    CustomFieldPatch,
    ErrorOut,
    TicketFieldOut,
    TicketStatusIn,
    TicketStatusOut,
    TicketStatusPatch,
)

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


@router.get(
    "/ticket-types/{type_id}/fields",
    response_model=list[CustomFieldOut],
    responses=ERR,
    summary="List the custom fields of a ticket type in display order",
)
def list_fields(type_id: int, include_archived: bool = False, ctx: Ctx = require(P.TICKET_READ)):
    if ctx.db.get(TicketType, type_id) is None:
        raise HTTPException(404, "Ticket type not found")
    stmt = (
        select(CustomField)
        .where(CustomField.ticket_type_id == type_id)
        .order_by(CustomField.position, CustomField.id)
    )
    if not include_archived:
        stmt = stmt.where(CustomField.archived_at.is_(None))
    return list(ctx.db.execute(stmt).scalars())


@router.post(
    "/ticket-types/{type_id}/fields",
    response_model=CustomFieldOut,
    status_code=201,
    responses=ERR,
    summary="Add a custom field to a ticket type",
)
def create_field(type_id: int, body: CustomFieldIn, ctx: Ctx = require(P.CONFIG_MANAGE)):
    return svc.create_custom_field(ctx, type_id, body.model_dump())


@router.patch(
    "/custom-fields/{field_id}",
    response_model=CustomFieldOut,
    responses=ERR,
    summary="Rename, reorder or change options/required/visibility (type cannot change)",
)
def update_field(field_id: int, body: CustomFieldPatch, ctx: Ctx = require(P.CONFIG_MANAGE)):
    return svc.update_custom_field(ctx, field_id, body.model_dump(exclude_unset=True))


@router.post(
    "/custom-fields/{field_id}/archive",
    response_model=CustomFieldOut,
    responses=ERR,
    summary="Hide a custom field (tickets keep their stored values)",
)
def archive_field(field_id: int, ctx: Ctx = require(P.CONFIG_MANAGE)):
    return svc.set_custom_field_archived(ctx, field_id, True)


@router.post(
    "/custom-fields/{field_id}/unarchive",
    response_model=CustomFieldOut,
    responses=ERR,
    summary="Bring an archived custom field back",
)
def unarchive_field(field_id: int, ctx: Ctx = require(P.CONFIG_MANAGE)):
    return svc.set_custom_field_archived(ctx, field_id, False)


@router.get(
    "/tickets/{ticket_id}/custom-fields",
    response_model=list[TicketFieldOut],
    responses=ERR,
    summary="The custom fields of this ticket's type, with the ticket's values",
)
def ticket_fields(ticket_id: int, ctx: Ctx = require(P.TICKET_READ)):
    ticket = repo.get_ticket(ctx.db, ctx.scope, ticket_id)
    if ticket is None:
        raise HTTPException(404, "Ticket not found")
    return custom_fields.definitions_with_values(ctx, ticket.type_id, ticket.custom_values)
