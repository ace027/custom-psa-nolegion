"""Credit memos and refunds (docs/BILLING_PLAN.md slice B).

* A credit memo is a numbered (CM-YYYY-NNNN, gap-free), immutable document: lines are positive
  amounts with tax per line, exactly like an invoice. It is issued on creation; there is no draft.
* A memo reduces what a client owes by being APPLIED to finalized invoices. Whatever is not
  applied stays as client credit. Voiding a memo (reason required) undoes its applications.
* A refund records money paid back against a payment. It can only come out of the part of the
  payment that is not applied to an invoice; to refund applied money, undo that application first
  (which reopens the invoice), then refund.
* Nothing here is edited or deleted, only voided with a reason. The database enforces the caps.
"""

from decimal import Decimal

from sqlalchemy import text

from app import audit
from app import billing_repo as brepo
from app import payment_repo as prepo
from app import repositories as repo
from app.billing import today
from app.deps import Ctx
from app.errors import Conflict, NotFound
from app.models import CreditMemo, CreditMemoApplication, CreditMemoLine, Refund
from app.money import line_amounts, to_qty
from app.payments import _balance, _final_invoice, _flush, _require_reason
from app.ticket_services import now


def _next_number(ctx: Ctx, year: int) -> str:
    """Gap-free per year; the counter row is locked by the UPSERT and rolls back with the
    surrounding transaction, so a failed issue never burns a number."""
    n = ctx.db.execute(
        text(
            "INSERT INTO credit_memo_counters (year, last_number) VALUES (:y, 1) "
            "ON CONFLICT (year) DO UPDATE SET last_number = credit_memo_counters.last_number + 1 "
            "RETURNING last_number"
        ),
        {"y": year},
    ).scalar_one()
    return f"CM-{year}-{n:04d}"


def memo_unapplied(ctx: Ctx, memo: CreditMemo) -> int:
    if memo.status != "active":
        return 0
    return memo.total_cents - prepo.memo_applied(ctx.db, [memo.id])[memo.id]


def _apply(ctx: Ctx, memo: CreditMemo, inv, amount: int) -> CreditMemoApplication:
    application = CreditMemoApplication(
        memo_id=memo.id,
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
        "credit_memo.apply",
        application,
        after=audit.snapshot(application),
        organization_id=inv.organization_id,
        detail={"invoice": inv.number, "memo": memo.number},
    )
    return application


def create_memo(ctx: Ctx, data: dict) -> CreditMemo:
    org = repo.get_organization(ctx.db, ctx.scope, data["organization_id"])
    if org is None:
        raise NotFound("Organization not found")
    reason = _require_reason(data.get("reason"))
    memo_date = data.get("memo_date") or today(ctx)
    if memo_date > today(ctx):
        raise Conflict("A credit memo cannot be dated in the future")
    related = None
    if data.get("invoice_id") is not None:
        related = brepo.get_invoice(ctx.db, ctx.scope, data["invoice_id"])
        if related is None or related.organization_id != org.id or related.status == "draft":
            raise Conflict("The invoice this corrects must be an issued invoice of the same client")
    lines = data.get("lines") or []
    if not lines:
        raise Conflict("A credit memo needs at least one line")
    computed = []
    for i, ln in enumerate(lines, start=1):
        qty = to_qty(ln["quantity"])
        rate = org.tax_rate_bp if ln.get("taxable") else 0
        amount, tax = line_amounts(qty, ln["unit_price_cents"], rate)
        if qty <= 0 or amount <= 0:
            raise Conflict(f"Line {i} rounds to zero; enter a positive quantity and price")
        computed.append(
            (i, ln["description"].strip(), qty, ln["unit_price_cents"], amount, rate, tax)
        )
    subtotal = sum(c[4] for c in computed)
    tax_total = sum(c[6] for c in computed)
    total = subtotal + tax_total
    applications = data.get("applications") or []
    if len({a["invoice_id"] for a in applications}) != len(applications):
        raise Conflict("List each invoice only once")
    if sum(a["amount_cents"] for a in applications) > total:
        raise Conflict("The amounts applied to invoices exceed the credit memo")
    locked = {
        a["invoice_id"]: _final_invoice(ctx, a["invoice_id"], org.id)
        for a in sorted(applications, key=lambda a: a["invoice_id"])
    }
    for a in applications:
        inv = locked[a["invoice_id"]]
        if a["amount_cents"] > _balance(ctx, inv):
            raise Conflict(f"Invoice {inv.number} only has a balance of {_balance(ctx, inv)} cents")
    memo = CreditMemo(
        organization_id=org.id,
        number=_next_number(ctx, memo_date.year),
        memo_date=memo_date,
        reason=reason,
        invoice_id=related.id if related else None,
        subtotal_cents=subtotal,
        tax_cents=tax_total,
        total_cents=total,
        created_by=ctx.user.id if ctx.user else None,
    )
    ctx.db.add(memo)
    ctx.db.flush()
    for position, description, qty, unit, amount, rate, tax in computed:
        ctx.db.add(
            CreditMemoLine(
                memo_id=memo.id,
                organization_id=org.id,
                position=position,
                description=description,
                quantity=Decimal(qty),
                unit_price_cents=unit,
                amount_cents=amount,
                tax_rate_bp=rate,
                tax_cents=tax,
            )
        )
    _flush(ctx)
    ctx.db.refresh(memo)
    audit.record(
        ctx.db,
        ctx.user,
        "credit_memo.create",
        memo,
        after=audit.snapshot(memo),
        organization_id=org.id,
        detail={"number": memo.number, "lines": len(computed)},
    )
    for a in sorted(applications, key=lambda a: a["invoice_id"]):
        _apply(ctx, memo, locked[a["invoice_id"]], a["amount_cents"])
    return memo


def apply_memo(ctx: Ctx, memo_id: int, invoice_id: int, amount: int) -> CreditMemoApplication:
    peek = prepo.get_memo(ctx.db, ctx.scope, memo_id)
    if peek is None:
        raise NotFound("Credit memo not found")
    inv = _final_invoice(ctx, invoice_id, peek.organization_id)  # invoice lock first...
    memo = prepo.get_memo(ctx.db, ctx.scope, memo_id, lock=True)  # ...then the memo
    if memo.status != "active":
        raise Conflict("A voided credit memo cannot be applied")
    left = memo_unapplied(ctx, memo)
    if amount > left:
        raise Conflict(f"Only {left} cents of this credit memo are unapplied")
    if amount > _balance(ctx, inv):
        raise Conflict(f"Invoice {inv.number} only has a balance of {_balance(ctx, inv)} cents")
    return _apply(ctx, memo, inv, amount)


def void_memo_application(
    ctx: Ctx, application_id: int, reason: str | None
) -> CreditMemoApplication:
    reason = _require_reason(reason)
    application = prepo.get_memo_application(ctx.db, ctx.scope, application_id, lock=True)
    if application is None:
        raise NotFound("Credit memo application not found")
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
        "credit_memo.unapply",
        application,
        before=before,
        after=audit.snapshot(application),
        organization_id=application.organization_id,
        detail={"reason": reason},
    )
    return application


def void_memo(ctx: Ctx, memo_id: int, reason: str | None) -> CreditMemo:
    reason = _require_reason(reason)
    memo = prepo.get_memo(ctx.db, ctx.scope, memo_id, lock=True)
    if memo is None:
        raise NotFound("Credit memo not found")
    if memo.status == "void":
        raise Conflict("Already voided")
    before = audit.snapshot(memo)
    active = prepo.memo_applications(ctx.db, ctx.scope, memo.id, active_only=True)
    for application in active:  # the invoices it reduced become open again
        application.voided_at, application.void_reason = now(), f"Credit memo voided: {reason}"
        application.voided_by = ctx.user.id if ctx.user else None
    ctx.db.flush()
    memo.status, memo.voided_at, memo.void_reason = "void", now(), reason
    memo.voided_by = ctx.user.id if ctx.user else None
    _flush(ctx)
    ctx.db.refresh(memo)
    audit.record(
        ctx.db,
        ctx.user,
        "credit_memo.void",
        memo,
        before=before,
        after=audit.snapshot(memo),
        organization_id=memo.organization_id,
        detail={"reason": reason, "unapplied_invoices": [a.invoice_id for a in active]},
    )
    return memo


# ---- refunds ----
def payment_refundable(ctx: Ctx, payment) -> int:
    """The part of a payment that is neither applied to an invoice nor already refunded."""
    if payment.status != "active":
        return 0
    return (
        payment.amount_cents
        - prepo.applied_by_payment(ctx.db, [payment.id])[payment.id]
        - prepo.refunded_by_payment(ctx.db, [payment.id])[payment.id]
    )


def create_refund(ctx: Ctx, payment_id: int, data: dict) -> Refund:
    reason = _require_reason(data.get("reason"))
    payment = prepo.get_payment(ctx.db, ctx.scope, payment_id, lock=True)
    if payment is None:
        raise NotFound("Payment not found")
    if payment.status != "active":
        raise Conflict("A voided payment cannot be refunded")
    on = data.get("refunded_on") or today(ctx)
    if on > today(ctx):
        raise Conflict("A refund cannot be dated in the future")
    left = payment_refundable(ctx, payment)
    if data["amount_cents"] > left:
        raise Conflict(
            f"Only {left} cents of this payment can be refunded; money applied to invoices "
            "must be unapplied first"
        )
    refund = Refund(
        payment_id=payment.id,
        organization_id=payment.organization_id,
        amount_cents=data["amount_cents"],
        refunded_on=on,
        method=data["method"],
        reference=data.get("reference"),
        reason=reason,
        created_by=ctx.user.id if ctx.user else None,
    )
    ctx.db.add(refund)
    _flush(ctx)
    ctx.db.refresh(refund)
    audit.record(
        ctx.db,
        ctx.user,
        "payment.refund",
        refund,
        after=audit.snapshot(refund),
        organization_id=refund.organization_id,
        detail={"payment_id": payment.id, "reason": reason},
    )
    return refund


def void_refund(ctx: Ctx, refund_id: int, reason: str | None) -> Refund:
    reason = _require_reason(reason)
    refund = prepo.get_refund(ctx.db, ctx.scope, refund_id)
    if refund is None:
        raise NotFound("Refund not found")
    if refund.voided_at:
        raise Conflict("Already voided")
    before = audit.snapshot(refund)
    refund.voided_at, refund.void_reason = now(), reason
    refund.voided_by = ctx.user.id if ctx.user else None
    _flush(ctx)
    ctx.db.refresh(refund)
    audit.record(
        ctx.db,
        ctx.user,
        "payment.refund_void",
        refund,
        before=before,
        after=audit.snapshot(refund),
        organization_id=refund.organization_id,
        detail={"reason": reason},
    )
    return refund
