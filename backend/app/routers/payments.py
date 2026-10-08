"""Payments, applying them to invoices, write-offs, and receivables (aging)."""

from fastapi import APIRouter, HTTPException, Query

from app import credits
from app import payment_repo as prepo
from app import payments as svc
from app import permissions as P
from app.deps import Ctx, require
from app.schemas import (
    ApplicationOut,
    ApplyIn,
    ErrorOut,
    Page,
    PaymentDetailOut,
    PaymentIn,
    PaymentOut,
    ReasonIn,
    ReceivablesOut,
    RefundIn,
    RefundOut,
    WriteOffIn,
    WriteOffOut,
)

router = APIRouter(tags=["payments"])
ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}


def _out(ctx: Ctx, payments) -> list[PaymentOut]:
    applied = prepo.applied_by_payment(ctx.db, [p.id for p in payments])
    refunded = prepo.refunded_by_payment(ctx.db, [p.id for p in payments])
    return [
        PaymentOut(
            id=p.id,
            organization_id=p.organization_id,
            organization_name=p.organization.name,
            amount_cents=p.amount_cents,
            received_on=p.received_on,
            method=p.method,
            reference=p.reference,
            notes=p.notes,
            status=p.status,
            applied_cents=applied[p.id],
            refunded_cents=refunded[p.id],
            unapplied_cents=(
                p.amount_cents - applied[p.id] - refunded[p.id] if p.status == "active" else 0
            ),
            void_reason=p.void_reason,
            voided_at=p.voided_at,
            created_at=p.created_at,
        )
        for p in payments
    ]


def _detail(ctx: Ctx, payment) -> PaymentDetailOut:
    apps = prepo.applications_for_payment(ctx.db, ctx.scope, payment.id)
    return PaymentDetailOut(
        **_out(ctx, [payment])[0].model_dump(),
        applications=[ApplicationOut.model_validate(a) for a in apps],
        refunds=[
            RefundOut.model_validate(r)
            for r in prepo.refunds_for_payment(ctx.db, ctx.scope, payment.id)
        ],
    )


@router.get("/payments", response_model=Page[PaymentOut], summary="List payments received")
def list_payments(
    organization_id: int | None = None,
    status: str | None = Query(None, pattern="^(active|void)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: Ctx = require(P.BILLING_READ),
):
    items, total = prepo.list_payments(
        ctx.db, ctx.scope, org_id=organization_id, status=status, limit=limit, offset=offset
    )
    return Page(items=_out(ctx, items), total=total, limit=limit, offset=offset)


@router.post(
    "/payments",
    response_model=PaymentDetailOut,
    status_code=201,
    responses=ERR,
    summary="Record a payment, optionally applying it to invoices; any remainder is credit",
)
def create_payment(body: PaymentIn, ctx: Ctx = require(P.PAYMENT_WRITE)):
    return _detail(ctx, svc.create_payment(ctx, body.model_dump()))


@router.get(
    "/payments/{payment_id}",
    response_model=PaymentDetailOut,
    responses=ERR,
    summary="A payment with its applications",
)
def get_payment(payment_id: int, ctx: Ctx = require(P.BILLING_READ)):
    payment = prepo.get_payment(ctx.db, ctx.scope, payment_id)
    if payment is None:
        raise HTTPException(404, "Payment not found")
    return _detail(ctx, payment)


@router.post(
    "/payments/{payment_id}/apply",
    response_model=PaymentDetailOut,
    responses=ERR,
    summary="Apply (unapplied) payment credit to a finalized invoice",
)
def apply_payment(payment_id: int, body: ApplyIn, ctx: Ctx = require(P.PAYMENT_WRITE)):
    svc.apply_payment(ctx, payment_id, body.invoice_id, body.amount_cents)
    return _detail(ctx, prepo.get_payment(ctx.db, ctx.scope, payment_id))


@router.post(
    "/payments/{payment_id}/void",
    response_model=PaymentDetailOut,
    responses=ERR,
    summary="Void a payment (reason required); the invoices it paid become open again",
)
def void_payment(payment_id: int, body: ReasonIn, ctx: Ctx = require(P.BILLING_FINALIZE)):
    return _detail(ctx, svc.void_payment(ctx, payment_id, body.reason))


@router.post(
    "/payments/{payment_id}/refunds",
    response_model=RefundOut,
    status_code=201,
    responses=ERR,
    summary="Record money paid back against a payment (only its unapplied part; nothing is sent)",
)
def create_refund(payment_id: int, body: RefundIn, ctx: Ctx = require(P.BILLING_FINALIZE)):
    return credits.create_refund(ctx, payment_id, body.model_dump())


@router.post(
    "/refunds/{refund_id}/void",
    response_model=RefundOut,
    responses=ERR,
    summary="Void a refund (reason required); the money is available on the payment again",
)
def void_refund(refund_id: int, body: ReasonIn, ctx: Ctx = require(P.BILLING_FINALIZE)):
    return credits.void_refund(ctx, refund_id, body.reason)


@router.post(
    "/payment-applications/{application_id}/void",
    response_model=ApplicationOut,
    responses=ERR,
    summary="Undo one application (reason required); the money returns to the payment's credit",
)
def void_application(application_id: int, body: ReasonIn, ctx: Ctx = require(P.BILLING_FINALIZE)):
    return svc.void_application(ctx, application_id, body.reason)


@router.post(
    "/invoices/{invoice_id}/write-off",
    response_model=WriteOffOut,
    status_code=201,
    responses=ERR,
    summary="Write off an uncollectible balance (reason required)",
)
def write_off(invoice_id: int, body: WriteOffIn, ctx: Ctx = require(P.BILLING_FINALIZE)):
    return svc.write_off(ctx, invoice_id, body.amount_cents, body.reason)


@router.post(
    "/write-offs/{write_off_id}/void",
    response_model=WriteOffOut,
    responses=ERR,
    summary="Reverse a write-off (reason required)",
)
def void_write_off(write_off_id: int, body: ReasonIn, ctx: Ctx = require(P.BILLING_FINALIZE)):
    return svc.void_write_off(ctx, write_off_id, body.reason)


@router.get(
    "/receivables",
    response_model=ReceivablesOut,
    summary="Open balances by client, aged by days past due, plus unapplied credit",
)
def receivables(ctx: Ctx = require(P.BILLING_READ)):
    return svc.receivables(ctx)
