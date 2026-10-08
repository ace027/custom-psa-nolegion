"""Payment queries. Balances are computed from applications and write-offs, never stored."""

from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import (
    CreditMemo,
    CreditMemoApplication,
    CreditMemoLine,
    Invoice,
    Payment,
    PaymentApplication,
    Refund,
    WriteOff,
)
from app.scope import Scope


# ---- derived amounts as correlated subqueries (usable in WHERE and ORDER BY) ----
def applied_expr():
    return (
        select(func.coalesce(func.sum(PaymentApplication.amount_cents), 0))
        .where(PaymentApplication.invoice_id == Invoice.id, PaymentApplication.voided_at.is_(None))
        .scalar_subquery()
    )


def written_off_expr():
    return (
        select(func.coalesce(func.sum(WriteOff.amount_cents), 0))
        .where(WriteOff.invoice_id == Invoice.id, WriteOff.voided_at.is_(None))
        .scalar_subquery()
    )


def credited_expr():
    return (
        select(func.coalesce(func.sum(CreditMemoApplication.amount_cents), 0))
        .where(
            CreditMemoApplication.invoice_id == Invoice.id,
            CreditMemoApplication.voided_at.is_(None),
        )
        .scalar_subquery()
    )


def balance_expr():
    return Invoice.total_cents - applied_expr() - written_off_expr() - credited_expr()


def payment_applied_expr():
    return (
        select(func.coalesce(func.sum(PaymentApplication.amount_cents), 0))
        .where(PaymentApplication.payment_id == Payment.id, PaymentApplication.voided_at.is_(None))
        .scalar_subquery()
    )


def amounts_for(db: Session, invoice_ids: list[int]) -> dict[int, tuple[int, int, int]]:
    """invoice id -> (applied, written_off, credited) for the given invoices.
    Balance = total - sum of the three. `credited` is credit memo applications."""
    out = {i: [0, 0, 0] for i in invoice_ids}
    if not invoice_ids:
        return {}
    for slot, model in enumerate((PaymentApplication, WriteOff, CreditMemoApplication)):
        rows = db.execute(
            select(model.invoice_id, func.sum(model.amount_cents))
            .where(model.invoice_id.in_(invoice_ids), model.voided_at.is_(None))
            .group_by(model.invoice_id)
        )
        for inv_id, total in rows:
            out[inv_id][slot] = int(total)
    return {k: (v[0], v[1], v[2]) for k, v in out.items()}


def filter_invoices(stmt: Select, payment_filter: str | None, today: date) -> Select:
    """payment_filter: open (owes money), overdue, paid (balance 0), unpaid (nothing received)."""
    if not payment_filter:
        return stmt
    stmt = stmt.where(Invoice.status == "final")
    if payment_filter == "open":
        return stmt.where(balance_expr() > 0)
    if payment_filter == "overdue":
        return stmt.where(balance_expr() > 0, Invoice.due_date < today)
    if payment_filter == "paid":
        return stmt.where(balance_expr() <= 0)
    if payment_filter == "unpaid":
        return stmt.where(
            applied_expr() + written_off_expr() + credited_expr() == 0, Invoice.total_cents > 0
        )
    raise ValueError(payment_filter)


def open_invoices(db: Session, scope: Scope, org_id: int | None = None):
    stmt = scope.apply(select(Invoice), Invoice.organization_id).where(
        Invoice.status == "final", balance_expr() > 0
    )
    if org_id is not None:
        stmt = stmt.where(Invoice.organization_id == org_id)
    return list(db.execute(stmt.order_by(Invoice.due_date, Invoice.id)).unique().scalars())


# ---- payments ----
def get_payment(db: Session, scope: Scope, payment_id: int, lock: bool = False):
    stmt = scope.apply(select(Payment).where(Payment.id == payment_id), Payment.organization_id)
    if lock:
        stmt = stmt.with_for_update(of=Payment)
    return db.execute(stmt).unique().scalar_one_or_none()


def list_payments(db: Session, scope: Scope, *, org_id, status, limit, offset):
    stmt = scope.apply(select(Payment), Payment.organization_id)
    if org_id is not None:
        stmt = stmt.where(Payment.organization_id == org_id)
    if status:
        stmt = stmt.where(Payment.status == status)
    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = db.execute(
        stmt.order_by(Payment.received_on.desc(), Payment.id.desc()).limit(limit).offset(offset)
    )
    return list(rows.unique().scalars()), total


def refunded_expr():
    return (
        select(func.coalesce(func.sum(Refund.amount_cents), 0))
        .where(Refund.payment_id == Payment.id, Refund.voided_at.is_(None))
        .scalar_subquery()
    )


def refunded_by_payment(db: Session, payment_ids: list[int]) -> dict[int, int]:
    out = {i: 0 for i in payment_ids}
    if payment_ids:
        rows = db.execute(
            select(Refund.payment_id, func.sum(Refund.amount_cents))
            .where(Refund.payment_id.in_(payment_ids), Refund.voided_at.is_(None))
            .group_by(Refund.payment_id)
        )
        for pid, total in rows:
            out[pid] = int(total)
    return out


def applied_by_payment(db: Session, payment_ids: list[int]) -> dict[int, int]:
    out = {i: 0 for i in payment_ids}
    if payment_ids:
        rows = db.execute(
            select(PaymentApplication.payment_id, func.sum(PaymentApplication.amount_cents))
            .where(
                PaymentApplication.payment_id.in_(payment_ids),
                PaymentApplication.voided_at.is_(None),
            )
            .group_by(PaymentApplication.payment_id)
        )
        for pid, total in rows:
            out[pid] = int(total)
    return out


def applications_for_payment(db: Session, scope: Scope, payment_id: int, active_only=False):
    stmt = scope.apply(
        select(PaymentApplication).where(PaymentApplication.payment_id == payment_id),
        PaymentApplication.organization_id,
    )
    if active_only:
        stmt = stmt.where(PaymentApplication.voided_at.is_(None))
    return list(db.execute(stmt.order_by(PaymentApplication.id)).scalars())


def applications_for_invoice(db: Session, scope: Scope, invoice_id: int):
    stmt = scope.apply(
        select(PaymentApplication).where(PaymentApplication.invoice_id == invoice_id),
        PaymentApplication.organization_id,
    )
    return list(db.execute(stmt.order_by(PaymentApplication.id)).scalars())


def get_application(db: Session, scope: Scope, app_id: int, lock: bool = False):
    stmt = scope.apply(
        select(PaymentApplication).where(PaymentApplication.id == app_id),
        PaymentApplication.organization_id,
    )
    if lock:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def writeoffs_for_invoice(db: Session, scope: Scope, invoice_id: int):
    stmt = scope.apply(
        select(WriteOff).where(WriteOff.invoice_id == invoice_id), WriteOff.organization_id
    )
    return list(db.execute(stmt.order_by(WriteOff.id)).scalars())


def get_write_off(db: Session, scope: Scope, wo_id: int):
    stmt = scope.apply(select(WriteOff).where(WriteOff.id == wo_id), WriteOff.organization_id)
    return db.execute(stmt).scalar_one_or_none()


def credit_by_org(db: Session, scope: Scope) -> dict[int, int]:
    """Unused money per client: unapplied, unrefunded payments plus unapplied credit memos."""
    out: dict[int, int] = {}
    pay = scope.apply(
        select(
            Payment.organization_id,
            func.sum(Payment.amount_cents - payment_applied_expr() - refunded_expr()),
        )
        .where(Payment.status == "active")
        .group_by(Payment.organization_id),
        Payment.organization_id,
    )
    for org, total in db.execute(pay):
        out[org] = out.get(org, 0) + int(total or 0)
    memo = scope.apply(
        select(
            CreditMemo.organization_id,
            func.sum(CreditMemo.total_cents - memo_applied_expr()),
        )
        .where(CreditMemo.status == "active")
        .group_by(CreditMemo.organization_id),
        CreditMemo.organization_id,
    )
    for org, total in db.execute(memo):
        out[org] = out.get(org, 0) + int(total or 0)
    return {org: total for org, total in out.items() if total > 0}


def memo_applied_expr():
    return (
        select(func.coalesce(func.sum(CreditMemoApplication.amount_cents), 0))
        .where(
            CreditMemoApplication.memo_id == CreditMemo.id,
            CreditMemoApplication.voided_at.is_(None),
        )
        .scalar_subquery()
    )


# ---- credit memos and refunds ----
def get_memo(db: Session, scope: Scope, memo_id: int, lock: bool = False):
    stmt = scope.apply(
        select(CreditMemo).where(CreditMemo.id == memo_id), CreditMemo.organization_id
    )
    if lock:
        stmt = stmt.with_for_update(of=CreditMemo)
    return db.execute(stmt).unique().scalar_one_or_none()


def list_memos(db: Session, scope: Scope, *, org_id, status, limit, offset):
    stmt = scope.apply(select(CreditMemo), CreditMemo.organization_id)
    if org_id is not None:
        stmt = stmt.where(CreditMemo.organization_id == org_id)
    if status:
        stmt = stmt.where(CreditMemo.status == status)
    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = db.execute(stmt.order_by(CreditMemo.id.desc()).limit(limit).offset(offset))
    return list(rows.unique().scalars()), total


def memo_lines(db: Session, scope: Scope, memo_id: int):
    stmt = scope.apply(
        select(CreditMemoLine).where(CreditMemoLine.memo_id == memo_id),
        CreditMemoLine.organization_id,
    )
    return list(db.execute(stmt.order_by(CreditMemoLine.position)).scalars())


def memo_applications(db: Session, scope: Scope, memo_id: int, active_only=False):
    stmt = scope.apply(
        select(CreditMemoApplication).where(CreditMemoApplication.memo_id == memo_id),
        CreditMemoApplication.organization_id,
    )
    if active_only:
        stmt = stmt.where(CreditMemoApplication.voided_at.is_(None))
    return list(db.execute(stmt.order_by(CreditMemoApplication.id)).scalars())


def memo_applications_for_invoice(db: Session, scope: Scope, invoice_id: int):
    stmt = scope.apply(
        select(CreditMemoApplication).where(CreditMemoApplication.invoice_id == invoice_id),
        CreditMemoApplication.organization_id,
    )
    return list(db.execute(stmt.order_by(CreditMemoApplication.id)).scalars())


def get_memo_application(db: Session, scope: Scope, app_id: int, lock: bool = False):
    stmt = scope.apply(
        select(CreditMemoApplication).where(CreditMemoApplication.id == app_id),
        CreditMemoApplication.organization_id,
    )
    if lock:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def memo_applied(db: Session, memo_ids: list[int]) -> dict[int, int]:
    out = {i: 0 for i in memo_ids}
    if memo_ids:
        rows = db.execute(
            select(CreditMemoApplication.memo_id, func.sum(CreditMemoApplication.amount_cents))
            .where(
                CreditMemoApplication.memo_id.in_(memo_ids),
                CreditMemoApplication.voided_at.is_(None),
            )
            .group_by(CreditMemoApplication.memo_id)
        )
        for mid, total in rows:
            out[mid] = int(total)
    return out


def get_refund(db: Session, scope: Scope, refund_id: int):
    stmt = scope.apply(select(Refund).where(Refund.id == refund_id), Refund.organization_id)
    return db.execute(stmt).scalar_one_or_none()


def refunds_for_payment(db: Session, scope: Scope, payment_id: int, active_only=False):
    stmt = scope.apply(
        select(Refund).where(Refund.payment_id == payment_id), Refund.organization_id
    )
    if active_only:
        stmt = stmt.where(Refund.voided_at.is_(None))
    return list(db.execute(stmt.order_by(Refund.id)).scalars())


def payment_lookup(db: Session, ids: set[int]) -> dict[int, Payment]:
    if not ids:
        return {}
    rows = db.execute(select(Payment).where(Payment.id.in_(ids))).unique().scalars()
    return {p.id: p for p in rows}
