"""Procurement: vendors, purchase orders, receiving, inventory, delivery to clients and markup.

Money rule: a delivered billable item becomes ONE ProductCharge at cost plus the resolved markup
(money.marked_up). Invoice amounts and tax are never computed here; the billing run does that from
the charge. Hard deletes are used only for draft PO lines and markup rules; everything else
archives or changes status. Undoing a delivery voids the charge and is refused once invoiced."""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app import audit
from app import repositories as repo
from app.assets import normalize_serial
from app.billing import today
from app.deps import Ctx
from app.errors import Conflict, NotFound
from app.models import (
    Asset,
    InventoryItem,
    MarkupRule,
    Product,
    ProductCharge,
    PurchaseOrder,
    PurchaseOrderLine,
    Vendor,
)
from app.money import marked_up
from app.ticket_services import now

VENDOR_EDITABLE = ("name", "account_number", "email", "phone", "website", "notes")
PO_HEADER_EDITABLE = ("ordered_on", "expected_on", "vendor_reference", "notes")
LINE_NOT_NULL = ("description", "quantity", "unit_cost_cents", "serialised", "billable", "taxable")


def _flush(ctx: Ctx, message: str) -> None:
    try:
        ctx.db.flush()
    except IntegrityError as exc:
        ctx.db.rollback()
        raise Conflict(message) from exc


# ---- vendors ----------------------------------------------------------------------------------
def get_vendor(ctx: Ctx, vendor_id: int) -> Vendor:
    vendor = ctx.db.get(Vendor, vendor_id)
    if vendor is None:
        raise NotFound("Vendor not found")
    return vendor


def list_vendors(ctx: Ctx, include_archived: bool = False) -> list[Vendor]:
    stmt = select(Vendor)
    if not include_archived:
        stmt = stmt.where(Vendor.archived_at.is_(None))
    return list(ctx.db.execute(stmt.order_by(func.lower(Vendor.name), Vendor.id)).scalars())


def create_vendor(ctx: Ctx, data: dict) -> Vendor:
    vendor = Vendor(**{k: v for k, v in data.items() if k in VENDOR_EDITABLE})
    ctx.db.add(vendor)
    _flush(ctx, "A vendor with that name already exists")
    ctx.db.refresh(vendor)
    audit.record(ctx.db, ctx.user, "vendor.create", vendor, after=audit.snapshot(vendor))
    return vendor


def update_vendor(ctx: Ctx, vendor_id: int, data: dict) -> Vendor:
    vendor = get_vendor(ctx, vendor_id)
    before = audit.snapshot(vendor)
    for key, value in data.items():
        if key in VENDOR_EDITABLE and (value is not None or key != "name"):
            setattr(vendor, key, value)
    archived = data.get("archived")
    if archived is True and vendor.archived_at is None:
        vendor.archived_at = now()
    elif archived is False:
        vendor.archived_at = None
    _flush(ctx, "A vendor with that name already exists")
    ctx.db.refresh(vendor)
    action = "vendor.update"
    if archived is True and before["archived_at"] is None:
        action = "vendor.archive"
    elif archived is False and before["archived_at"] is not None:
        action = "vendor.unarchive"
    audit.record(ctx.db, ctx.user, action, vendor, before=before, after=audit.snapshot(vendor))
    return vendor


# ---- purchase orders --------------------------------------------------------------------------
def get_po(ctx: Ctx, po_id: int, *, lock: bool = False) -> PurchaseOrder:
    stmt = select(PurchaseOrder).where(PurchaseOrder.id == po_id)
    if lock:
        stmt = stmt.with_for_update(of=PurchaseOrder)
    po = ctx.db.execute(stmt).scalar_one_or_none()
    if po is None:
        raise NotFound("Purchase order not found")
    return po


def list_pos(
    ctx: Ctx,
    status: str | None = None,
    vendor_id: int | None = None,
    organization_id: int | None = None,
) -> list[PurchaseOrder]:
    stmt = select(PurchaseOrder)
    if status:
        stmt = stmt.where(PurchaseOrder.status == status)
    if vendor_id is not None:
        stmt = stmt.where(PurchaseOrder.vendor_id == vendor_id)
    if organization_id is not None:
        stmt = stmt.where(PurchaseOrder.organization_id == organization_id)
    return list(ctx.db.execute(stmt.order_by(PurchaseOrder.id.desc())).scalars().unique())


def _active_vendor(ctx: Ctx, vendor_id: int) -> Vendor:
    vendor = ctx.db.get(Vendor, vendor_id)
    if vendor is None or vendor.archived_at is not None:
        raise Conflict("Choose an active vendor")
    return vendor


def _visible_org(ctx: Ctx, org_id: int | None) -> None:
    if org_id is None:
        return
    org = repo.get_organization(ctx.db, ctx.scope, org_id)
    if org is None:
        raise NotFound("Organization not found")
    if org.archived_at is not None:
        raise Conflict("That client is archived")


def _product(ctx: Ctx, product_id: int | None) -> Product | None:
    if product_id is None:
        return None
    product = ctx.db.get(Product, product_id)
    if product is None or product.archived_at is not None:
        raise Conflict("Unknown or archived product")
    return product


def _build_line(ctx: Ctx, po: PurchaseOrder, data: dict, position: int) -> PurchaseOrderLine:
    product = _product(ctx, data.get("product_id"))
    description = (data.get("description") or "").strip() or (product.name if product else "")
    if not description:
        raise Conflict("A description is required when no product is chosen")
    cost = data.get("unit_cost_cents")
    if cost is None and product is not None:
        cost = product.cost_cents
    if cost is None:
        raise Conflict("Unit cost required")
    taxable = data.get("taxable")
    if taxable is None:
        taxable = product.taxable if product is not None else True
    line = PurchaseOrderLine(
        purchase_order_id=po.id,
        position=position,
        product_id=data.get("product_id"),
        description=description,
        quantity=data["quantity"],
        unit_cost_cents=cost,
        serialised=bool(data.get("serialised", False)),
        billable=bool(data.get("billable", True)),
        taxable=taxable,
        markup_bp=data.get("markup_bp"),
    )
    ctx.db.add(line)
    return line


def _require_draft(po: PurchaseOrder) -> None:
    if po.status != "draft":
        raise Conflict("Only a draft purchase order can be changed")


def create_po(ctx: Ctx, data: dict) -> PurchaseOrder:
    _active_vendor(ctx, data["vendor_id"])
    _visible_org(ctx, data.get("organization_id"))
    po = PurchaseOrder(
        vendor_id=data["vendor_id"],
        organization_id=data.get("organization_id"),
        status="draft",
        created_by=ctx.user.id if ctx.user else None,
        **{k: data.get(k) for k in PO_HEADER_EDITABLE},
    )
    ctx.db.add(po)
    ctx.db.flush()
    po.number = f"PO-{po.id}"
    for position, line in enumerate(data.get("lines") or []):
        _build_line(ctx, po, line, position)
    ctx.db.flush()
    ctx.db.refresh(po)
    audit.record(
        ctx.db,
        ctx.user,
        "purchase_order.create",
        po,
        after={**audit.snapshot(po), "line_count": len(po.lines)},
        organization_id=po.organization_id,
    )
    return po


def update_po(ctx: Ctx, po_id: int, data: dict) -> PurchaseOrder:
    po = get_po(ctx, po_id, lock=True)
    if po.status in ("received", "cancelled"):
        raise Conflict(f"A {po.status} purchase order is read-only")
    structural = {"vendor_id", "organization_id", "lines"} & {
        k for k, v in data.items() if v is not None or k == "organization_id"
    }
    if structural:
        _require_draft(po)
    before = {**audit.snapshot(po), "line_count": len(po.lines)}
    if data.get("vendor_id") is not None:
        _active_vendor(ctx, data["vendor_id"])
        po.vendor_id = data["vendor_id"]
    if "organization_id" in data:
        _visible_org(ctx, data["organization_id"])
        po.organization_id = data["organization_id"]
    for key in PO_HEADER_EDITABLE:
        if key in data:
            setattr(po, key, data[key])
    if data.get("lines") is not None:
        for old in list(po.lines):
            po.lines.remove(old)
        ctx.db.flush()
        for position, line in enumerate(data["lines"]):
            _build_line(ctx, po, line, position)
    ctx.db.flush()
    ctx.db.refresh(po)
    ctx.db.expire(po, ["vendor"])
    audit.record(
        ctx.db,
        ctx.user,
        "purchase_order.update",
        po,
        before=before,
        after={**audit.snapshot(po), "line_count": len(po.lines)},
        organization_id=po.organization_id,
    )
    return po


def _line_of(po: PurchaseOrder, line_id: int) -> PurchaseOrderLine:
    for line in po.lines:
        if line.id == line_id:
            return line
    raise NotFound("Purchase order line not found")


def add_line(ctx: Ctx, po_id: int, data: dict) -> PurchaseOrderLine:
    po = get_po(ctx, po_id, lock=True)
    _require_draft(po)
    position = max((ln.position for ln in po.lines), default=-1) + 1
    line = _build_line(ctx, po, data, position)
    ctx.db.flush()
    ctx.db.refresh(line)
    audit.record(
        ctx.db,
        ctx.user,
        "purchase_order.line_add",
        line,
        after=audit.snapshot(line),
        organization_id=po.organization_id,
    )
    return line


def update_line(ctx: Ctx, po_id: int, line_id: int, data: dict) -> PurchaseOrderLine:
    po = get_po(ctx, po_id, lock=True)
    _require_draft(po)
    line = _line_of(po, line_id)
    before = audit.snapshot(line)
    if data.get("product_id") is not None:
        _product(ctx, data["product_id"])
    for key, value in data.items():
        if value is None and key in LINE_NOT_NULL:
            continue
        setattr(line, key, value)
    ctx.db.flush()
    ctx.db.refresh(line)
    audit.record(
        ctx.db,
        ctx.user,
        "purchase_order.line_update",
        line,
        before=before,
        after=audit.snapshot(line),
        organization_id=po.organization_id,
    )
    return line


def delete_line(ctx: Ctx, po_id: int, line_id: int) -> None:
    po = get_po(ctx, po_id, lock=True)
    _require_draft(po)
    line = _line_of(po, line_id)
    before = audit.snapshot(line)
    po.lines.remove(line)
    ctx.db.flush()
    audit.record(
        ctx.db,
        ctx.user,
        "purchase_order.line_delete",
        po,
        before=before,
        organization_id=po.organization_id,
    )


def order(ctx: Ctx, po_id: int) -> PurchaseOrder:
    po = get_po(ctx, po_id, lock=True)
    _require_draft(po)
    if not po.lines:
        raise Conflict("Add at least one line before ordering")
    before = audit.snapshot(po)
    po.status = "ordered"
    if po.ordered_on is None:
        po.ordered_on = today(ctx)
    ctx.db.flush()
    ctx.db.refresh(po)
    audit.record(
        ctx.db,
        ctx.user,
        "purchase_order.order",
        po,
        before=before,
        after=audit.snapshot(po),
        organization_id=po.organization_id,
    )
    return po


def cancel(ctx: Ctx, po_id: int) -> PurchaseOrder:
    po = get_po(ctx, po_id, lock=True)
    if po.status not in ("draft", "ordered"):
        raise Conflict(f"A {po.status} purchase order cannot be cancelled")
    if any(ln.received_quantity > 0 for ln in po.lines):
        raise Conflict("Goods have been received against this order; it cannot be cancelled")
    before = audit.snapshot(po)
    po.status = "cancelled"
    ctx.db.flush()
    ctx.db.refresh(po)
    audit.record(
        ctx.db,
        ctx.user,
        "purchase_order.cancel",
        po,
        before=before,
        after=audit.snapshot(po),
        organization_id=po.organization_id,
    )
    return po


# ---- markup rules -----------------------------------------------------------------------------
def list_markup_rules(ctx: Ctx) -> list[MarkupRule]:
    return list(ctx.db.execute(select(MarkupRule).order_by(MarkupRule.id)).scalars())


def get_markup_rule(ctx: Ctx, rule_id: int) -> MarkupRule:
    rule = ctx.db.get(MarkupRule, rule_id)
    if rule is None:
        raise NotFound("Markup rule not found")
    return rule


def create_markup_rule(ctx: Ctx, data: dict) -> MarkupRule:
    if data.get("product_id") is not None and ctx.db.get(Product, data["product_id"]) is None:
        raise Conflict("Unknown product")
    rule = MarkupRule(
        product_id=data.get("product_id"),
        category=data.get("category"),
        markup_bp=data["markup_bp"],
    )
    ctx.db.add(rule)
    _flush(ctx, "A markup rule for that product or category already exists")
    ctx.db.refresh(rule)
    audit.record(ctx.db, ctx.user, "markup_rule.create", rule, after=audit.snapshot(rule))
    return rule


def update_markup_rule(ctx: Ctx, rule_id: int, data: dict) -> MarkupRule:
    rule = get_markup_rule(ctx, rule_id)
    before = audit.snapshot(rule)
    rule.markup_bp = data["markup_bp"]
    ctx.db.flush()
    ctx.db.refresh(rule)
    audit.record(
        ctx.db, ctx.user, "markup_rule.update", rule, before=before, after=audit.snapshot(rule)
    )
    return rule


def delete_markup_rule(ctx: Ctx, rule_id: int) -> None:
    rule = get_markup_rule(ctx, rule_id)
    before = audit.snapshot(rule)
    ctx.db.delete(rule)
    ctx.db.flush()
    audit.record(ctx.db, ctx.user, "markup_rule.delete", rule, before=before)


def _resolve(ctx: Ctx, line_markup_bp: int | None, product_id: int | None) -> int:
    """line override > product rule > category rule > the default in Settings."""
    if line_markup_bp is not None:
        return line_markup_bp
    category = None
    if product_id is not None:
        rule = ctx.db.execute(
            select(MarkupRule).where(MarkupRule.product_id == product_id)
        ).scalar_one_or_none()
        if rule is not None:
            return rule.markup_bp
        product = ctx.db.get(Product, product_id)
        category = product.category if product is not None else None
    if category is not None:
        rule = ctx.db.execute(
            select(MarkupRule).where(MarkupRule.category == category)
        ).scalar_one_or_none()
        if rule is not None:
            return rule.markup_bp
    return repo.get_settings_row(ctx.db).default_markup_bp


def resolve_markup(ctx: Ctx, line: PurchaseOrderLine) -> int:
    return _resolve(ctx, line.markup_bp, line.product_id)


# ---- receiving and inventory ------------------------------------------------------------------
def get_item(ctx: Ctx, item_id: int, *, lock: bool = False) -> InventoryItem:
    stmt = select(InventoryItem).where(InventoryItem.id == item_id)
    if lock:
        stmt = stmt.with_for_update()
    item = ctx.db.execute(stmt).scalar_one_or_none()
    if item is None:
        raise NotFound("Inventory item not found")
    return item


def list_inventory(
    ctx: Ctx,
    status: str | None = None,
    organization_id: int | None = None,
    product_id: int | None = None,
    q: str | None = None,
) -> list[InventoryItem]:
    stmt = select(InventoryItem)
    if status:
        stmt = stmt.where(InventoryItem.status == status)
    if organization_id is not None:
        stmt = stmt.where(InventoryItem.organization_id == organization_id)
    if product_id is not None:
        stmt = stmt.where(InventoryItem.product_id == product_id)
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(InventoryItem.description).like(like),
                func.lower(func.coalesce(InventoryItem.serial_number, "")).like(like),
            )
        )
    return list(ctx.db.execute(stmt.order_by(InventoryItem.id.desc())).scalars())


def list_org_inventory(ctx: Ctx, org_id: int) -> list[InventoryItem]:
    """What a client holds: items delivered to it plus stock reserved for it."""
    org = repo.get_organization(ctx.db, ctx.scope, org_id)
    if org is None:
        raise NotFound("Organization not found")
    stmt = select(InventoryItem).where(
        InventoryItem.organization_id == org_id,
        InventoryItem.status.in_(("in_stock", "delivered")),
    )
    return list(ctx.db.execute(stmt.order_by(InventoryItem.id.desc())).scalars())


def receive(
    ctx: Ctx, po_id: int, line_id: int, quantity: int, serials: list[str] | None = None
) -> list[InventoryItem]:
    serials = [s.strip() for s in (serials or [])]
    po = get_po(ctx, po_id, lock=True)
    if po.status not in ("ordered", "partial"):
        raise Conflict("Goods can only be received against an ordered purchase order")
    line = _line_of(po, line_id)
    if quantity < 1:
        raise Conflict("Quantity must be at least 1")
    if line.received_quantity + quantity > line.quantity:
        raise Conflict(
            f"Receiving {quantity} would be more than ordered "
            f"({line.received_quantity} of {line.quantity} already received)"
        )
    if line.serialised:
        if len(serials) != quantity:
            raise Conflict(f"Enter exactly {quantity} serial numbers, one per unit")
        lowered = [s.lower() for s in serials]
        if any(not s for s in serials) or len(set(lowered)) != len(lowered):
            raise Conflict("Serial numbers must be non-blank and unique")
        taken = ctx.db.execute(
            select(InventoryItem.serial_number).where(
                func.lower(InventoryItem.serial_number).in_(lowered)
            )
        ).scalars()
        dup = next(iter(taken), None)
        if dup is not None:
            raise Conflict(f"Serial number already in inventory: {dup}")
    elif serials:
        raise Conflict("This line is not serialised; do not enter serial numbers")

    received_on = today(ctx)
    units = [(s, 1) for s in serials] if line.serialised else [(None, quantity)]
    items = []
    for serial, qty in units:
        item = InventoryItem(
            purchase_order_line_id=line.id,
            product_id=line.product_id,
            description=line.description,
            serial_number=serial,
            quantity=qty,
            unit_cost_cents=line.unit_cost_cents,
            status="in_stock",
            organization_id=po.organization_id,
            received_on=received_on,
        )
        ctx.db.add(item)
        items.append(item)
    before = {
        "status": po.status,
        "received": {str(ln.id): ln.received_quantity for ln in po.lines},
    }
    line.received_quantity += quantity
    po.status = (
        "received" if all(ln.received_quantity >= ln.quantity for ln in po.lines) else "partial"
    )
    _flush(ctx, "A serial number is already in inventory")
    for item in items:
        ctx.db.refresh(item)
    audit.record(
        ctx.db,
        ctx.user,
        "purchase_order.receive",
        po,
        before=before,
        after={
            "status": po.status,
            "line_id": line.id,
            "quantity": quantity,
            "serials": serials,
            "item_ids": [i.id for i in items],
        },
        organization_id=po.organization_id,
    )
    return items


def _po_org(ctx: Ctx, item: InventoryItem) -> int | None:
    if item.purchase_order_line_id is None:
        return None
    line = ctx.db.get(PurchaseOrderLine, item.purchase_order_line_id)
    po = ctx.db.get(PurchaseOrder, line.purchase_order_id) if line else None
    return po.organization_id if po else None


def deliver(
    ctx: Ctx,
    item_id: int,
    organization_id: int,
    quantity: int | None = None,
    asset_id: int | None = None,
    create_asset: bool = False,
    delivered_on: date | None = None,
) -> InventoryItem:
    if asset_id is not None and create_asset:
        raise Conflict("Choose an existing asset or create one, not both")
    item = get_item(ctx, item_id, lock=True)
    if item.status != "in_stock":
        raise Conflict("Only in-stock items can be delivered")
    if item.organization_id is not None and item.organization_id != organization_id:
        raise Conflict("This item is reserved for a different client")
    org = repo.get_organization(ctx.db, ctx.scope, organization_id)
    if org is None:
        raise NotFound("Organization not found")
    qty = item.quantity if quantity is None else quantity
    if qty < 1 or qty > item.quantity:
        raise Conflict(f"Quantity must be between 1 and {item.quantity}")
    if (asset_id is not None or create_asset) and item.serial_number is None and qty != 1:
        raise Conflict("Only a serialised item or a single unit can be linked to an asset")
    asset = None
    if asset_id is not None:
        asset = ctx.db.get(Asset, asset_id)
        if asset is None or asset.organization_id != organization_id:
            raise Conflict("That asset does not belong to this client")
    before = audit.snapshot(item)
    if qty < item.quantity:  # split a non-serialised row; the remainder stays in stock
        item.quantity -= qty
        row = InventoryItem(
            purchase_order_line_id=item.purchase_order_line_id,
            product_id=item.product_id,
            description=item.description,
            quantity=qty,
            unit_cost_cents=item.unit_cost_cents,
            status="in_stock",
            organization_id=item.organization_id,
            received_on=item.received_on,
            notes=item.notes,
        )
        ctx.db.add(row)
        ctx.db.flush()
        item = row
    on = delivered_on or today(ctx)
    if create_asset:
        asset = Asset(
            organization_id=organization_id,
            kind="other",
            name=item.description[:300],
            serial=item.serial_number,
            serial_norm=normalize_serial(item.serial_number),
        )
        ctx.db.add(asset)
        ctx.db.flush()
    item.status = "delivered"
    item.organization_id = organization_id
    item.delivered_on = on
    item.asset_id = asset.id if asset is not None else None

    line = (
        ctx.db.get(PurchaseOrderLine, item.purchase_order_line_id)
        if item.purchase_order_line_id is not None
        else None
    )
    if line is None or line.billable:
        product = ctx.db.get(Product, item.product_id) if item.product_id is not None else None
        markup_bp = (
            resolve_markup(ctx, line) if line is not None else _resolve(ctx, None, item.product_id)
        )
        if line is not None:
            taxable = line.taxable
        else:
            taxable = product.taxable if product is not None else True
        description = item.description
        if item.serial_number:
            description += f" (S/N {item.serial_number})"
        charge = ProductCharge(
            organization_id=organization_id,
            product_id=item.product_id,
            ticket_id=None,
            description=description,
            quantity=Decimal(qty),
            unit_price_cents=marked_up(item.unit_cost_cents, markup_bp),
            taxable=taxable,
            charged_on=on,
            created_by=ctx.user.id if ctx.user else None,
        )
        ctx.db.add(charge)
        ctx.db.flush()
        item.markup_bp = markup_bp
        item.product_charge_id = charge.id
        audit.record(
            ctx.db,
            ctx.user,
            "charge.create",
            charge,
            after=audit.snapshot(charge),
            organization_id=organization_id,
        )
    _flush(ctx, "Could not deliver this item")
    ctx.db.refresh(item)
    audit.record(
        ctx.db,
        ctx.user,
        "inventory.deliver",
        item,
        before=before,
        after=audit.snapshot(item),
        organization_id=organization_id,
    )
    return item


def undo_delivery(ctx: Ctx, item_id: int) -> InventoryItem:
    item = get_item(ctx, item_id, lock=True)
    if item.status != "delivered":
        raise Conflict("Only a delivered item can be taken back")
    charge = (
        ctx.db.get(ProductCharge, item.product_charge_id, with_for_update=True)
        if item.product_charge_id is not None
        else None
    )
    if charge is not None and charge.invoice_line_id is not None:
        raise Conflict("Already invoiced: issue a credit memo instead")
    before = audit.snapshot(item)
    delivered_org = item.organization_id
    if charge is not None and charge.voided_at is None:
        charge.voided_at = now()
    item.product_charge_id = None
    item.markup_bp = None
    item.delivered_on = None
    item.asset_id = None  # a created asset is kept
    item.status = "in_stock"
    item.organization_id = _po_org(ctx, item)
    ctx.db.flush()
    ctx.db.refresh(item)
    if charge is not None:
        audit.record(
            ctx.db,
            ctx.user,
            "charge.void",
            charge,
            after=audit.snapshot(charge),
            organization_id=delivered_org,
        )
    audit.record(
        ctx.db,
        ctx.user,
        "inventory.undo_delivery",
        item,
        before=before,
        after=audit.snapshot(item),
        organization_id=delivered_org,
    )
    return item


def consume(ctx: Ctx, item_id: int) -> InventoryItem:
    item = get_item(ctx, item_id, lock=True)
    if item.status != "in_stock":
        raise Conflict("Only in-stock items can be marked as consumed")
    before = audit.snapshot(item)
    item.status = "consumed"
    ctx.db.flush()
    ctx.db.refresh(item)
    audit.record(
        ctx.db,
        ctx.user,
        "inventory.consume",
        item,
        before=before,
        after=audit.snapshot(item),
        organization_id=item.organization_id,
    )
    return item
