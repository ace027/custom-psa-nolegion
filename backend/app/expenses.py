"""Expenses and mileage: reimbursable to the person and/or billable to a client.

Amounts are integer cents. `amount_cents` is what it COST (and what the person is reimbursed);
a billable expense is charged at cost plus markup (money.marked_up) by the normal invoice
generation (billing._pull_expenses). Mileage amount = round_half_up(miles x rate), the rate copied
from Settings when the trip is entered. Approval of the timesheet does not gate billing; a
submitted or approved week locks the expense like it locks time. Nothing is deleted: void."""

import hashlib
import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from sqlalchemy import select

from app import audit, timesheets
from app import repositories as repo
from app import ticket_services as tsvc
from app.config import get_settings
from app.deps import Ctx
from app.errors import Conflict, Forbidden, NotFound
from app.models import Expense, ExpenseCategory, ExpenseReceipt, Organization
from app.money import marked_up, round_cents

MAX_RECEIPT_BYTES = 10 * 1024 * 1024
RECEIPT_TYPES = {
    "application/pdf": (b"%PDF-",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/webp": (b"RIFF",),
}


def _own_or_admin(ctx: Ctx, user_id: int) -> None:
    if user_id != ctx.user.id and ctx.user.role != "admin":
        raise Forbidden("You can only change your own expenses")


def mileage_amount(miles: Decimal, rate_cents: int) -> int:
    return round_cents(miles * rate_cents)


def _miles(value) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _category(ctx: Ctx, category_id: int | None) -> ExpenseCategory:
    cat = ctx.db.get(ExpenseCategory, category_id) if category_id else None
    if cat is None or cat.archived_at is not None:
        raise Conflict("Choose an active expense category")
    return cat


def _client_and_ticket(ctx: Ctx, org_id: int | None, ticket_id: int | None):
    """Validate the client/ticket pair. A ticket alone implies its client."""
    if ticket_id is not None:
        ticket = repo.get_ticket(ctx.db, ctx.scope, ticket_id)
        if ticket is None or ticket.organization_id is None:
            raise Conflict("Unknown ticket, or it is not matched to a client")
        if org_id is not None and ticket.organization_id != org_id:
            raise Conflict("That ticket belongs to a different client")
        org_id = ticket.organization_id
    if org_id is not None:
        org = repo.get_organization(ctx.db, ctx.scope, org_id)
        if org is None or org.archived_at is not None:
            raise Conflict("Unknown or archived client")
    return org_id, ticket_id


def _check_flags(e: Expense) -> None:
    if e.billable and e.organization_id is None:
        raise Conflict("A billable expense needs a client")
    if not e.billable and e.markup_bp:
        raise Conflict("Markup only applies to billable expenses")


def _get(ctx: Ctx, expense_id: int) -> Expense:
    e = ctx.db.get(Expense, expense_id)
    if e is None:
        raise NotFound("Expense not found")
    _own_or_admin(ctx, e.user_id)
    return e


def _mutable(ctx: Ctx, e: Expense) -> None:
    if e.voided_at:
        raise Conflict("Voided expenses cannot be changed")
    if e.invoice_line_id is not None:
        raise Conflict("This expense is on an invoice and is locked")
    timesheets.assert_open(ctx, e.user_id, e.expense_date)


def view(ctx: Ctx, e: Expense) -> dict:
    user = repo.get_user(ctx.db, e.user_id)
    org = ctx.db.get(Organization, e.organization_id) if e.organization_id else None
    receipts = ctx.db.execute(
        select(ExpenseReceipt).where(ExpenseReceipt.expense_id == e.id).order_by(ExpenseReceipt.id)
    ).scalars()
    return dict(
        id=e.id,
        user_id=e.user_id,
        user_name=user.display_name if user else f"User {e.user_id}",
        expense_date=e.expense_date,
        kind=e.kind,
        category_id=e.category_id,
        category_name=e.category.name if e.category else None,
        description=e.description,
        miles=e.miles,
        mileage_rate_cents=e.mileage_rate_cents,
        amount_cents=e.amount_cents,
        reimbursable=e.reimbursable,
        billable=e.billable,
        taxable=e.taxable,
        markup_bp=e.markup_bp,
        client_price_cents=marked_up(e.amount_cents, e.markup_bp) if e.billable else 0,
        organization_id=e.organization_id,
        organization_name=org.name if org else None,
        ticket_id=e.ticket_id,
        invoiced=e.invoice_line_id is not None,
        voided_at=e.voided_at,
        receipts=list(receipts),
    )


def create(ctx: Ctx, data: dict) -> Expense:
    user_id = data.get("user_id") or ctx.user.id
    if user_id != ctx.user.id:
        if ctx.user.role != "admin":
            raise Forbidden("Only admins can enter expenses for someone else")
        target = repo.get_user(ctx.db, user_id)
        if target is None or not target.is_active:
            raise Conflict("Unknown or inactive user")
    kind = data.get("kind", "expense")
    fields: dict = dict(miles=None, mileage_rate_cents=None, category_id=None)
    if kind == "mileage":
        if data.get("miles") is None or data.get("amount_cents") is not None:
            raise Conflict("Mileage takes miles, not an amount")
        rate = repo.get_settings_row(ctx.db).mileage_rate_cents
        if rate <= 0:
            raise Conflict("Set the mileage rate in Settings before entering mileage")
        miles = _miles(data["miles"])
        amount = mileage_amount(miles, rate)
        if miles <= 0 or amount <= 0:
            raise Conflict("That trip is worth less than one cent")
        fields.update(miles=miles, mileage_rate_cents=rate)
        if data.get("category_id"):
            fields["category_id"] = _category(ctx, data["category_id"]).id
    else:
        if data.get("amount_cents") is None or data.get("miles") is not None:
            raise Conflict("An expense takes an amount, not miles")
        amount = data["amount_cents"]
        fields["category_id"] = _category(ctx, data.get("category_id")).id
    org_id, ticket_id = _client_and_ticket(ctx, data.get("organization_id"), data.get("ticket_id"))
    day = tsvc._entry_date(ctx, data.get("expense_date"))
    timesheets.assert_open(ctx, user_id, day)
    e = Expense(
        user_id=user_id,
        expense_date=day,
        kind=kind,
        description=data["description"].strip(),
        amount_cents=amount,
        reimbursable=data.get("reimbursable", False),
        billable=data.get("billable", False),
        taxable=data.get("taxable", False),
        markup_bp=data.get("markup_bp", 0),
        organization_id=org_id,
        ticket_id=ticket_id,
        **fields,
    )
    if not e.description:
        raise Conflict("Describe the expense")
    _check_flags(e)
    ctx.db.add(e)
    ctx.db.flush()
    audit.record(
        ctx.db,
        ctx.user,
        "expense.create",
        e,
        after=audit.snapshot(e),
        organization_id=e.organization_id,
    )
    return e


def update(ctx: Ctx, expense_id: int, data: dict) -> Expense:
    e = _get(ctx, expense_id)
    _mutable(ctx, e)
    before = audit.snapshot(e)
    if data.get("expense_date"):
        timesheets.assert_open(ctx, e.user_id, data["expense_date"])
        e.expense_date = data["expense_date"]
    if data.get("description") is not None:
        if not data["description"].strip():
            raise Conflict("Describe the expense")
        e.description = data["description"].strip()
    if data.get("category_id") is not None:
        e.category_id = _category(ctx, data["category_id"]).id
    if e.kind == "mileage":
        if data.get("amount_cents") is not None:
            raise Conflict("A mileage amount comes from the miles and the rate; change the miles")
        if data.get("miles") is not None:
            e.miles = _miles(data["miles"])
            e.amount_cents = mileage_amount(e.miles, e.mileage_rate_cents)  # the rate stays fixed
            if e.amount_cents <= 0:
                raise Conflict("That trip is worth less than one cent")
    else:
        if data.get("miles") is not None:
            raise Conflict("Only mileage has miles")
        if data.get("amount_cents") is not None:
            e.amount_cents = data["amount_cents"]
    for key in ("reimbursable", "billable", "taxable", "markup_bp"):
        if data.get(key) is not None:
            setattr(e, key, data[key])
    if data.get("clear_client"):
        e.organization_id = e.ticket_id = None
    else:
        new_org, new_ticket = data.get("organization_id"), data.get("ticket_id")
        if new_org is not None or new_ticket is not None:
            if new_ticket is None:  # keep the ticket only while it is still this client's
                new_ticket = e.ticket_id if new_org in (None, e.organization_id) else None
            e.organization_id, e.ticket_id = _client_and_ticket(ctx, new_org, new_ticket)
    if data.get("billable") is False and data.get("markup_bp") is None:
        e.markup_bp = 0  # no longer billed: the markup goes with it
    _check_flags(e)
    ctx.db.flush()
    ctx.db.refresh(e)
    audit.record(
        ctx.db,
        ctx.user,
        "expense.update",
        e,
        before=before,
        after=audit.snapshot(e),
        organization_id=e.organization_id,
    )
    return e


def void(ctx: Ctx, expense_id: int) -> Expense:
    e = _get(ctx, expense_id)
    _mutable(ctx, e)
    before = audit.snapshot(e)
    e.voided_at = tsvc.now()
    ctx.db.flush()
    ctx.db.refresh(e)
    audit.record(
        ctx.db,
        ctx.user,
        "expense.void",
        e,
        before=before,
        after=audit.snapshot(e),
        organization_id=e.organization_id,
    )
    return e


def get(ctx: Ctx, expense_id: int) -> Expense:
    return _get(ctx, expense_id)


def listing(
    ctx: Ctx,
    *,
    start: date | None,
    end: date | None,
    user_id: int | None,
    organization_id: int | None,
    include_voided: bool,
) -> list[Expense]:
    target = user_id or ctx.user.id
    if target != ctx.user.id and ctx.user.role != "admin":
        raise Forbidden("Only admins can list someone else's expenses")
    q = select(Expense).where(Expense.user_id == target)
    if start:
        q = q.where(Expense.expense_date >= start)
    if end:
        q = q.where(Expense.expense_date <= end)
    if organization_id:
        q = q.where(Expense.organization_id == organization_id)
    if not include_voided:
        q = q.where(Expense.voided_at.is_(None))
    return list(
        ctx.db.execute(
            q.order_by(Expense.expense_date.desc(), Expense.id.desc()).limit(500)
        ).scalars()
    )


# ---- receipts ---------------------------------------------------------------------------------
def add_receipt(ctx: Ctx, expense_id: int, filename: str, content_type: str, data: bytes):
    e = _get(ctx, expense_id)
    if e.voided_at:
        raise Conflict("Voided expenses cannot take receipts")
    ctype = content_type.split(";")[0].strip().lower()
    if ctype not in RECEIPT_TYPES:
        raise Conflict("Receipts must be a PDF, PNG, JPEG or WebP file")
    if not data:
        raise Conflict("The file is empty")
    if len(data) > MAX_RECEIPT_BYTES:
        raise Conflict("Receipts can be at most 10 MB")
    if not any(data.startswith(sig) for sig in RECEIPT_TYPES[ctype]) or (
        ctype == "image/webp" and data[8:12] != b"WEBP"
    ):
        raise Conflict("The file does not look like a " + ctype.split("/")[1].upper())
    key = f"receipts/{e.id}/{uuid.uuid4().hex}"
    path = Path(get_settings().attachments_dir) / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    r = ExpenseReceipt(
        expense_id=e.id,
        organization_id=e.organization_id,
        filename=(filename or "receipt")[:300],
        content_type=ctype,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        storage_key=key,
        created_by=ctx.user.id,
    )
    ctx.db.add(r)
    ctx.db.flush()
    ctx.db.refresh(r)
    audit.record(
        ctx.db,
        ctx.user,
        "expense.receipt_add",
        e,
        after={"receipt_id": r.id, "filename": r.filename, "size_bytes": r.size_bytes},
        organization_id=e.organization_id,
    )
    return r


def get_receipt(ctx: Ctx, receipt_id: int) -> tuple[ExpenseReceipt, Path]:
    r = ctx.db.get(ExpenseReceipt, receipt_id)
    if r is None:
        raise NotFound("Receipt not found")
    _get(ctx, r.expense_id)  # owner or admin
    base = Path(get_settings().attachments_dir).resolve()
    path = (base / r.storage_key).resolve()
    if base not in path.parents or not path.is_file():  # path-traversal guard
        raise NotFound("Receipt file is missing")
    return r, path


# ---- payroll export ---------------------------------------------------------------------------
def reimbursement_rows(ctx: Ctx, start: date, end: date) -> list[list]:
    """Reimbursable expenses in APPROVED weeks: the cost amount (never the marked-up price)."""
    from sqlalchemy import and_

    from app.models import Timesheet

    if end < start:
        raise Conflict("The end date is before the start date")
    q = (
        select(Expense)
        .join(
            Timesheet,
            and_(
                Timesheet.user_id == Expense.user_id,
                Expense.expense_date >= Timesheet.week_start,
                Expense.expense_date <= Timesheet.week_start + 6,
            ),
        )
        .where(
            Timesheet.status == "approved",
            Expense.reimbursable.is_(True),
            Expense.voided_at.is_(None),
            Expense.expense_date.between(start, end),
        )
    )
    expenses = list(ctx.db.execute(q).scalars())
    users = {x.user_id: repo.get_user(ctx.db, x.user_id) for x in expenses}
    expenses.sort(key=lambda x: (users[x.user_id].display_name.lower(), x.expense_date, x.id))
    return [
        [
            users[x.user_id].display_name,
            users[x.user_id].email,
            x.expense_date,
            "Mileage" if x.kind == "mileage" else (x.category.name if x.category else ""),
            x.description,
            f"{x.miles}" if x.miles is not None else "",
            x.amount_cents,
        ]
        for x in expenses
    ]
