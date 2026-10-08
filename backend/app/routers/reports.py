"""Billing reports (JSON) and CSV exports. Read-only; CSV downloads are audited."""

from datetime import date

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app import permissions as P
from app import reports as svc
from app.deps import Ctx, require
from app.schemas import ErrorOut, RecurringOut, RevenueOut, UnbilledOut

router = APIRouter(prefix="/reports", tags=["reports"])
ERR = {409: {"model": ErrorOut}}
FROM = Query(None, alias="from", description="Start date (default: 12 months ago)")
TO = Query(None, alias="to", description="End date (default: today, business time zone)")


def _csv(name: str, text: str) -> Response:
    return Response(
        text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get(
    "/revenue",
    response_model=RevenueOut,
    responses=ERR,
    summary="Invoiced revenue by client and by month (finalized invoices, by invoice date)",
)
def revenue(start: date | None = FROM, end: date | None = TO, ctx: Ctx = require(P.REPORT_READ)):
    return svc.revenue(ctx, start, end)


@router.get(
    "/revenue.csv",
    responses=ERR,
    summary="Revenue by client as CSV (dollars)",
)
def revenue_csv(
    start: date | None = FROM, end: date | None = TO, ctx: Ctx = require(P.REPORT_READ)
):
    d = svc.revenue(ctx, start, end)
    header = [
        "client",
        "invoices",
        "time",
        "products",
        "agreements",
        "other",
        "subtotal",
        "tax",
        "total",
    ]
    rows = [
        [
            c["organization_name"],
            c["invoices"],
            c["time_cents"],
            c["product_cents"],
            c["agreement_cents"],
            c["manual_cents"],
            c["subtotal_cents"],
            c["tax_cents"],
            c["total_cents"],
        ]
        for c in d["clients"]
    ]
    svc.record_export(ctx, "revenue", {"from": d["start"], "to": d["end"]}, len(rows))
    return _csv(f"revenue-{d['start']}-{d['end']}.csv", svc.to_csv(header, rows, set(range(2, 9))))


@router.get(
    "/unbilled",
    response_model=UnbilledOut,
    summary="Billable time and one-off charges not yet invoiced, by client",
)
def unbilled(through: date | None = Query(None), ctx: Ctx = require(P.REPORT_READ)):
    return svc.unbilled(ctx, through)


@router.get("/unbilled.csv", summary="Unbilled work by client as CSV (dollars)")
def unbilled_csv(through: date | None = Query(None), ctx: Ctx = require(P.REPORT_READ)):
    d = svc.unbilled(ctx, through)
    header = [
        "client",
        "time_entries",
        "billable_hours",
        "time_value",
        "unpriced_hours",
        "oldest",
        "charges",
        "charges_value",
        "expenses",
        "expenses_value",
        "total",
    ]
    rows = [
        [
            r["organization_name"],
            r["time_entries"],
            f"{r['billable_minutes'] / 60:.2f}",
            r["time_value_cents"],
            f"{r['unpriced_minutes'] / 60:.2f}",
            r["oldest_work_date"],
            r["charges"],
            r["charges_cents"],
            r["expenses"],
            r["expenses_cents"],
            r["total_cents"],
        ]
        for r in d["rows"]
    ]
    svc.record_export(ctx, "unbilled", {"through": d["through"]}, len(rows))
    return _csv(f"unbilled-{d['through']}.csv", svc.to_csv(header, rows, {3, 7, 9, 10}))


@router.get(
    "/recurring",
    response_model=RecurringOut,
    responses=ERR,
    summary="Agreement revenue per month: contracted (current terms) vs actually invoiced",
)
def recurring(months: int = Query(12), ctx: Ctx = require(P.REPORT_READ)):
    return svc.recurring(ctx, months)


@router.get("/recurring.csv", responses=ERR, summary="Recurring revenue trend as CSV (dollars)")
def recurring_csv(months: int = Query(12), ctx: Ctx = require(P.REPORT_READ)):
    d = svc.recurring(ctx, months)
    header = ["month", "contracted", "agreements", "clients", "invoiced"]
    rows = [
        [m["month"], m["contracted_cents"], m["agreements"], m["clients"], m["invoiced_cents"]]
        for m in d["months"]
    ]
    svc.record_export(ctx, "recurring", {"months": months}, len(rows))
    return _csv("recurring-revenue.csv", svc.to_csv(header, rows, {1, 4}))


@router.get(
    "/invoices.csv",
    responses=ERR,
    summary="Every finalized or voided invoice in a date range, for your accountant (CSV, dollars)",
)
def invoices_csv(
    start: date | None = FROM, end: date | None = TO, ctx: Ctx = require(P.REPORT_READ)
):
    rows = svc.invoice_rows(ctx, start, end)
    lo, hi = svc.default_range(ctx, start, end)
    header = [
        "number",
        "client",
        "status",
        "invoice_date",
        "due_date",
        "subtotal",
        "tax",
        "total",
        "paid",
        "written_off",
        "credited",
        "balance",
        "payment_status",
        "void_reason",
    ]
    keys = [
        "number",
        "client",
        "status",
        "invoice_date",
        "due_date",
        "subtotal_cents",
        "tax_cents",
        "total_cents",
        "paid_cents",
        "written_off_cents",
        "credited_cents",
        "balance_cents",
        "payment_status",
        "void_reason",
    ]
    svc.record_export(ctx, "invoices", {"from": lo, "to": hi}, len(rows))
    return _csv(
        f"invoices-{lo}-{hi}.csv",
        svc.to_csv(header, [[r[k] for k in keys] for r in rows], {5, 6, 7, 8, 9, 10, 11}),
    )
