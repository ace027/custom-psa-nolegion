"""Expenses, mileage and receipts."""

import re
from datetime import date

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, Response

from app import expenses as svc
from app import permissions as P
from app import reports as rpt
from app.deps import Ctx, require
from app.schemas import ErrorOut, ExpenseIn, ExpenseOut, ExpensePatch, ReceiptOut

router = APIRouter(tags=["expenses"])
ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}


@router.post(
    "/expenses",
    response_model=ExpenseOut,
    status_code=201,
    responses=ERR,
    summary="Record an expense or a mileage trip (reimbursable and/or billable to a client)",
)
def create_expense(body: ExpenseIn, ctx: Ctx = require(P.TIME_WRITE)):
    return svc.view(ctx, svc.create(ctx, body.model_dump()))


@router.get(
    "/expenses",
    response_model=list[ExpenseOut],
    responses=ERR,
    summary="My expenses, newest first (admins can pass user_id)",
)
def list_expenses(
    start: date | None = Query(None, alias="from"),
    end: date | None = Query(None, alias="to"),
    user_id: int | None = None,
    organization_id: int | None = None,
    include_voided: bool = False,
    ctx: Ctx = require(P.TIME_WRITE),
):
    rows = svc.listing(
        ctx,
        start=start,
        end=end,
        user_id=user_id,
        organization_id=organization_id,
        include_voided=include_voided,
    )
    return [svc.view(ctx, e) for e in rows]


@router.get(
    "/expenses/{expense_id}", response_model=ExpenseOut, responses=ERR, summary="One expense"
)
def get_expense(expense_id: int, ctx: Ctx = require(P.TIME_WRITE)):
    return svc.view(ctx, svc.get(ctx, expense_id))


@router.patch(
    "/expenses/{expense_id}",
    response_model=ExpenseOut,
    responses=ERR,
    summary="Edit an expense (not once it is invoiced or its week is submitted)",
)
def update_expense(expense_id: int, body: ExpensePatch, ctx: Ctx = require(P.TIME_WRITE)):
    return svc.view(ctx, svc.update(ctx, expense_id, body.model_dump(exclude_unset=True)))


@router.post(
    "/expenses/{expense_id}/void",
    response_model=ExpenseOut,
    responses=ERR,
    summary="Void an expense (kept for the audit trail)",
)
def void_expense(expense_id: int, ctx: Ctx = require(P.TIME_WRITE)):
    return svc.view(ctx, svc.void(ctx, expense_id))


@router.post(
    "/expenses/{expense_id}/receipts",
    response_model=ReceiptOut,
    status_code=201,
    responses=ERR,
    summary="Attach a receipt: send the file as the request body with its Content-Type "
    "(PDF, PNG, JPEG or WebP, up to 10 MB) and ?filename=",
)
async def add_receipt(
    expense_id: int,
    request: Request,
    filename: str = Query("receipt", max_length=300),
    ctx: Ctx = require(P.TIME_WRITE),
):
    data = await request.body()
    return svc.add_receipt(ctx, expense_id, filename, request.headers.get("content-type", ""), data)


@router.get(
    "/expense-receipts/{receipt_id}/download",
    response_class=FileResponse,
    responses=ERR,
    summary="Download a receipt (always as a download, never inline)",
)
def download_receipt(receipt_id: int, ctx: Ctx = require(P.TIME_WRITE)):
    r, path = svc.get_receipt(ctx, receipt_id)
    safe = re.sub(r"[^\w.\- ]", "_", r.filename).lstrip(".") or "receipt"
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=safe,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get(
    "/timesheets/expenses.csv",
    responses=ERR,
    summary="Payroll CSV: reimbursable expenses (cost, in dollars) from approved weeks",
)
def reimbursement_csv(
    start: date = Query(alias="from"),
    end: date = Query(alias="to"),
    ctx: Ctx = require(P.TIMESHEET_APPROVE),
):
    rows = svc.reimbursement_rows(ctx, start, end)
    rpt.record_export(ctx, "payroll-expenses", {"from": start, "to": end}, len(rows))
    header = ["Employee", "Email", "Date", "Category", "Description", "Miles", "Reimburse"]
    return Response(
        rpt.to_csv(header, rows, {6}),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="expenses-{start}-{end}.csv"'},
    )
