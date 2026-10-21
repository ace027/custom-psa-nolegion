"""Outbound webhooks: admins register endpoints, see deliveries and retry failures.
The URL and the signing secret are write-only (the secret is shown once)."""

from typing import Literal

from fastapi import APIRouter, Query

from app import permissions as P
from app import webhooks as svc
from app.deps import Ctx, require
from app.schemas import (
    ErrorOut,
    WebhookCreate,
    WebhookCreated,
    WebhookDeliveryOut,
    WebhookOut,
    WebhookPatch,
    WebhookTestOut,
)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}
M = P.AUTOMATION_MANAGE


@router.get("", response_model=list[WebhookOut], summary="List webhooks (never the URL or secret)")
def list_webhooks(ctx: Ctx = require(M)):
    return [svc.view(e) for e in svc.list_endpoints(ctx)]


@router.post(
    "",
    response_model=WebhookCreated,
    status_code=201,
    responses=ERR,
    summary="Add a webhook; the signing secret is returned only in this response",
)
def create(body: WebhookCreate, ctx: Ctx = require(M)):
    ep, secret = svc.create(ctx, body.model_dump())
    return WebhookCreated(endpoint=svc.view(ep), secret=secret)


@router.patch(
    "/{webhook_id}",
    response_model=WebhookOut,
    responses=ERR,
    summary="Edit a webhook (name, URL, events, enabled)",
)
def update(webhook_id: int, body: WebhookPatch, ctx: Ctx = require(M)):
    return svc.view(svc.update(ctx, webhook_id, body.model_dump(exclude_unset=True)))


@router.post(
    "/{webhook_id}/rotate-secret",
    response_model=WebhookCreated,
    responses=ERR,
    summary="Replace the signing secret; the new one is returned only in this response",
)
def rotate(webhook_id: int, ctx: Ctx = require(M)):
    ep, secret = svc.rotate_secret(ctx, webhook_id)
    return WebhookCreated(endpoint=svc.view(ep), secret=secret)


@router.post(
    "/{webhook_id}/test",
    response_model=WebhookTestOut,
    status_code=202,
    responses=ERR,
    summary="Queue a test ping to this webhook",
)
def test(webhook_id: int, ctx: Ctx = require(M)):
    return WebhookTestOut(queued=svc.test(ctx, webhook_id))


@router.get(
    "/{webhook_id}/deliveries",
    response_model=list[WebhookDeliveryOut],
    responses=ERR,
    summary="Delivery log for a webhook, newest first",
)
def deliveries(
    webhook_id: int,
    status: Literal["pending", "delivered", "failed"] | None = None,
    limit: int = Query(50, ge=1, le=200),
    ctx: Ctx = require(M),
):
    return svc.deliveries(ctx, webhook_id, status, limit)


@router.post(
    "/deliveries/{delivery_id}/retry",
    response_model=WebhookDeliveryOut,
    responses=ERR,
    summary="Send a failed or pending delivery again",
)
def retry(delivery_id: int, ctx: Ctx = require(M)):
    return svc.retry(ctx, delivery_id)
