"""Procurement: vendors, purchase orders, receiving, inventory, delivery and markup rules."""

from fastapi import APIRouter, Response
from sqlalchemy import select

from app import permissions as P
from app import procurement as svc
from app.deps import Ctx, require
from app.models import InventoryItem, Organization, PurchaseOrder
from app.procurement_schemas import (
    DeliverIn,
    InventoryItemOut,
    InventoryStatus,
    MarkupRuleIn,
    MarkupRuleOut,
    MarkupRulePatch,
    POStatus,
    PurchaseOrderIn,
    PurchaseOrderLineIn,
    PurchaseOrderLinePatch,
    PurchaseOrderOut,
    PurchaseOrderPatch,
    ReceiveIn,
    VendorIn,
    VendorOut,
    VendorPatch,
)
from app.schemas import ErrorOut

router = APIRouter(prefix="/procurement", tags=["procurement"])
ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}
VENDOR_NOT_NULL = ("name",)


def _po_out(ctx: Ctx, po: PurchaseOrder) -> PurchaseOrderOut:
    out = PurchaseOrderOut.model_validate(po)
    out.vendor_name = po.vendor.name if po.vendor is not None else None
    return out


def _item_outs(ctx: Ctx, items: list[InventoryItem]) -> list[InventoryItemOut]:
    ids = {i.organization_id for i in items if i.organization_id is not None}
    names = (
        dict(
            ctx.db.execute(
                select(Organization.id, Organization.name).where(Organization.id.in_(ids))
            ).all()
        )
        if ids
        else {}
    )
    outs = []
    for item in items:
        out = InventoryItemOut.model_validate(item)
        out.organization_name = names.get(item.organization_id)
        outs.append(out)
    return outs


def _item_out(ctx: Ctx, item: InventoryItem) -> InventoryItemOut:
    return _item_outs(ctx, [item])[0]


def _patch(body, not_null: tuple[str, ...] = ()) -> dict:
    data = body.model_dump(exclude_unset=True)
    return {k: v for k, v in data.items() if v is not None or k not in not_null}


# ---- vendors ----
@router.get("/vendors", response_model=list[VendorOut], summary="List vendors")
def list_vendors(include_archived: bool = False, ctx: Ctx = require(P.PROCUREMENT_READ)):
    return svc.list_vendors(ctx, include_archived)


@router.post(
    "/vendors", response_model=VendorOut, status_code=201, responses=ERR, summary="Add a vendor"
)
def create_vendor(body: VendorIn, ctx: Ctx = require(P.PROCUREMENT_WRITE)):
    return svc.create_vendor(ctx, body.model_dump())


@router.patch(
    "/vendors/{vendor_id}",
    response_model=VendorOut,
    responses=ERR,
    summary="Edit, archive or restore a vendor",
)
def update_vendor(vendor_id: int, body: VendorPatch, ctx: Ctx = require(P.PROCUREMENT_WRITE)):
    return svc.update_vendor(ctx, vendor_id, _patch(body, VENDOR_NOT_NULL))


# ---- purchase orders ----
@router.get(
    "/purchase-orders", response_model=list[PurchaseOrderOut], summary="List purchase orders"
)
def list_pos(
    status: POStatus | None = None,
    vendor_id: int | None = None,
    organization_id: int | None = None,
    ctx: Ctx = require(P.PROCUREMENT_READ),
):
    return [_po_out(ctx, p) for p in svc.list_pos(ctx, status, vendor_id, organization_id)]


@router.post(
    "/purchase-orders",
    response_model=PurchaseOrderOut,
    status_code=201,
    responses=ERR,
    summary="Create a draft purchase order",
)
def create_po(body: PurchaseOrderIn, ctx: Ctx = require(P.PROCUREMENT_WRITE)):
    return _po_out(ctx, svc.create_po(ctx, body.model_dump()))


@router.get(
    "/purchase-orders/{po_id}",
    response_model=PurchaseOrderOut,
    responses=ERR,
    summary="One purchase order with its lines",
)
def get_po(po_id: int, ctx: Ctx = require(P.PROCUREMENT_READ)):
    return _po_out(ctx, svc.get_po(ctx, po_id))


@router.patch(
    "/purchase-orders/{po_id}",
    response_model=PurchaseOrderOut,
    responses=ERR,
    summary="Edit a purchase order (vendor, client and lines only while draft)",
)
def update_po(po_id: int, body: PurchaseOrderPatch, ctx: Ctx = require(P.PROCUREMENT_WRITE)):
    return _po_out(ctx, svc.update_po(ctx, po_id, _patch(body, ("vendor_id", "lines"))))


@router.post(
    "/purchase-orders/{po_id}/lines",
    response_model=PurchaseOrderOut,
    status_code=201,
    responses=ERR,
    summary="Add a line to a draft purchase order",
)
def add_line(po_id: int, body: PurchaseOrderLineIn, ctx: Ctx = require(P.PROCUREMENT_WRITE)):
    svc.add_line(ctx, po_id, body.model_dump())
    return _po_out(ctx, svc.get_po(ctx, po_id))


@router.patch(
    "/purchase-orders/{po_id}/lines/{line_id}",
    response_model=PurchaseOrderOut,
    responses=ERR,
    summary="Edit a line of a draft purchase order",
)
def update_line(
    po_id: int,
    line_id: int,
    body: PurchaseOrderLinePatch,
    ctx: Ctx = require(P.PROCUREMENT_WRITE),
):
    svc.update_line(ctx, po_id, line_id, body.model_dump(exclude_unset=True))
    ctx.db.expire_all()
    return _po_out(ctx, svc.get_po(ctx, po_id))


@router.delete(
    "/purchase-orders/{po_id}/lines/{line_id}",
    status_code=204,
    responses=ERR,
    summary="Remove a line from a draft purchase order",
)
def delete_line(po_id: int, line_id: int, ctx: Ctx = require(P.PROCUREMENT_WRITE)):
    svc.delete_line(ctx, po_id, line_id)
    return Response(status_code=204)


@router.post(
    "/purchase-orders/{po_id}/order",
    response_model=PurchaseOrderOut,
    responses=ERR,
    summary="Place a draft purchase order with the vendor",
)
def order_po(po_id: int, ctx: Ctx = require(P.PROCUREMENT_WRITE)):
    return _po_out(ctx, svc.order(ctx, po_id))


@router.post(
    "/purchase-orders/{po_id}/cancel",
    response_model=PurchaseOrderOut,
    responses=ERR,
    summary="Cancel a draft or ordered purchase order (nothing received yet)",
)
def cancel_po(po_id: int, ctx: Ctx = require(P.PROCUREMENT_WRITE)):
    return _po_out(ctx, svc.cancel(ctx, po_id))


@router.post(
    "/purchase-orders/{po_id}/receive",
    response_model=list[InventoryItemOut],
    status_code=201,
    responses=ERR,
    summary="Receive goods against a line; serialised lines need one serial per unit",
)
def receive(po_id: int, body: ReceiveIn, ctx: Ctx = require(P.PROCUREMENT_WRITE)):
    return _item_outs(ctx, svc.receive(ctx, po_id, body.line_id, body.quantity, body.serials))


# ---- inventory ----
@router.get("/inventory", response_model=list[InventoryItemOut], summary="List inventory")
def list_inventory(
    status: InventoryStatus | None = None,
    organization_id: int | None = None,
    product_id: int | None = None,
    q: str | None = None,
    ctx: Ctx = require(P.PROCUREMENT_READ),
):
    return _item_outs(ctx, svc.list_inventory(ctx, status, organization_id, product_id, q))


@router.get(
    "/inventory/{item_id}",
    response_model=InventoryItemOut,
    responses=ERR,
    summary="One inventory item",
)
def get_item(item_id: int, ctx: Ctx = require(P.PROCUREMENT_READ)):
    return _item_out(ctx, svc.get_item(ctx, item_id))


@router.post(
    "/inventory/{item_id}/deliver",
    response_model=InventoryItemOut,
    responses=ERR,
    summary="Deliver stock to a client; a billable item adds a marked-up product charge",
)
def deliver(item_id: int, body: DeliverIn, ctx: Ctx = require(P.PROCUREMENT_WRITE)):
    item = svc.deliver(
        ctx,
        item_id,
        body.organization_id,
        body.quantity,
        body.asset_id,
        body.create_asset,
        body.delivered_on,
    )
    return _item_out(ctx, item)


@router.post(
    "/inventory/{item_id}/undo-delivery",
    response_model=InventoryItemOut,
    responses=ERR,
    summary="Take back a delivery that has not been invoiced; its charge is voided",
)
def undo_delivery(item_id: int, ctx: Ctx = require(P.PROCUREMENT_WRITE)):
    return _item_out(ctx, svc.undo_delivery(ctx, item_id))


@router.post(
    "/inventory/{item_id}/consume",
    response_model=InventoryItemOut,
    responses=ERR,
    summary="Mark stock as used internally (never billed)",
)
def consume(item_id: int, ctx: Ctx = require(P.PROCUREMENT_WRITE)):
    return _item_out(ctx, svc.consume(ctx, item_id))


@router.get(
    "/organizations/{org_id}/inventory",
    response_model=list[InventoryItemOut],
    responses=ERR,
    summary="Items delivered to a client, and stock reserved for it",
)
def org_inventory(org_id: int, ctx: Ctx = require(P.PROCUREMENT_READ)):
    return _item_outs(ctx, svc.list_org_inventory(ctx, org_id))


# ---- markup rules ----
@router.get("/markup-rules", response_model=list[MarkupRuleOut], summary="List markup rules")
def list_markup_rules(ctx: Ctx = require(P.PROCUREMENT_READ)):
    return svc.list_markup_rules(ctx)


@router.post(
    "/markup-rules",
    response_model=MarkupRuleOut,
    status_code=201,
    responses=ERR,
    summary="Add a markup rule for a product or a category",
)
def create_markup_rule(body: MarkupRuleIn, ctx: Ctx = require(P.BILLING_WRITE)):
    return svc.create_markup_rule(ctx, body.model_dump())


@router.patch(
    "/markup-rules/{rule_id}",
    response_model=MarkupRuleOut,
    responses=ERR,
    summary="Change a markup rule's percentage",
)
def update_markup_rule(rule_id: int, body: MarkupRulePatch, ctx: Ctx = require(P.BILLING_WRITE)):
    return svc.update_markup_rule(ctx, rule_id, body.model_dump())


@router.delete(
    "/markup-rules/{rule_id}",
    status_code=204,
    responses=ERR,
    summary="Delete a markup rule (items already delivered keep their price)",
)
def delete_markup_rule(rule_id: int, ctx: Ctx = require(P.BILLING_WRITE)):
    svc.delete_markup_rule(ctx, rule_id)
    return Response(status_code=204)
