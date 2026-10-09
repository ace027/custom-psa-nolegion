"""Rates, products, agreements and one-off product charges."""

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Response

from app import billing as svc
from app import billing_repo as brepo
from app import permissions as P
from app import repositories as repo
from app.deps import Ctx, require
from app.permissions import has_permission
from app.schemas import (
    AgreementIn,
    AgreementOut,
    AgreementPatch,
    ChargeIn,
    ChargeOut,
    DeviceCountOut,
    ErrorOut,
    OrgBillingOut,
    OrgBillingPatch,
    OrgRateIn,
    OrgRateOut,
    ProductIn,
    ProductOut,
    ProductPatch,
    QuantityLogOut,
    WorkTypeBillingOut,
    WorkTypeBillingPatch,
)

router = APIRouter(tags=["billing"])
ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}
AGREEMENT_ERR = {**ERR, 422: {"model": ErrorOut}}


# ---- work type rates ----
@router.get(
    "/billing/work-types",
    response_model=list[WorkTypeBillingOut],
    summary="Hourly rate and taxability per work type",
)
def list_work_type_rates(ctx: Ctx = require(P.BILLING_READ)):
    return brepo.list_work_types(ctx.db)


@router.patch(
    "/billing/work-types/{work_type_id}",
    response_model=WorkTypeBillingOut,
    responses=ERR,
    summary="Set a work type's hourly rate / taxability / block coverage",
)
def patch_work_type_rate(
    work_type_id: int, body: WorkTypeBillingPatch, ctx: Ctx = require(P.BILLING_WRITE)
):
    return svc.update_work_type_billing(ctx, work_type_id, body.model_dump(exclude_unset=True))


# ---- per-organization terms, tax, rate overrides ----
def _org_billing(ctx: Ctx, org_id: int) -> OrgBillingOut:
    org = repo.get_organization(ctx.db, ctx.scope, org_id)
    if org is None:
        raise HTTPException(404, "Organization not found")
    return OrgBillingOut(
        payment_terms_days=org.payment_terms_days,
        tax_rate_bp=org.tax_rate_bp,
        do_not_remind=org.do_not_remind,
        late_fees_enabled=org.late_fees_enabled,
        rates=[
            OrgRateOut(work_type_id=r.work_type_id, rate_cents=r.rate_cents)
            for r in brepo.list_org_rates(ctx.db, ctx.scope, org_id)
        ],
    )


@router.get(
    "/organizations/{org_id}/billing",
    response_model=OrgBillingOut,
    responses=ERR,
    summary="An organization's payment terms, tax rate and hourly-rate overrides",
)
def get_org_billing(org_id: int, ctx: Ctx = require(P.BILLING_READ)):
    return _org_billing(ctx, org_id)


@router.patch(
    "/organizations/{org_id}/billing",
    response_model=OrgBillingOut,
    responses=ERR,
    summary="Set payment terms (days) and tax rate (basis points)",
)
def patch_org_billing(org_id: int, body: OrgBillingPatch, ctx: Ctx = require(P.BILLING_WRITE)):
    svc.update_org_billing(ctx, org_id, body.model_dump(exclude_unset=True))
    return _org_billing(ctx, org_id)


@router.put(
    "/organizations/{org_id}/billing/rates/{work_type_id}",
    response_model=OrgRateOut,
    responses=ERR,
    summary="Override the hourly rate for one work type for this client",
)
def put_org_rate(
    org_id: int, work_type_id: int, body: OrgRateIn, ctx: Ctx = require(P.BILLING_WRITE)
):
    return svc.set_org_rate(ctx, org_id, work_type_id, body.rate_cents)


@router.delete(
    "/organizations/{org_id}/billing/rates/{work_type_id}",
    status_code=204,
    responses=ERR,
    summary="Remove a client's rate override (back to the default rate)",
)
def delete_org_rate(org_id: int, work_type_id: int, ctx: Ctx = require(P.BILLING_WRITE)):
    svc.delete_org_rate(ctx, org_id, work_type_id)
    return Response(status_code=204)


# ---- products ----
def _product_out(ctx: Ctx, product) -> ProductOut:
    """Cost (your margin) is only shown to people who manage billing."""
    out = ProductOut.model_validate(product)
    if not has_permission(ctx.user.role, P.BILLING_WRITE):
        out.cost_cents = None
    return out


@router.get("/products", response_model=list[ProductOut], summary="List the product catalog")
def list_products(include_archived: bool = False, ctx: Ctx = require(P.BILLING_READ)):
    return [_product_out(ctx, p) for p in brepo.list_products(ctx.db, include_archived)]


@router.post(
    "/products", response_model=ProductOut, status_code=201, responses=ERR, summary="Add a product"
)
def create_product(body: ProductIn, ctx: Ctx = require(P.BILLING_WRITE)):
    return _product_out(ctx, svc.create_product(ctx, body.model_dump()))


@router.patch(
    "/products/{product_id}",
    response_model=ProductOut,
    responses=ERR,
    summary="Edit a product (existing charges and invoices keep their price)",
)
def update_product(product_id: int, body: ProductPatch, ctx: Ctx = require(P.BILLING_WRITE)):
    return _product_out(
        ctx, svc.update_product(ctx, product_id, body.model_dump(exclude_unset=True))
    )


@router.post(
    "/products/{product_id}/archive",
    response_model=ProductOut,
    responses=ERR,
    summary="Archive a product",
)
def archive_product(product_id: int, ctx: Ctx = require(P.BILLING_WRITE)):
    return _product_out(ctx, svc.set_product_archived(ctx, product_id, True))


@router.post(
    "/products/{product_id}/unarchive",
    response_model=ProductOut,
    responses=ERR,
    summary="Restore an archived product",
)
def unarchive_product(product_id: int, ctx: Ctx = require(P.BILLING_WRITE)):
    return _product_out(ctx, svc.set_product_archived(ctx, product_id, False))


# ---- agreements ----
def _agreement_out(a) -> AgreementOut:
    return AgreementOut(
        id=a.id,
        organization_id=a.organization_id,
        organization_name=a.organization.name,
        name=a.name,
        type=a.type,
        unit_price_cents=a.unit_price_cents,
        quantity=a.quantity,
        taxable=a.taxable,
        start_date=a.start_date,
        end_date=a.end_date,
        notes=a.notes,
        block_minutes=a.block_minutes,
        monthly_amount_cents=svc.monthly_amount_cents(a),
    )


@router.get(
    "/agreements", response_model=list[AgreementOut], summary="List recurring service agreements"
)
def list_agreements(
    organization_id: int | None = None,
    active_on: date | None = Query(None, description="Only agreements in force"),
    ctx: Ctx = require(P.BILLING_READ),
):
    return [
        _agreement_out(a)
        for a in brepo.list_agreements(
            ctx.db, ctx.scope, org_id=organization_id, active_on=active_on
        )
    ]


@router.post(
    "/agreements",
    response_model=AgreementOut,
    status_code=201,
    responses=AGREEMENT_ERR,
    summary="Create a recurring agreement (per user, per device, flat fee, or block hours)",
)
def create_agreement(body: AgreementIn, ctx: Ctx = require(P.BILLING_WRITE)):
    try:
        return _agreement_out(svc.create_agreement(ctx, body.model_dump()))
    except svc.InvalidAgreement as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get(
    "/agreements/{agreement_id}",
    response_model=AgreementOut,
    responses=ERR,
    summary="Get an agreement",
)
def get_agreement(agreement_id: int, ctx: Ctx = require(P.BILLING_READ)):
    a = brepo.get_agreement(ctx.db, ctx.scope, agreement_id)
    if a is None:
        raise HTTPException(404, "Agreement not found")
    return _agreement_out(a)


@router.patch(
    "/agreements/{agreement_id}",
    response_model=AgreementOut,
    responses=AGREEMENT_ERR,
    summary="Edit an agreement; quantity changes are logged with an optional reason",
)
def update_agreement(agreement_id: int, body: AgreementPatch, ctx: Ctx = require(P.BILLING_WRITE)):
    try:
        return _agreement_out(
            svc.update_agreement(ctx, agreement_id, body.model_dump(exclude_unset=True))
        )
    except svc.InvalidAgreement as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get(
    "/agreements/{agreement_id}/quantity-log",
    response_model=list[QuantityLogOut],
    responses=ERR,
    summary="History of quantity changes (evidence for what was billed)",
)
def agreement_quantity_log(agreement_id: int, ctx: Ctx = require(P.BILLING_READ)):
    if brepo.get_agreement(ctx.db, ctx.scope, agreement_id) is None:
        raise HTTPException(404, "Agreement not found")
    return brepo.quantity_log(ctx.db, ctx.scope, agreement_id)


@router.get(
    "/agreements/{agreement_id}/device-count",
    response_model=DeviceCountOut,
    responses=ERR,
    summary="NinjaOne device count for a per-device agreement (a suggestion; nothing changes)",
)
def agreement_device_count(agreement_id: int, ctx: Ctx = require(P.BILLING_READ)):
    a = brepo.get_agreement(ctx.db, ctx.scope, agreement_id)
    if a is None:
        raise HTTPException(404, "Agreement not found")
    if a.type != "per_device":
        raise HTTPException(409, "Only per-device agreements have a device count")
    n = brepo.ninjaone_device_count(ctx.db, ctx.scope, a.organization_id)
    return DeviceCountOut(
        ninjaone_devices=n, agreement_quantity=a.quantity, differs=n != a.quantity
    )


# ---- one-off product charges ----
@router.get(
    "/product-charges",
    response_model=list[ChargeOut],
    summary="One-off product charges (hardware, licenses...) awaiting invoicing",
)
def list_charges(
    organization_id: int | None = None,
    ticket_id: int | None = None,
    unbilled_only: bool = False,
    ctx: Ctx = require(P.BILLING_READ),
):
    return brepo.list_charges(
        ctx.db, ctx.scope, org_id=organization_id, ticket_id=ticket_id, unbilled_only=unbilled_only
    )


@router.post(
    "/product-charges",
    response_model=ChargeOut,
    status_code=201,
    responses=ERR,
    summary="Record a product sale; it goes on the client's next invoice",
)
def create_charge(body: ChargeIn, ctx: Ctx = require(P.CHARGE_WRITE)):
    return svc.create_charge(ctx, body.model_dump())


@router.post(
    "/product-charges/{charge_id}/void",
    response_model=ChargeOut,
    responses=ERR,
    summary="Void a charge that has not been invoiced",
)
def void_charge(charge_id: int, ctx: Ctx = require(P.CHARGE_WRITE)):
    return svc.void_charge(ctx, charge_id)
