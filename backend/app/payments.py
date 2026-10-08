"""Payment tracking rules.

* An invoice's balance is DERIVED: total - active applications - active write-offs.
* Payments, applications and write-offs are never edited or deleted, only VOIDED with a reason.
* Money can only be applied to finalized invoices, never beyond the invoice balance or the
  payment amount, and never across clients. These rules are enforced by database triggers as
  well as here (the triggers also serialize concurrent applications).
"""

from datetime import date

from sqlalchemy.exc import DBAPIError

from app import audit
from app import billing_repo as brepo
from app import payment_repo as prepo
from app import repositories as repo
from app.billing import today
from app.deps import Ctx
from app.errors import Conflict, NotFound
from app.models import Invoice, Payment, PaymentApplication, WriteOff
from app.ticket_services import now


def _flush(ctx: Ctx) -> None:
    """Flush; a money-rule violation raised by a database trigger becomes a friendly 409."""
    try:
        ctx.db.flush()
    except DBAPIError as exc:
        state = getattr(getattr(exc.orig, "diag", None), "sqlstate", None)
        ctx.db.rollback()
        if state == "P0001":  # RAISE EXCEPTION in our guards
            raise Conflict(str(exc.orig).splitlines()[0]) from exc
        raise


def payment_state(inv: Invoice, applied: int, written_off: int, credited: int, on: date) -> dict:
    """Derived payment fields for an invoice (all None for drafts and voided invoices)."""
    if inv.status != "final":
        return dict(
            paid_cents=None,
            written_off_cents=None,
            credited_cents=None,
            balance_cents=None,
            payment_status=None,
            is_overdue=False,
            days_past_due=0,
        )
    balance = inv.total_cents - applied - written_off - credited
    if balance > 0:
        status = "partial" if applied + written_off + credited > 0 else "unpaid"
    else:
        status = "written_off" if written_off > 0 else "paid"
    overdue = balance > 0 and inv.due_date is not None and inv.due_date < on
    return dict(
        paid_cents=applied,
        written_off_cents=written_off,
        credited_cents=credited,
        balance_cents=balance,
        payment_status=status,
        is_overdue=overdue,
        days_past_due=(on - inv.due_date).days if overdue else 0,
    )


def _final_invoice(ctx: Ctx, invoice_id: int, org_id: int | None = None) -> Invoice:
    inv = brepo.get_invoice(ctx.db, ctx.scope, invoice_id, lock=True)
    if inv is None:
        raise NotFound(f"Invoice {invoice_id} not found")
    if inv.status != "final":
        raise Conflict(
            "Payments can only be applied to finalized invoices "
            f"({inv.number or 'draft #' + str(inv.id)} is {inv.status})"
        )
    if org_id is not None and inv.organization_id != org_id:
        raise Conflict(f"Invoice {inv.number} belongs to a different client")
    return inv


def _balance(ctx: Ctx, inv: Invoice) -> int:
    return inv.total_cents - sum(prepo.amounts_for(ctx.db, [inv.id])[inv.id])


def _require_reason(reason: str | None) -> str:
    if not reason or len(reason.strip()) < 3:
        raise Conflict("A reason is required")
    return reason.strip()


def _apply(ctx: Ctx, payment: Payment, inv: Invoice, amount: int) -> PaymentApplication:
    application = PaymentApplication(
        payment_id=payment.id,
        invoice_id=inv.id,
        organization_id=inv.organization_id,
        amount_cents=amount,
        created_by=ctx.user.id if ctx.user else None,
    )
    ctx.db.add(application)
    _flush(ctx)
    audit.record(
        ctx.db,
        ctx.user,
        "payment.apply",
        application,
        after=audit.snapshot(application),
        organization_id=inv.organization_id,
        detail={"invoice": inv.number, "payment_id": payment.id},
    )
    return application


def create_payment(ctx: Ctx, data: dict) -> Payment:
    org = repo.get_organization(ctx.db, ctx.scope, data["organization_id"])
    if org is None:
        raise NotFound("Organization not found")
    received = data.get("received_on") or today(ctx)
    if received > today(ctx):
        raise Conflict("A payment cannot be dated in the future")
    applications = data.get("applications") or []
    if len({a["invoice_id"] for a in applications}) != len(applications):
        raise Conflict("List each invoice only once")
    if sum(a["amount_cents"] for a in applications) > data["amount_cents"]:
        raise Conflict("The amounts applied to invoices exceed the payment")
    # lock invoices in id order (consistent order = no deadlocks), then validate balances
    locked = {
        a["invoice_id"]: _final_invoice(ctx, a["invoice_id"], org.id)
        for a in sorted(applications, key=lambda a: a["invoice_id"])
    }
    for a in applications:
        inv = locked[a["invoice_id"]]
        if a["amount_cents"] > _balance(ctx, inv):
            raise Conflict(f"Invoice {inv.number} only has a balance of {_balance(ctx, inv)} cents")
    payment = Payment(
        organization_id=org.id,
        amount_cents=data["amount_cents"],
        received_on=received,
        method=data["method"],
        reference=data.get("reference"),
        notes=data.get("notes"),
        created_by=ctx.user.id if ctx.user else None,
    )
    ctx.db.add(payment)
    _flush(ctx)
    ctx.db.refresh(payment)
    audit.record(
        ctx.db,
        ctx.user,
        "payment.create",
        payment,
        after=audit.snapshot(payment),
        organization_id=org.id,
        detail={
            "applied": [
                {"invoice_id": a["invoice_id"], "amount_cents": a["amount_cents"]}
                for a in applications
            ]
        },
    )
    for a in sorted(applications, key=lambda a: a["invoice_id"]):
        _apply(ctx, payment, locked[a["invoice_id"]], a["amount_cents"])
    return payment


def apply_payment(ctx: Ctx, payment_id: int, invoice_id: int, amount: int) -> PaymentApplication:
    peek = prepo.get_payment(ctx.db, ctx.scope, payment_id)
    if peek is None:
        raise NotFound("Payment not found")
    inv = _final_invoice(ctx, invoice_id, peek.organization_id)  # invoice lock first...
    payment = prepo.get_payment(ctx.db, ctx.scope, payment_id, lock=True)  # ...then payment
    if payment.status != "active":
        raise Conflict("A voided payment cannot be applied")
    credit = (
        payment.amount_cents
        - prepo.applied_by_payment(ctx.db, [payment.id])[payment.id]
        - prepo.refunded_by_payment(ctx.db, [payment.id])[payment.id]
    )
    if amount > credit:
        raise Conflict(f"Only {credit} cents of this payment are unapplied")
    if amount > _balance(ctx, inv):
        raise Conflict(f"Invoice {inv.number} only has a balance of {_balance(ctx, inv)} cents")
    return _apply(ctx, payment, inv, amount)


def void_application(ctx: Ctx, application_id: int, reason: str | None) -> PaymentApplication:
    reason = _require_reason(reason)
    application = prepo.get_application(ctx.db, ctx.scope, application_id, lock=True)
    if application is None:
        raise NotFound("Payment application not found")
    if application.voided_at:
        raise Conflict("Already voided")
    before = audit.snapshot(application)
    application.voided_at, application.void_reason = now(), reason
    application.voided_by = ctx.user.id if ctx.user else None
    _flush(ctx)
    ctx.db.refresh(application)
    audit.record(
        ctx.db,
        ctx.user,
        "payment.unapply",
        application,
        before=before,
        after=audit.snapshot(application),
        organization_id=application.organization_id,
        detail={"reason": reason},
    )
    return application


def void_payment(ctx: Ctx, payment_id: int, reason: str | None) -> Payment:
    reason = _require_reason(reason)
    payment = prepo.get_payment(ctx.db, ctx.scope, payment_id, lock=True)
    if payment is None:
        raise NotFound("Payment not found")
    if payment.status == "void":
        raise Conflict("Already voided")
    before = audit.snapshot(payment)
    active = prepo.applications_for_payment(ctx.db, ctx.scope, payment.id, active_only=True)
    for application in active:  # the invoices it paid become open again
        application.voided_at, application.void_reason = now(), f"Payment voided: {reason}"
        application.voided_by = ctx.user.id if ctx.user else None
    ctx.db.flush()
    payment.status, payment.voided_at, payment.void_reason = "void", now(), reason
    payment.voided_by = ctx.user.id if ctx.user else None
    _flush(ctx)
    ctx.db.refresh(payment)
    audit.record(
        ctx.db,
        ctx.user,
        "payment.void",
        payment,
        before=before,
        after=audit.snapshot(payment),
        organization_id=payment.organization_id,
        detail={"reason": reason, "unapplied_invoices": [a.invoice_id for a in active]},
    )
    return payment


def write_off(ctx: Ctx, invoice_id: int, amount: int | None, reason: str | None) -> WriteOff:
    reason = _require_reason(reason)
    inv = _final_invoice(ctx, invoice_id)
    balance = _balance(ctx, inv)
    if balance <= 0:
        raise Conflict("This invoice has no balance to write off")
    amount = balance if amount is None else amount
    if amount > balance:
        raise Conflict(f"Cannot write off more than the balance ({balance} cents)")
    wo = WriteOff(
        invoice_id=inv.id,
        organization_id=inv.organization_id,
        amount_cents=amount,
        reason=reason,
        created_by=ctx.user.id if ctx.user else None,
    )
    ctx.db.add(wo)
    _flush(ctx)
    ctx.db.refresh(wo)
    audit.record(
        ctx.db,
        ctx.user,
        "invoice.write_off",
        wo,
        after=audit.snapshot(wo),
        organization_id=inv.organization_id,
        detail={"invoice": inv.number, "reason": reason},
    )
    return wo


def void_write_off(ctx: Ctx, write_off_id: int, reason: str | None) -> WriteOff:
    reason = _require_reason(reason)
    wo = prepo.get_write_off(ctx.db, ctx.scope, write_off_id)
    if wo is None:
        raise NotFound("Write-off not found")
    if wo.voided_at:
        raise Conflict("Already voided")
    before = audit.snapshot(wo)
    wo.voided_at, wo.void_reason = now(), reason
    wo.voided_by = ctx.user.id if ctx.user else None
    _flush(ctx)
    ctx.db.refresh(wo)
    audit.record(
        ctx.db,
        ctx.user,
        "invoice.write_off_void",
        wo,
        before=before,
        after=audit.snapshot(wo),
        organization_id=wo.organization_id,
        detail={"reason": reason},
    )
    return wo


def ensure_can_void_invoice(ctx: Ctx, inv: Invoice) -> None:
    if any(prepo.amounts_for(ctx.db, [inv.id])[inv.id]):
        raise Conflict(
            "This invoice has payments, write-offs or credit memos applied; "
            "void those first, then void the invoice"
        )


# ---- receivables / aging ----
BUCKETS = ("current_cents", "d1_30_cents", "d31_60_cents", "d61_90_cents", "d90_plus_cents")


def bucket_for(days_past_due: int) -> str:
    if days_past_due <= 0:
        return BUCKETS[0]
    if days_past_due <= 30:
        return BUCKETS[1]
    if days_past_due <= 60:
        return BUCKETS[2]
    if days_past_due <= 90:
        return BUCKETS[3]
    return BUCKETS[4]


def receivables(ctx: Ctx) -> dict:
    on = today(ctx)
    invoices = prepo.open_invoices(ctx.db, ctx.scope)
    amounts = prepo.amounts_for(ctx.db, [i.id for i in invoices])
    credits = prepo.credit_by_org(ctx.db, ctx.scope)
    rows: dict[int, dict] = {}

    def row_for(org_id: int, name: str) -> dict:
        return rows.setdefault(
            org_id,
            dict(
                organization_id=org_id,
                organization_name=name,
                **{b: 0 for b in BUCKETS},
                total_open_cents=0,
                credit_cents=credits.get(org_id, 0),
                open_invoice_count=0,
                overdue_invoice_count=0,
                oldest_days_past_due=0,
            ),
        )

    for inv in invoices:
        balance = inv.total_cents - sum(amounts[inv.id])
        days = (on - inv.due_date).days
        r = row_for(inv.organization_id, inv.organization.name)
        r[bucket_for(days)] += balance
        r["total_open_cents"] += balance
        r["open_invoice_count"] += 1
        if days > 0:
            r["overdue_invoice_count"] += 1
            r["oldest_days_past_due"] = max(r["oldest_days_past_due"], days)
    for org_id in credits:  # clients with credit but nothing owed still show
        if org_id not in rows:
            org = repo.get_organization(ctx.db, ctx.scope, org_id)
            if org:
                row_for(org_id, org.name)
    ordered = sorted(
        rows.values(), key=lambda r: (-r["total_open_cents"], r["organization_name"].lower())
    )
    totals = dict(
        organization_id=0,
        organization_name="Total",
        **{b: sum(r[b] for r in ordered) for b in BUCKETS},
        total_open_cents=sum(r["total_open_cents"] for r in ordered),
        credit_cents=sum(r["credit_cents"] for r in ordered),
        open_invoice_count=sum(r["open_invoice_count"] for r in ordered),
        overdue_invoice_count=sum(r["overdue_invoice_count"] for r in ordered),
        oldest_days_past_due=max((r["oldest_days_past_due"] for r in ordered), default=0),
    )
    return dict(as_of=on, rows=ordered, totals=totals)
