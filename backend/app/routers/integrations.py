"""Vendor integrations (NinjaOne, Hudu): connect, test, sync, map clients. Admin only."""

from fastapi import APIRouter

from app import integration_services as svc
from app import permissions as P
from app.asset_schemas import (
    ClientMapIn,
    ClientMapOut,
    IntegrationIn,
    IntegrationOut,
    IntegrationPatch,
    SyncRunOut,
    TestOut,
)
from app.deps import Ctx, require
from app.schemas import ErrorOut

router = APIRouter(prefix="/integrations", tags=["integrations"])
ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}
M = P.INTEGRATION_MANAGE


@router.get("", response_model=list[IntegrationOut], summary="List connected vendors")
def list_integrations(ctx: Ctx = require(M)):
    return svc.list_integrations(ctx)


@router.post(
    "",
    response_model=IntegrationOut,
    status_code=201,
    responses=ERR,
    summary="Connect a vendor (credentials are stored encrypted and never returned)",
)
def create(body: IntegrationIn, ctx: Ctx = require(M)):
    return svc.create(ctx, body.model_dump())


@router.patch(
    "/{integration_id}",
    response_model=IntegrationOut,
    responses=ERR,
    summary="Edit a vendor connection or replace its credentials",
)
def update(integration_id: int, body: IntegrationPatch, ctx: Ctx = require(M)):
    return svc.update(ctx, integration_id, body.model_dump(exclude_unset=True))


@router.post(
    "/{integration_id}/test",
    response_model=TestOut,
    responses=ERR,
    summary="Test the connection (read-only call to the vendor)",
)
def test(integration_id: int, ctx: Ctx = require(M)):
    return svc.test(ctx, integration_id)


@router.post(
    "/{integration_id}/sync",
    response_model=IntegrationOut,
    responses=ERR,
    summary="Ask the worker to sync now",
)
def sync_now(integration_id: int, ctx: Ctx = require(M)):
    return svc.request_sync(ctx, integration_id)


@router.get(
    "/{integration_id}/runs",
    response_model=list[SyncRunOut],
    responses=ERR,
    summary="Recent sync runs",
)
def runs(integration_id: int, ctx: Ctx = require(M)):
    return svc.runs(ctx, integration_id)


@router.get(
    "/{integration_id}/clients",
    response_model=list[ClientMapOut],
    responses=ERR,
    summary="Vendor clients and how they map to PSA clients",
)
def clients(integration_id: int, ctx: Ctx = require(M)):
    return svc.clients(ctx, integration_id)


@router.post(
    "/{integration_id}/clients/refresh",
    response_model=list[ClientMapOut],
    responses=ERR,
    summary="Fetch the vendor's client list now",
)
def refresh_clients(integration_id: int, ctx: Ctx = require(M)):
    return svc.refresh_clients(ctx, integration_id)


@router.put(
    "/{integration_id}/clients/{map_id}",
    response_model=ClientMapOut,
    responses=ERR,
    summary="Map a vendor client to a PSA client, or ignore it",
)
def map_client(integration_id: int, map_id: int, body: ClientMapIn, ctx: Ctx = require(M)):
    return svc.map_client(ctx, integration_id, map_id, body.organization_id, body.ignored)
