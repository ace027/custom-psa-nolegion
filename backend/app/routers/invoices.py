"""Invoices, invoice lines, monthly billing runs, PDF."""

from fastapi import APIRouter, HTTPException, Query, Response

from app import billing as svc
from app import billing_repo as brepo
from app import payment_repo as prepo
from app import permissions as P
from app import repositories as repo
from app.deps import Ctx, require
from app.invoice_pdf import render_invoice_pdf
from app.payments import payment_state
from app.schemas import (
    ErrorOut,
    FinalizeIn,
    InvoiceDetailOut,
    InvoiceIn,
    InvoiceOut,
    InvoicePatch,
    InvoicePaymentLine,
    LineIn,
    LineOut,
    LinePatch,
    Page,
    RunDetailOut,
    RunIn,
    RunOut,
    VoidIn,
    WriteOffOut,
)

router = APIRouter(tags=["invoicing"])
ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}


def _invoice_out(inv, state: dict | None = None) -> InvoiceOut:
    return InvoiceOut(
        id=inv.id,
        number=inv.number,
        organization_id=inv.organization_id,
        organization_name=inv.organization.name,
        status=inv.status,
        billing_run_id=inv.billing_run_id,
        period_start=inv.period_start,
        period_end=inv.period_end,
        invoice_date=inv.invoice_date,
        due_date=inv.due_date,
        terms_days=inv.terms_days,
        subtotal_cents=inv.subtotal_cents,
        tax_cents=inv.tax_cents,
        total_cents=inv.total_cents,
        memo=inv.memo,
        warnings=list(inv.warnings or []),
        void_reason=inv.void_reason,
        created_at=inv.created_at,
        finalized_at=inv.finalized_at,
        voided_at=inv.voided_at,
        **(state or {}),
    )


def _outs(ctx: Ctx, invoices) -> list[InvoiceOut]:
    """Invoice output with derived payment state (one query for all balances)."""
    amounts = prepo.amounts_for(ctx.db, [i.id for i in invoices])
    on = svc.today(ctx)
    return [_invoice_out(i, payment_state(i, *amounts[i.id], on)) for i in invoices]


def _detail(ctx: Ctx, inv) -> InvoiceDetailOut:
    lines = [LineOut.model_validate(x) for x in brepo.invoice_lines(ctx.db, ctx.scope, inv.id)]
    apps = prepo.applications_for_invoice(ctx.db, ctx.scope, inv.id)
    payments = prepo.payment_lookup(ctx.db, {a.payment_id for a in apps})
    return InvoiceDetailOut(
        **_outs(ctx, [inv])[0].model_dump(),
        lines=lines,
        payments=[
            InvoicePaymentLine(
                application_id=a.id,
                payment_id=a.payment_id,
                amount_cents=a.amount_cents,
                received_on=payments[a.payment_id].received_on,
                method=payments[a.payment_id].method,
                reference=payments[a.payment_id].reference,
                voided_at=a.voided_at,
                void_reason=a.void_reason,
            )
            for a in apps
        ],
        write_offs=[
            WriteOffOut.model_validate(w)
            for w in prepo.writeoffs_for_invoice(ctx.db, ctx.scope, inv.id)
        ],
    )


def _invoice_or_404(ctx: Ctx, invoice_id: int):
    inv = brepo.get_invoice(ctx.db, ctx.scope, invoice_id)
    if inv is None:
        raise HTTPException(404, "Invoice not found")
    return inv


def _run_out(ctx: Ctx, run, detail: bool = False):
    live = brepo.run_invoices(ctx.db, ctx.scope, run.id, include_void=False)
    base = dict(
        id=run.id,
        period_start=run.period_start,
        period_end=run.period_end,
        status=run.status,
        created_at=run.created_at,
        reviewed_at=run.reviewed_at,
        finalized_at=run.finalized_at,
        invoice_count=len(live),
        total_cents=sum(i.total_cents for i in live),
        warnings=svc.run_warnings(ctx, run),
    )
    if not detail:
        return RunOut(**base)
    return RunDetailOut(**base, invoices=_outs(ctx, brepo.run_invoices(ctx.db, ctx.scope, run.id)))


# ---- invoices ----
@router.get("/invoices", response_model=Page[InvoiceOut], summary="List invoices")
def list_invoices(
    organization_id: int | None = None,
    status: str | None = None,
    billing_run_id: int | None = None,
    payment_status: str | None = Query(
        None,
        pattern="^(open|overdue|paid|unpaid)$",
        description="Finalized invoices only: open (owes money), overdue, paid, unpaid",
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: Ctx = require(P.BILLING_READ),
):
    items, total = brepo.list_invoices(
        ctx.db,
        ctx.scope,
        org_id=organization_id,
        status=status,
        run_id=billing_run_id,
        limit=limit,
        offset=offset,
        payment_filter=payment_status,
        today=svc.today(ctx),
    )
    return Page(items=_outs(ctx, items), total=total, limit=limit, offset=offset)


@router.post(
    "/invoices",
    response_model=InvoiceDetailOut,
    status_code=201,
    responses=ERR,
    summary="Create a draft invoice (optionally pulling in unbilled time and charges)",
)
def create_invoice(body: InvoiceIn, ctx: Ctx = require(P.BILLING_WRITE)):
    inv = svc.create_invoice(ctx, body.organization_id, body.memo, body.include_unbilled)
    return _detail(ctx, inv)


@router.get(
    "/invoices/{invoice_id}",
    response_model=InvoiceDetailOut,
    responses=ERR,
    summary="Get an invoice with its lines",
)
def get_invoice(invoice_id: int, ctx: Ctx = require(P.BILLING_READ)):
    return _detail(ctx, _invoice_or_404(ctx, invoice_id))


@router.patch(
    "/invoices/{invoice_id}",
    response_model=InvoiceDetailOut,
    responses=ERR,
    summary="Edit a draft invoice's memo",
)
def update_invoice(invoice_id: int, body: InvoicePatch, ctx: Ctx = require(P.BILLING_WRITE)):
    return _detail(ctx, svc.update_invoice(ctx, invoice_id, body.model_dump()))


@router.post(
    "/invoices/{invoice_id}/add-unbilled",
    response_model=InvoiceDetailOut,
    responses=ERR,
    summary="Pull newly logged billable time and charges into a draft",
)
def add_unbilled(invoice_id: int, ctx: Ctx = require(P.BILLING_WRITE)):
    return _detail(ctx, svc.add_unbilled(ctx, invoice_id))


@router.post(
    "/invoices/{invoice_id}/lines",
    response_model=LineOut,
    status_code=201,
    responses=ERR,
    summary="Add a manual line to a draft (use a negative price for a credit)",
)
def add_line(invoice_id: int, body: LineIn, ctx: Ctx = require(P.BILLING_WRITE)):
    return svc.add_manual_line(ctx, invoice_id, body.model_dump())


@router.patch(
    "/invoice-lines/{line_id}",
    response_model=LineOut,
    responses=ERR,
    summary="Adjust a draft line (description, quantity, price, tax rate)",
)
def update_line(line_id: int, body: LinePatch, ctx: Ctx = require(P.BILLING_WRITE)):
    return svc.update_line(ctx, line_id, body.model_dump(exclude_unset=True))


@router.delete(
    "/invoice-lines/{line_id}",
    status_code=204,
    responses=ERR,
    summary="Remove a draft line; its time/charges become billable again",
)
def delete_line(line_id: int, ctx: Ctx = require(P.BILLING_WRITE)):
    svc.delete_line(ctx, line_id)
    return Response(status_code=204)


@router.post(
    "/invoices/{invoice_id}/finalize",
    response_model=InvoiceDetailOut,
    responses=ERR,
    summary="Finalize a draft: assigns the invoice number and freezes it",
)
def finalize_invoice(
    invoice_id: int, body: FinalizeIn | None = None, ctx: Ctx = require(P.BILLING_FINALIZE)
):
    inv = svc.finalize_invoice_by_id(ctx, invoice_id, body.invoice_date if body else None)
    return _detail(ctx, inv)


@router.post(
    "/invoices/{invoice_id}/void",
    response_model=InvoiceDetailOut,
    responses=ERR,
    summary="Void an invoice (reason required if finalized); releases time and charges",
)
def void_invoice(
    invoice_id: int, body: VoidIn | None = None, ctx: Ctx = require(P.BILLING_FINALIZE)
):
    return _detail(ctx, svc.void_invoice(ctx, invoice_id, body.reason if body else None))


@router.get(
    "/invoices/{invoice_id}/pdf",
    response_class=Response,
    responses=ERR,
    summary="Download the invoice as a PDF (drafts are watermarked)",
)
def invoice_pdf(invoice_id: int, ctx: Ctx = require(P.BILLING_READ)):
    inv = _invoice_or_404(ctx, invoice_id)
    lines = brepo.invoice_lines(ctx.db, ctx.scope, inv.id)
    pdf = render_invoice_pdf(inv, lines, repo.get_settings_row(ctx.db))
    name = f"{inv.number or 'DRAFT-' + str(inv.id)}.pdf"
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


# ---- billing runs ----
@router.get("/billing-runs", response_model=list[RunOut], summary="List monthly billing runs")
def list_runs(ctx: Ctx = require(P.BILLING_READ)):
    return [_run_out(ctx, r) for r in brepo.list_runs(ctx.db)]


@router.post(
    "/billing-runs",
    response_model=RunDetailOut,
    status_code=201,
    responses=ERR,
    summary="Start the billing run for a month: builds DRAFT invoices to review",
)
def create_run(body: RunIn, ctx: Ctx = require(P.BILLING_WRITE)):
    return _run_out(ctx, svc.create_run(ctx, body.period), detail=True)


@router.get(
    "/billing-runs/{run_id}",
    response_model=RunDetailOut,
    responses=ERR,
    summary="A billing run with its invoices and warnings",
)
def get_run(run_id: int, ctx: Ctx = require(P.BILLING_READ)):
    run = brepo.get_run(ctx.db, run_id)
    if run is None:
        raise HTTPException(404, "Billing run not found")
    return _run_out(ctx, run, detail=True)


@router.post(
    "/billing-runs/{run_id}/review",
    response_model=RunDetailOut,
    responses=ERR,
    summary="Mark the run reviewed (any later change to its drafts undoes this)",
)
def review_run(run_id: int, ctx: Ctx = require(P.BILLING_FINALIZE)):
    return _run_out(ctx, svc.review_run(ctx, run_id), detail=True)


@router.post(
    "/billing-runs/{run_id}/finalize",
    response_model=RunDetailOut,
    responses=ERR,
    summary="Finalize every invoice in a reviewed run, all-or-nothing",
)
def finalize_run(
    run_id: int, body: FinalizeIn | None = None, ctx: Ctx = require(P.BILLING_FINALIZE)
):
    return _run_out(
        ctx, svc.finalize_run(ctx, run_id, body.invoice_date if body else None), detail=True
    )


@router.post(
    "/billing-runs/{run_id}/cancel",
    response_model=RunDetailOut,
    responses=ERR,
    summary="Cancel a draft/reviewed run: voids its drafts and frees the month",
)
def cancel_run(run_id: int, ctx: Ctx = require(P.BILLING_FINALIZE)):
    return _run_out(ctx, svc.cancel_run(ctx, run_id), detail=True)
