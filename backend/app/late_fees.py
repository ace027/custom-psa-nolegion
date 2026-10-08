"""Late fees (docs/BILLING_PLAN.md slice C).

Nothing here runs by itself. The preview lists invoices that qualify under the Settings rule;
a person ticks the ones to charge and applies. Applying creates an ordinary product charge
(not taxable) that is billed on the client's next invoice, plus a record linking it to the
overdue invoice.

* Only clients with ``late_fees_enabled`` are considered (off by default).
* An invoice qualifies when it is final, still owes money, and is more than ``grace_days``
  past due. Fees never compound: earlier late-fee lines on an invoice are left out of its base.
* fee = round_half_up(base x percent_bp / 10000) + flat_cents, where base is the balance.
* An invoice takes at most ``max_per_invoice`` fees; voiding a fee's charge frees its slot.
* The server recomputes every figure on apply; the client only says which invoices.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app import audit
from app import payment_repo as prepo
from app import repositories as repo
from app.billing import create_charge, today
from app.deps import Ctx
from app.errors import Conflict
from app.models import (
    Invoice,
    InvoiceLine,
    LateFeeApplication,
    Organization,
    ProductCharge,
)
from app.money import round_cents


def _rule(ctx: Ctx) -> dict:
    s = repo.get_settings_row(ctx.db)
    return {
        "percent_bp": s.late_fee_percent_bp,
        "flat_cents": s.late_fee_flat_cents,
        "grace_days": s.late_fee_grace_days,
        "max_per_invoice": s.late_fee_max_per_invoice,
    }


def fee_for(base: int, percent_bp: int, flat_cents: int) -> tuple[int, int]:
    """(percent part, total) for a base in cents."""
    pct = round_cents(Decimal(base) * percent_bp / 10000)
    return pct, pct + flat_cents


def _fee_line_totals(ctx: Ctx, invoice_ids: list[int]) -> dict[int, int]:
    """Amount plus tax of late-fee lines sitting on each invoice."""
    if not invoice_ids:
        return {}
    rows = ctx.db.execute(
        select(InvoiceLine.invoice_id, func.sum(InvoiceLine.amount_cents + InvoiceLine.tax_cents))
        .join(ProductCharge, ProductCharge.invoice_line_id == InvoiceLine.id)
        .join(LateFeeApplication, LateFeeApplication.charge_id == ProductCharge.id)
        .where(InvoiceLine.invoice_id.in_(invoice_ids), InvoiceLine.voided.is_(False))
        .group_by(InvoiceLine.invoice_id)
    )
    return {i: int(t) for i, t in rows}


def _fees_so_far(ctx: Ctx, invoice_ids: list[int]) -> dict[int, int]:
    if not invoice_ids:
        return {}
    rows = ctx.db.execute(
        select(LateFeeApplication.invoice_id, func.count())
        .join(ProductCharge, ProductCharge.id == LateFeeApplication.charge_id)
        .where(LateFeeApplication.invoice_id.in_(invoice_ids), ProductCharge.voided_at.is_(None))
        .group_by(LateFeeApplication.invoice_id)
    )
    return {i: int(n) for i, n in rows}


def candidates(ctx: Ctx, org_id: int | None = None, on: date | None = None):
    """(rule, rows) where rows are dicts matching LateFeeRow."""
    rule = _rule(ctx)
    configured = rule["percent_bp"] > 0 or rule["flat_cents"] > 0
    if not configured:
        return rule, False, []
    on = on or today(ctx)
    invoices = [
        i
        for i in prepo.open_invoices(ctx.db, ctx.scope, org_id)
        if i.due_date is not None and (on - i.due_date).days > rule["grace_days"]
    ]
    orgs = {
        o.id: o
        for o in ctx.db.execute(
            select(Organization).where(
                Organization.id.in_({i.organization_id for i in invoices} or {0}),
                Organization.late_fees_enabled.is_(True),
                Organization.archived_at.is_(None),
            )
        )
        .unique()
        .scalars()
    }
    invoices = [i for i in invoices if i.organization_id in orgs]
    ids = [i.id for i in invoices]
    settled = {k: sum(v) for k, v in prepo.amounts_for(ctx.db, ids).items()}
    fee_lines = _fee_line_totals(ctx, ids)
    so_far = _fees_so_far(ctx, ids)
    rows = []
    for inv in invoices:
        balance = inv.total_cents - settled[inv.id]
        base = min(balance, inv.total_cents - fee_lines.get(inv.id, 0))
        if base <= 0 or so_far.get(inv.id, 0) >= rule["max_per_invoice"]:
            continue
        pct, fee = fee_for(base, rule["percent_bp"], rule["flat_cents"])
        if fee <= 0:
            continue
        rows.append(
            {
                "invoice_id": inv.id,
                "invoice_number": inv.number,
                "organization_id": inv.organization_id,
                "organization_name": orgs[inv.organization_id].name,
                "due_date": inv.due_date,
                "days_overdue": (on - inv.due_date).days,
                "balance_cents": balance,
                "base_cents": base,
                "percent_bp": rule["percent_bp"],
                "percent_fee_cents": pct,
                "flat_fee_cents": rule["flat_cents"],
                "fee_cents": fee,
                "fees_so_far": so_far.get(inv.id, 0),
            }
        )
    return rule, True, rows


def _description(row: dict) -> str:
    parts = f"Late fee on {row['invoice_number']}: {row['days_overdue']} days overdue"
    bits = []
    if row["percent_bp"]:
        pct = Decimal(row["percent_bp"]) / 100
        bits.append(f"{pct.normalize():f}% of ${row['base_cents'] / 100:,.2f}")
    if row["flat_fee_cents"]:
        bits.append(f"${row['flat_fee_cents'] / 100:,.2f} flat")
    return parts + (", " + " + ".join(bits) if bits else "")


def apply(ctx: Ctx, invoice_ids: list[int]) -> list[LateFeeApplication]:
    ids = sorted(set(invoice_ids))
    # Serialise concurrent applies for the same invoices before recomputing.
    ctx.db.execute(
        select(Invoice.id).where(Invoice.id.in_(ids)).order_by(Invoice.id).with_for_update()
    ).all()
    rule, _, rows = candidates(ctx)
    by_id = {r["invoice_id"]: r for r in rows}
    bad = [i for i in ids if i not in by_id]
    if bad:
        raise Conflict(
            "These invoices do not qualify for a late fee right now (not overdue past the "
            f"grace period, opted out, already at the limit, or paid): {bad}"
        )
    out = []
    for inv_id in ids:
        row = by_id[inv_id]
        charge = create_charge(
            ctx,
            {
                "organization_id": row["organization_id"],
                "description": _description(row),
                "quantity": 1,
                "unit_price_cents": row["fee_cents"],
                "taxable": False,
            },
        )
        app = LateFeeApplication(
            organization_id=row["organization_id"],
            invoice_id=inv_id,
            charge_id=charge.id,
            days_overdue=row["days_overdue"],
            base_cents=row["base_cents"],
            percent_bp=row["percent_bp"],
            flat_cents=row["flat_fee_cents"],
            fee_cents=row["fee_cents"],
            applied_by=ctx.user.id if ctx.user else None,
        )
        ctx.db.add(app)
        ctx.db.flush()
        audit.record(
            ctx.db,
            ctx.user,
            "late_fee.apply",
            app,
            after=audit.snapshot(app),
            organization_id=app.organization_id,
        )
        out.append(app)
    return out


def applied(ctx: Ctx, org_id: int | None = None, limit: int = 100):
    stmt = ctx.scope.apply(select(LateFeeApplication), LateFeeApplication.organization_id)
    if org_id is not None:
        stmt = stmt.where(LateFeeApplication.organization_id == org_id)
    return list(ctx.db.execute(stmt.order_by(LateFeeApplication.id.desc()).limit(limit)).scalars())
