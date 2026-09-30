"""Queries for contracts and invoicing. Client-owned data always goes through Scope."""

from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Agreement,
    AgreementQuantityLog,
    BillingRun,
    Invoice,
    InvoiceLine,
    Organization,
    OrgWorkTypeRate,
    Product,
    ProductCharge,
    Ticket,
    TimeEntry,
    WorkType,
)
from app.scope import Scope


# ---- products / rates ----
def list_products(db: Session, include_archived: bool):
    stmt = select(Product)
    if not include_archived:
        stmt = stmt.where(Product.archived_at.is_(None))
    return list(db.execute(stmt.order_by(func.lower(Product.name), Product.id)).scalars())


def list_work_types(db: Session):
    return list(db.execute(select(WorkType).order_by(func.lower(WorkType.name))).scalars())


def list_org_rates(db: Session, scope: Scope, org_id: int):
    stmt = scope.apply(
        select(OrgWorkTypeRate).where(OrgWorkTypeRate.organization_id == org_id),
        OrgWorkTypeRate.organization_id,
    )
    return list(db.execute(stmt.order_by(OrgWorkTypeRate.work_type_id)).scalars())


def get_org_rate(db: Session, scope: Scope, org_id: int, work_type_id: int):
    stmt = scope.apply(
        select(OrgWorkTypeRate).where(
            OrgWorkTypeRate.organization_id == org_id, OrgWorkTypeRate.work_type_id == work_type_id
        ),
        OrgWorkTypeRate.organization_id,
    )
    return db.execute(stmt).scalar_one_or_none()


# ---- agreements ----
def list_agreements(db: Session, scope: Scope, *, org_id, active_on: date | None):
    stmt = scope.apply(select(Agreement), Agreement.organization_id)
    if org_id is not None:
        stmt = stmt.where(Agreement.organization_id == org_id)
    if active_on is not None:
        stmt = stmt.where(
            Agreement.start_date <= active_on,
            or_(Agreement.end_date.is_(None), Agreement.end_date >= active_on),
        )
    return list(
        db.execute(stmt.order_by(Agreement.organization_id, Agreement.id)).unique().scalars()
    )


def get_agreement(db: Session, scope: Scope, agreement_id: int) -> Agreement | None:
    stmt = scope.apply(
        select(Agreement).where(Agreement.id == agreement_id), Agreement.organization_id
    )
    return db.execute(stmt).unique().scalar_one_or_none()


def agreements_overlapping(db: Session, scope: Scope, org_id: int, start: date, end: date):
    stmt = scope.apply(
        select(Agreement).where(
            Agreement.organization_id == org_id,
            Agreement.start_date <= end,
            or_(Agreement.end_date.is_(None), Agreement.end_date >= start),
        ),
        Agreement.organization_id,
    )
    return list(db.execute(stmt.order_by(Agreement.id)).unique().scalars())


def quantity_log(db: Session, scope: Scope, agreement_id: int):
    stmt = scope.apply(
        select(AgreementQuantityLog).where(AgreementQuantityLog.agreement_id == agreement_id),
        AgreementQuantityLog.organization_id,
    )
    return list(db.execute(stmt.order_by(AgreementQuantityLog.id.desc())).scalars())


# ---- charges ----
def list_charges(db: Session, scope: Scope, *, org_id, ticket_id, unbilled_only: bool):
    stmt = scope.apply(select(ProductCharge), ProductCharge.organization_id)
    if org_id is not None:
        stmt = stmt.where(ProductCharge.organization_id == org_id)
    if ticket_id is not None:
        stmt = stmt.where(ProductCharge.ticket_id == ticket_id)
    if unbilled_only:
        stmt = stmt.where(
            ProductCharge.invoice_line_id.is_(None), ProductCharge.voided_at.is_(None)
        )
    return list(db.execute(stmt.order_by(ProductCharge.id.desc())).scalars())


def get_charge(db: Session, scope: Scope, charge_id: int) -> ProductCharge | None:
    stmt = scope.apply(
        select(ProductCharge).where(ProductCharge.id == charge_id), ProductCharge.organization_id
    )
    return db.execute(stmt).scalar_one_or_none()


def unbilled_charges(db: Session, scope: Scope, org_id: int, through: date):
    stmt = scope.apply(
        select(ProductCharge).where(
            ProductCharge.organization_id == org_id,
            ProductCharge.invoice_line_id.is_(None),
            ProductCharge.voided_at.is_(None),
            ProductCharge.charged_on <= through,
        ),
        ProductCharge.organization_id,
    ).with_for_update()
    return list(db.execute(stmt.order_by(ProductCharge.charged_on, ProductCharge.id)).scalars())


# ---- time ----
def unbilled_time(db: Session, scope: Scope, org_id: int, through: date):
    """Billable, non-voided, not-yet-invoiced entries. FOR UPDATE: two people generating
    invoices at once cannot both pick up the same entries."""
    stmt = scope.apply(
        select(TimeEntry).where(
            TimeEntry.organization_id == org_id,
            TimeEntry.billable.is_(True),
            TimeEntry.voided_at.is_(None),
            TimeEntry.invoice_line_id.is_(None),
            TimeEntry.minutes_billable > 0,
            TimeEntry.work_date <= through,
        ),
        TimeEntry.organization_id,
    ).with_for_update()
    return list(
        db.execute(
            stmt.order_by(TimeEntry.ticket_id, TimeEntry.work_type_id, TimeEntry.id)
        ).scalars()
    )


def tickets_by_id(db: Session, scope: Scope, ids: set[int]) -> dict[int, Ticket]:
    if not ids:
        return {}
    stmt = scope.apply(select(Ticket).where(Ticket.id.in_(ids)), Ticket.organization_id)
    return {t.id: t for t in db.execute(stmt).unique().scalars()}


def orgs_with_billables(db: Session, scope: Scope, start: date, end: date) -> list[Organization]:
    """Organizations that could appear on a run: active agreement, or unbilled time/charges."""
    ids: set[int] = set()
    ids |= {
        a.organization_id
        for a in list_agreements(db, scope, org_id=None, active_on=None)
        if a.start_date <= end and (a.end_date is None or a.end_date >= start)
    }
    t = scope.apply(
        select(TimeEntry.organization_id).where(
            TimeEntry.billable.is_(True),
            TimeEntry.voided_at.is_(None),
            TimeEntry.invoice_line_id.is_(None),
            TimeEntry.minutes_billable > 0,
            TimeEntry.work_date <= end,
        ),
        TimeEntry.organization_id,
    ).distinct()
    ids |= {r[0] for r in db.execute(t)}
    c = scope.apply(
        select(ProductCharge.organization_id).where(
            ProductCharge.invoice_line_id.is_(None),
            ProductCharge.voided_at.is_(None),
            ProductCharge.charged_on <= end,
        ),
        ProductCharge.organization_id,
    ).distinct()
    ids |= {r[0] for r in db.execute(c)}
    if not ids:
        return []
    stmt = select(Organization).where(Organization.id.in_(ids))
    return list(db.execute(stmt.order_by(func.lower(Organization.name))).scalars())


# ---- invoices ----
def get_invoice(db: Session, scope: Scope, invoice_id: int, lock: bool = False):
    stmt = scope.apply(select(Invoice).where(Invoice.id == invoice_id), Invoice.organization_id)
    if lock:
        stmt = stmt.with_for_update(of=Invoice)
    return db.execute(stmt).unique().scalar_one_or_none()


def list_invoices(db: Session, scope: Scope, *, org_id, status, run_id, limit, offset):
    stmt = scope.apply(select(Invoice), Invoice.organization_id)
    if org_id is not None:
        stmt = stmt.where(Invoice.organization_id == org_id)
    if status:
        stmt = stmt.where(Invoice.status == status)
    if run_id is not None:
        stmt = stmt.where(Invoice.billing_run_id == run_id)
    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = db.execute(stmt.order_by(Invoice.id.desc()).limit(limit).offset(offset))
    return list(rows.unique().scalars()), total


def invoice_lines(db: Session, scope: Scope, invoice_id: int):
    stmt = scope.apply(
        select(InvoiceLine).where(InvoiceLine.invoice_id == invoice_id), InvoiceLine.organization_id
    )
    return list(db.execute(stmt.order_by(InvoiceLine.position, InvoiceLine.id)).scalars())


def get_line(db: Session, scope: Scope, line_id: int) -> InvoiceLine | None:
    stmt = scope.apply(
        select(InvoiceLine).where(InvoiceLine.id == line_id), InvoiceLine.organization_id
    )
    return db.execute(stmt).scalar_one_or_none()


# ---- runs ----
def list_runs(db: Session):
    return list(
        db.execute(
            select(BillingRun).order_by(BillingRun.period_start.desc(), BillingRun.id.desc())
        ).scalars()
    )


def get_run(db: Session, run_id: int, lock: bool = False) -> BillingRun | None:
    stmt = select(BillingRun).where(BillingRun.id == run_id)
    if lock:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def live_run_for_period(db: Session, start: date) -> BillingRun | None:
    return db.execute(
        select(BillingRun).where(BillingRun.period_start == start, BillingRun.status != "cancelled")
    ).scalar_one_or_none()


def run_invoices(db: Session, scope: Scope, run_id: int, include_void: bool = True):
    stmt = scope.apply(
        select(Invoice).where(Invoice.billing_run_id == run_id), Invoice.organization_id
    )
    if not include_void:
        stmt = stmt.where(Invoice.status != "void")
    return list(db.execute(stmt.order_by(Invoice.id)).unique().scalars())
