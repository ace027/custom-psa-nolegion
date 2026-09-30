"""Payment queries. Balances are computed from applications and write-offs, never stored."""

from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import Invoice, Payment, PaymentApplication, WriteOff
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


def balance_expr():
    return Invoice.total_cents - applied_expr() - written_off_expr()


def payment_applied_expr():
    return (
        select(func.coalesce(func.sum(PaymentApplication.amount_cents), 0))
        .where(PaymentApplication.payment_id == Payment.id, PaymentApplication.voided_at.is_(None))
        .scalar_subquery()
    )


def amounts_for(db: Session, invoice_ids: list[int]) -> dict[int, tuple[int, int]]:
    """invoice id -> (applied, written_off) for the given invoices."""
    out = {i: (0, 0) for i in invoice_ids}
    if not invoice_ids:
        return out
    apps = db.execute(
        select(PaymentApplication.invoice_id, func.sum(PaymentApplication.amount_cents))
        .where(
            PaymentApplication.invoice_id.in_(invoice_ids), PaymentApplication.voided_at.is_(None)
        )
        .group_by(PaymentApplication.invoice_id)
    )
    for inv_id, total in apps:
        out[inv_id] = (int(total), 0)
    wos = db.execute(
        select(WriteOff.invoice_id, func.sum(WriteOff.amount_cents))
        .where(WriteOff.invoice_id.in_(invoice_ids), WriteOff.voided_at.is_(None))
        .group_by(WriteOff.invoice_id)
    )
    for inv_id, total in wos:
        out[inv_id] = (out[inv_id][0], int(total))
    return out


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
        return stmt.where(applied_expr() + written_off_expr() == 0, Invoice.total_cents > 0)
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
    """Unapplied money per client: active payments minus what has been applied."""
    stmt = scope.apply(
        select(Payment.organization_id, func.sum(Payment.amount_cents - payment_applied_expr()))
        .where(Payment.status == "active")
        .group_by(Payment.organization_id),
        Payment.organization_id,
    )
    return {org: int(total) for org, total in db.execute(stmt) if total and total > 0}


def payment_lookup(db: Session, ids: set[int]) -> dict[int, Payment]:
    if not ids:
        return {}
    rows = db.execute(select(Payment).where(Payment.id.in_(ids))).unique().scalars()
    return {p.id: p for p in rows}
