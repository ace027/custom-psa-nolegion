"""Credit memos: numbered, immutable credits applied to invoices or kept as client credit."""

from fastapi import APIRouter, HTTPException, Query

from app import credits as svc
from app import payment_repo as prepo
from app import permissions as P
from app.deps import Ctx, require
from app.schemas import (
    ApplyIn,
    CreditMemoDetailOut,
    CreditMemoIn,
    CreditMemoLineOut,
    CreditMemoOut,
    ErrorOut,
    MemoApplicationOut,
    Page,
    ReasonIn,
)

router = APIRouter(tags=["credit-memos"])
ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}


def _out(ctx: Ctx, memos) -> list[CreditMemoOut]:
    applied = prepo.memo_applied(ctx.db, [m.id for m in memos])
    return [
        CreditMemoOut(
            id=m.id,
            number=m.number,
            organization_id=m.organization_id,
            organization_name=m.organization.name,
            memo_date=m.memo_date,
            reason=m.reason,
            invoice_id=m.invoice_id,
            subtotal_cents=m.subtotal_cents,
            tax_cents=m.tax_cents,
            total_cents=m.total_cents,
            status=m.status,
            applied_cents=applied[m.id],
            unapplied_cents=m.total_cents - applied[m.id] if m.status == "active" else 0,
            void_reason=m.void_reason,
            voided_at=m.voided_at,
            created_at=m.created_at,
        )
        for m in memos
    ]


def _detail(ctx: Ctx, memo) -> CreditMemoDetailOut:
    return CreditMemoDetailOut(
        **_out(ctx, [memo])[0].model_dump(),
        lines=[
            CreditMemoLineOut.model_validate(x)
            for x in prepo.memo_lines(ctx.db, ctx.scope, memo.id)
        ],
        applications=[
            MemoApplicationOut.model_validate(a)
            for a in prepo.memo_applications(ctx.db, ctx.scope, memo.id)
        ],
    )


@router.get("/credit-memos", response_model=Page[CreditMemoOut], summary="List credit memos")
def list_memos(
    organization_id: int | None = None,
    status: str | None = Query(None, pattern="^(active|void)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: Ctx = require(P.BILLING_READ),
):
    items, total = prepo.list_memos(
        ctx.db, ctx.scope, org_id=organization_id, status=status, limit=limit, offset=offset
    )
    return Page(items=_out(ctx, items), total=total, limit=limit, offset=offset)


@router.post(
    "/credit-memos",
    response_model=CreditMemoDetailOut,
    status_code=201,
    responses=ERR,
    summary="Issue a credit memo (numbered CM-YYYY-NNNN, immutable); optionally apply it now",
)
def create_memo(body: CreditMemoIn, ctx: Ctx = require(P.BILLING_FINALIZE)):
    return _detail(ctx, svc.create_memo(ctx, body.model_dump()))


@router.get(
    "/credit-memos/{memo_id}",
    response_model=CreditMemoDetailOut,
    responses=ERR,
    summary="A credit memo with its lines and applications",
)
def get_memo(memo_id: int, ctx: Ctx = require(P.BILLING_READ)):
    memo = prepo.get_memo(ctx.db, ctx.scope, memo_id)
    if memo is None:
        raise HTTPException(404, "Credit memo not found")
    return _detail(ctx, memo)


@router.post(
    "/credit-memos/{memo_id}/apply",
    response_model=CreditMemoDetailOut,
    responses=ERR,
    summary="Apply unapplied credit memo value to a finalized invoice",
)
def apply_memo(memo_id: int, body: ApplyIn, ctx: Ctx = require(P.PAYMENT_WRITE)):
    svc.apply_memo(ctx, memo_id, body.invoice_id, body.amount_cents)
    return _detail(ctx, prepo.get_memo(ctx.db, ctx.scope, memo_id))


@router.post(
    "/credit-memos/{memo_id}/void",
    response_model=CreditMemoDetailOut,
    responses=ERR,
    summary="Void a credit memo (reason required); its applications are undone",
)
def void_memo(memo_id: int, body: ReasonIn, ctx: Ctx = require(P.BILLING_FINALIZE)):
    return _detail(ctx, svc.void_memo(ctx, memo_id, body.reason))


@router.post(
    "/credit-memo-applications/{application_id}/void",
    response_model=MemoApplicationOut,
    responses=ERR,
    summary="Undo one application (reason required); the value returns to the memo's credit",
)
def void_application(application_id: int, body: ReasonIn, ctx: Ctx = require(P.BILLING_FINALIZE)):
    return svc.void_memo_application(ctx, application_id, body.reason)
