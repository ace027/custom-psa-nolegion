"""Contracts and invoicing rules. Read docs/PLAN.md section 6 for the billing math contract.

Key guarantees (each has tests):
  * money is integer cents; per-line rounding; totals are sums of lines (app/money.py)
  * a finalized invoice is immutable (also enforced by database triggers)
  * a billing run for a month can exist only once, so an agreement period is never billed twice
  * finalizing a run is all-or-nothing and numbers are gap-free per year
  * time and product charges are locked onto an invoice line; voiding releases them
"""

import calendar
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import text, update
from sqlalchemy.exc import IntegrityError

from app import audit
from app import repositories as repo
from app.billing_repo import (
    agreements_overlapping,
    get_agreement,
    get_charge,
    get_invoice,
    get_line,
    get_org_rate,
    get_run,
    invoice_lines,
    list_work_types,
    live_run_for_period,
    orgs_with_billables,
    run_invoices,
    tickets_by_id,
    unbilled_charges,
    unbilled_time,
)
from app.deps import Ctx
from app.errors import Conflict, NotFound
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
    TimeEntry,
    WorkType,
)
from app.money import format_money, hours, line_amounts, to_qty
from app.ticket_services import calendar as business_calendar
from app.ticket_services import now

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def today(ctx: Ctx) -> date:
    return now().astimezone(business_calendar(ctx).tz).date()


def _org(ctx: Ctx, org_id: int) -> Organization:
    org = repo.get_organization(ctx.db, ctx.scope, org_id)
    if org is None:
        raise NotFound("Organization not found")
    return org


def _flush(ctx: Ctx, message: str) -> None:
    try:
        ctx.db.flush()
    except IntegrityError as exc:
        ctx.db.rollback()
        raise Conflict(message) from exc


def _apply(obj, data: dict) -> None:
    for key, value in data.items():
        setattr(obj, key, value)


# =========================================================================================
# Rates, tax and terms
# =========================================================================================
def update_work_type_billing(ctx: Ctx, work_type_id: int, data: dict) -> WorkType:
    wt = repo.get_lookup(ctx.db, WorkType, work_type_id)
    if wt is None:
        raise NotFound("Work type not found")
    before = audit.snapshot(wt)
    if "rate_cents" in data:
        wt.rate_cents = data["rate_cents"]
    if data.get("taxable") is not None:
        wt.taxable = data["taxable"]
    ctx.db.flush()
    ctx.db.refresh(wt)
    audit.record(
        ctx.db, ctx.user, "work_type.billing_update", wt, before=before, after=audit.snapshot(wt)
    )
    return wt


def update_org_billing(ctx: Ctx, org_id: int, data: dict) -> Organization:
    org = _org(ctx, org_id)
    before = audit.snapshot(org)
    _apply(org, {k: v for k, v in data.items() if v is not None})
    ctx.db.flush()
    ctx.db.refresh(org)
    audit.record(
        ctx.db,
        ctx.user,
        "organization.billing_update",
        org,
        before=before,
        after=audit.snapshot(org),
        organization_id=org.id,
    )
    return org


def set_org_rate(ctx: Ctx, org_id: int, work_type_id: int, rate_cents: int) -> OrgWorkTypeRate:
    _org(ctx, org_id)
    if repo.get_lookup(ctx.db, WorkType, work_type_id) is None:
        raise NotFound("Work type not found")
    rate = get_org_rate(ctx.db, ctx.scope, org_id, work_type_id)
    if rate is None:
        rate = OrgWorkTypeRate(
            organization_id=org_id, work_type_id=work_type_id, rate_cents=rate_cents
        )
        ctx.db.add(rate)
        ctx.db.flush()
        audit.record(
            ctx.db,
            ctx.user,
            "org_rate.set",
            rate,
            after=audit.snapshot(rate),
            organization_id=org_id,
        )
    else:
        before = audit.snapshot(rate)
        rate.rate_cents = rate_cents
        ctx.db.flush()
        ctx.db.refresh(rate)
        audit.record(
            ctx.db,
            ctx.user,
            "org_rate.set",
            rate,
            before=before,
            after=audit.snapshot(rate),
            organization_id=org_id,
        )
    return rate


def delete_org_rate(ctx: Ctx, org_id: int, work_type_id: int) -> None:
    rate = get_org_rate(ctx.db, ctx.scope, org_id, work_type_id)
    if rate is None:
        raise NotFound("No override for that work type")
    audit.record(
        ctx.db,
        ctx.user,
        "org_rate.delete",
        rate,
        before=audit.snapshot(rate),
        organization_id=org_id,
    )
    ctx.db.delete(rate)
    ctx.db.flush()


def hourly_rate(ctx: Ctx, org_id: int, wt: WorkType) -> int | None:
    override = get_org_rate(ctx.db, ctx.scope, org_id, wt.id)
    return override.rate_cents if override else wt.rate_cents


# =========================================================================================
# Products, agreements, one-off charges
# =========================================================================================
def create_product(ctx: Ctx, data: dict) -> Product:
    product = Product(**data)
    ctx.db.add(product)
    _flush(ctx, "An active product with that SKU already exists")
    audit.record(ctx.db, ctx.user, "product.create", product, after=audit.snapshot(product))
    return product


def update_product(ctx: Ctx, product_id: int, data: dict) -> Product:
    product = ctx.db.get(Product, product_id)
    if product is None:
        raise NotFound("Product not found")
    before = audit.snapshot(product)
    _apply(product, data)
    _flush(ctx, "An active product with that SKU already exists")
    ctx.db.refresh(product)
    audit.record(
        ctx.db, ctx.user, "product.update", product, before=before, after=audit.snapshot(product)
    )
    return product


def set_product_archived(ctx: Ctx, product_id: int, archived: bool) -> Product:
    product = ctx.db.get(Product, product_id)
    if product is None:
        raise NotFound("Product not found")
    before = audit.snapshot(product)
    product.archived_at = now() if archived else None
    _flush(ctx, "An active product with that SKU already exists")
    ctx.db.refresh(product)
    audit.record(
        ctx.db,
        ctx.user,
        "product.archive" if archived else "product.unarchive",
        product,
        before=before,
        after=audit.snapshot(product),
    )
    return product


def _validate_agreement(data: dict) -> None:
    if data.get("end_date") and data["end_date"] < data["start_date"]:
        raise Conflict("End date cannot be before the start date")


def create_agreement(ctx: Ctx, data: dict) -> Agreement:
    _org(ctx, data["organization_id"])
    _validate_agreement(data)
    if data["type"] == "flat":
        data = {**data, "quantity": 1}
    agreement = Agreement(**data)
    ctx.db.add(agreement)
    ctx.db.flush()
    ctx.db.add(
        AgreementQuantityLog(
            agreement_id=agreement.id,
            organization_id=agreement.organization_id,
            old_quantity=None,
            new_quantity=agreement.quantity,
            reason="Agreement created",
            changed_by=ctx.user.id if ctx.user else None,
        )
    )
    audit.record(
        ctx.db,
        ctx.user,
        "agreement.create",
        agreement,
        after=audit.snapshot(agreement),
        organization_id=agreement.organization_id,
    )
    ctx.db.refresh(agreement)
    return agreement


def update_agreement(ctx: Ctx, agreement_id: int, data: dict) -> Agreement:
    agreement = get_agreement(ctx.db, ctx.scope, agreement_id)
    if agreement is None:
        raise NotFound("Agreement not found")
    before = audit.snapshot(agreement)
    reason = data.pop("reason", None)
    for key, value in data.items():
        if value is not None or key == "end_date":  # end_date may be cleared explicitly
            setattr(agreement, key, value)
    if agreement.type == "flat":
        agreement.quantity = 1
    if agreement.end_date and agreement.end_date < agreement.start_date:
        raise Conflict("End date cannot be before the start date")
    ctx.db.flush()
    if agreement.quantity != before["quantity"]:
        ctx.db.add(
            AgreementQuantityLog(
                agreement_id=agreement.id,
                organization_id=agreement.organization_id,
                old_quantity=before["quantity"],
                new_quantity=agreement.quantity,
                reason=reason,
                changed_by=ctx.user.id if ctx.user else None,
            )
        )
    ctx.db.flush()
    ctx.db.refresh(agreement)
    audit.record(
        ctx.db,
        ctx.user,
        "agreement.update",
        agreement,
        before=before,
        after=audit.snapshot(agreement),
        organization_id=agreement.organization_id,
        detail={"reason": reason} if reason else None,
    )
    return agreement


def create_charge(ctx: Ctx, data: dict) -> ProductCharge:
    org = _org(ctx, data["organization_id"])
    product = None
    if data.get("product_id") is not None:
        product = ctx.db.get(Product, data["product_id"])
        if product is None or product.archived_at:
            raise Conflict("Unknown or archived product")
    if data.get("ticket_id") is not None:
        ticket = repo.get_ticket(ctx.db, ctx.scope, data["ticket_id"])
        if ticket is None or ticket.organization_id != org.id:
            raise Conflict("Ticket does not belong to this organization")
    description = data.get("description") or (product.name if product else None)
    price = data.get("unit_price_cents")
    if price is None and product:
        price = product.unit_price_cents
    if not description or price is None:
        raise Conflict("A description and a price are required when no product is chosen")
    taxable = data.get("taxable")
    if taxable is None:
        taxable = product.taxable if product else False
    charge = ProductCharge(
        organization_id=org.id,
        product_id=data.get("product_id"),
        ticket_id=data.get("ticket_id"),
        description=description,
        quantity=to_qty(data["quantity"]),
        unit_price_cents=price,
        taxable=taxable,
        charged_on=data.get("charged_on") or today(ctx),
        created_by=ctx.user.id if ctx.user else None,
    )
    ctx.db.add(charge)
    ctx.db.flush()
    ctx.db.refresh(charge)
    audit.record(
        ctx.db,
        ctx.user,
        "charge.create",
        charge,
        after=audit.snapshot(charge),
        organization_id=org.id,
    )
    return charge


def void_charge(ctx: Ctx, charge_id: int) -> ProductCharge:
    charge = get_charge(ctx.db, ctx.scope, charge_id)
    if charge is None:
        raise NotFound("Charge not found")
    if charge.invoice_line_id is not None:
        raise Conflict("This charge is on an invoice; remove it from the draft or void the invoice")
    if charge.voided_at:
        raise Conflict("Already voided")
    before = audit.snapshot(charge)
    charge.voided_at = now()
    ctx.db.flush()
    ctx.db.refresh(charge)
    audit.record(
        ctx.db,
        ctx.user,
        "charge.void",
        charge,
        before=before,
        after=audit.snapshot(charge),
        organization_id=charge.organization_id,
    )
    return charge


# =========================================================================================
# Invoices (drafts)
# =========================================================================================
def _require_draft(invoice: Invoice) -> None:
    if invoice.status != "draft":
        raise Conflict(f"Invoice is {invoice.status}; only drafts can be changed")


def _touch_run(ctx: Ctx, invoice: Invoice) -> None:
    """Any change to a draft invoice in a run voids the review: it must be looked at again."""
    if invoice.billing_run_id is None:
        return
    run = get_run(ctx.db, invoice.billing_run_id, lock=True)
    if run and run.status == "reviewed":
        run.status, run.reviewed_at, run.reviewed_by = "draft", None, None
        ctx.db.flush()
        audit.record(
            ctx.db,
            ctx.user,
            "billing_run.review_invalidated",
            run,
            detail={"reason": "an invoice in the run was changed"},
        )


def recalc(ctx: Ctx, invoice: Invoice) -> None:
    lines = invoice_lines(ctx.db, ctx.scope, invoice.id)
    invoice.subtotal_cents = sum(line.amount_cents for line in lines)
    invoice.tax_cents = sum(line.tax_cents for line in lines)
    invoice.total_cents = invoice.subtotal_cents + invoice.tax_cents
    invoice.updated_at = now()
    ctx.db.flush()


def _add_line(
    ctx: Ctx,
    invoice: Invoice,
    kind: str,
    description: str,
    quantity: Decimal,
    unit_price_cents: int,
    tax_rate_bp: int,
    **extra,
) -> InvoiceLine:
    amount, tax = line_amounts(quantity, unit_price_cents, tax_rate_bp)
    position = len(invoice_lines(ctx.db, ctx.scope, invoice.id)) + 1
    line = InvoiceLine(
        invoice_id=invoice.id,
        organization_id=invoice.organization_id,
        position=position,
        kind=kind,
        description=description,
        quantity=quantity,
        unit_price_cents=unit_price_cents,
        amount_cents=amount,
        tax_rate_bp=tax_rate_bp,
        tax_cents=tax,
        **extra,
    )
    ctx.db.add(line)
    ctx.db.flush()
    return line


def _new_draft(ctx: Ctx, org: Organization, *, run=None, period=None, memo=None) -> Invoice:
    invoice = Invoice(
        organization_id=org.id,
        status="draft",
        billing_run_id=run.id if run else None,
        period_start=period[0] if period else None,
        period_end=period[1] if period else None,
        memo=memo,
        created_by=ctx.user.id if ctx.user else None,
    )
    ctx.db.add(invoice)
    ctx.db.flush()
    ctx.db.refresh(invoice)
    return invoice


def _pull_time(ctx: Ctx, invoice: Invoice, org: Organization, through: date) -> list[str]:
    warnings: list[str] = []
    entries = unbilled_time(ctx.db, ctx.scope, org.id, through)
    if not entries:
        return warnings
    work_types = {wt.id: wt for wt in list_work_types(ctx.db)}
    tickets = tickets_by_id(ctx.db, ctx.scope, {e.ticket_id for e in entries})
    groups: dict[tuple[int, int], list[TimeEntry]] = {}
    for e in entries:
        groups.setdefault((e.ticket_id, e.work_type_id), []).append(e)
    for (ticket_id, wt_id), items in groups.items():
        wt = work_types[wt_id]
        rate = hourly_rate(ctx, org.id, wt)
        minutes = sum(e.minutes_billable for e in items)
        if rate is None:
            warnings.append(
                f"No hourly rate for work type '{wt.name}': {len(items)} time "
                f"entr{'y' if len(items) == 1 else 'ies'} "
                f"({minutes} min) left unbilled"
            )
            continue
        t = tickets.get(ticket_id)
        label = f"Ticket #{t.number}: {t.subject}" if t else f"Ticket {ticket_id}"
        line = _add_line(
            ctx,
            invoice,
            "time",
            f"{label} ({wt.name}, hours)",
            hours(minutes),
            rate,
            org.tax_rate_bp if wt.taxable else 0,
        )
        for e in items:
            e.invoice_line_id = line.id
    return warnings


def _pull_charges(ctx: Ctx, invoice: Invoice, org: Organization, through: date) -> None:
    for charge in unbilled_charges(ctx.db, ctx.scope, org.id, through):
        line = _add_line(
            ctx,
            invoice,
            "product",
            charge.description,
            charge.quantity,
            charge.unit_price_cents,
            org.tax_rate_bp if charge.taxable else 0,
        )
        charge.invoice_line_id = line.id


def _agreement_description(a: Agreement, period_start: date) -> str:
    month = f"{MONTHS[period_start.month - 1]} {period_start.year}"
    if a.type == "flat":
        return f"{a.name} ({month})"
    unit = "users" if a.type == "per_user" else "devices"
    return f"{a.name}: {a.quantity} {unit} x {format_money(a.unit_price_cents)} ({month})"


def _pull_agreements(
    ctx: Ctx, invoice: Invoice, org: Organization, start: date, end: date
) -> list[str]:
    warnings = []
    for a in agreements_overlapping(ctx.db, ctx.scope, org.id, start, end):
        if a.quantity == 0:
            warnings.append(f"Agreement '{a.name}' has quantity 0 and was not billed")
            continue
        _add_line(
            ctx,
            invoice,
            "agreement",
            _agreement_description(a, start),
            Decimal(a.quantity),
            a.unit_price_cents,
            org.tax_rate_bp if a.taxable else 0,
            agreement_id=a.id,
            period_start=start,
        )
    return warnings


def create_invoice(ctx: Ctx, org_id: int, memo: str | None, include_unbilled: bool) -> Invoice:
    org = _org(ctx, org_id)
    invoice = _new_draft(ctx, org, memo=memo)
    warnings: list[str] = []
    if include_unbilled:
        through = today(ctx)
        warnings += _pull_time(ctx, invoice, org, through)
        _pull_charges(ctx, invoice, org, through)
    invoice.warnings = warnings
    recalc(ctx, invoice)
    audit.record(
        ctx.db,
        ctx.user,
        "invoice.create",
        invoice,
        after=audit.snapshot(invoice),
        organization_id=org.id,
    )
    return invoice


def add_unbilled(ctx: Ctx, invoice_id: int) -> Invoice:
    invoice = get_invoice(ctx.db, ctx.scope, invoice_id, lock=True)
    if invoice is None:
        raise NotFound("Invoice not found")
    _require_draft(invoice)
    org, through = invoice.organization, today(ctx)
    warnings = _pull_time(ctx, invoice, org, through)
    _pull_charges(ctx, invoice, org, through)
    invoice.warnings = sorted(set(invoice.warnings) | set(warnings))
    recalc(ctx, invoice)
    _touch_run(ctx, invoice)
    audit.record(
        ctx.db,
        ctx.user,
        "invoice.add_unbilled",
        invoice,
        after={"total_cents": invoice.total_cents},
        organization_id=invoice.organization_id,
    )
    return invoice


def update_invoice(ctx: Ctx, invoice_id: int, data: dict) -> Invoice:
    invoice = get_invoice(ctx.db, ctx.scope, invoice_id, lock=True)
    if invoice is None:
        raise NotFound("Invoice not found")
    _require_draft(invoice)
    before = audit.snapshot(invoice)
    invoice.memo = data.get("memo")
    ctx.db.flush()
    _touch_run(ctx, invoice)
    audit.record(
        ctx.db,
        ctx.user,
        "invoice.update",
        invoice,
        before=before,
        after=audit.snapshot(invoice),
        organization_id=invoice.organization_id,
    )
    return invoice


def add_manual_line(ctx: Ctx, invoice_id: int, data: dict) -> InvoiceLine:
    invoice = get_invoice(ctx.db, ctx.scope, invoice_id, lock=True)
    if invoice is None:
        raise NotFound("Invoice not found")
    _require_draft(invoice)
    rate = invoice.organization.tax_rate_bp if data["taxable"] else 0
    line = _add_line(
        ctx,
        invoice,
        "manual",
        data["description"],
        to_qty(data["quantity"]),
        data["unit_price_cents"],
        rate,
    )
    recalc(ctx, invoice)
    _touch_run(ctx, invoice)
    audit.record(
        ctx.db,
        ctx.user,
        "invoice.line_add",
        line,
        after=audit.snapshot(line),
        organization_id=invoice.organization_id,
        detail={"invoice_id": invoice.id},
    )
    return line


def _line_and_invoice(ctx: Ctx, line_id: int) -> tuple[InvoiceLine, Invoice]:
    line = get_line(ctx.db, ctx.scope, line_id)
    if line is None:
        raise NotFound("Invoice line not found")
    invoice = get_invoice(ctx.db, ctx.scope, line.invoice_id, lock=True)
    _require_draft(invoice)
    return line, invoice


def update_line(ctx: Ctx, line_id: int, data: dict) -> InvoiceLine:
    line, invoice = _line_and_invoice(ctx, line_id)
    before = audit.snapshot(line)
    for key in ("description", "unit_price_cents", "tax_rate_bp"):
        if data.get(key) is not None:
            setattr(line, key, data[key])
    if data.get("quantity") is not None:
        line.quantity = to_qty(data["quantity"])
    if line.kind != "manual" and (line.quantity <= 0 or line.unit_price_cents < 0):
        raise Conflict("Only manual lines can be negative; add a manual credit line instead")
    line.amount_cents, line.tax_cents = line_amounts(
        line.quantity, line.unit_price_cents, line.tax_rate_bp
    )
    ctx.db.flush()
    recalc(ctx, invoice)
    _touch_run(ctx, invoice)
    ctx.db.refresh(line)
    audit.record(
        ctx.db,
        ctx.user,
        "invoice.line_update",
        line,
        before=before,
        after=audit.snapshot(line),
        organization_id=invoice.organization_id,
        detail={"invoice_id": invoice.id},
    )
    return line


def _release(ctx: Ctx, line_ids: list[int]) -> None:
    if not line_ids:
        return
    ctx.db.execute(
        update(TimeEntry)
        .where(TimeEntry.invoice_line_id.in_(line_ids))
        .values(invoice_line_id=None)
    )
    ctx.db.execute(
        update(ProductCharge)
        .where(ProductCharge.invoice_line_id.in_(line_ids))
        .values(invoice_line_id=None)
    )


def delete_line(ctx: Ctx, line_id: int) -> None:
    line, invoice = _line_and_invoice(ctx, line_id)
    audit.record(
        ctx.db,
        ctx.user,
        "invoice.line_delete",
        line,
        before=audit.snapshot(line),
        organization_id=invoice.organization_id,
        detail={"invoice_id": invoice.id},
    )
    _release(ctx, [line.id])  # the time/charges become billable again
    ctx.db.delete(line)
    ctx.db.flush()
    recalc(ctx, invoice)
    _touch_run(ctx, invoice)


# =========================================================================================
# Finalize / void
# =========================================================================================
def next_invoice_number(ctx: Ctx, year: int) -> str:
    """Gap-free per year: the counter row is locked by the UPSERT and rolls back with the
    surrounding transaction, so a failed finalize never burns a number."""
    n = ctx.db.execute(
        text(
            "INSERT INTO invoice_counters (year, last_number) VALUES (:y, 1) "
            "ON CONFLICT (year) DO UPDATE SET last_number = invoice_counters.last_number + 1 "
            "RETURNING last_number"
        ),
        {"y": year},
    ).scalar_one()
    return f"INV-{year}-{n:04d}"


def finalize_invoice(ctx: Ctx, invoice: Invoice, invoice_date: date | None = None) -> Invoice:
    _require_draft(invoice)
    lines = invoice_lines(ctx.db, ctx.scope, invoice.id)
    if not lines:
        raise Conflict("An invoice needs at least one line")
    recalc(ctx, invoice)
    if invoice.total_cents < 0:
        raise Conflict("The invoice total is negative; adjust the lines before finalizing")
    st = repo.get_settings_row(ctx.db)
    if not (st.company_name or "").strip():
        raise Conflict("Set your company name under Settings > Invoicing before finalizing")
    org = invoice.organization
    before = audit.snapshot(invoice)
    when = invoice_date or today(ctx)
    invoice.invoice_date = when
    invoice.terms_days = org.payment_terms_days
    invoice.due_date = when + timedelta(days=org.payment_terms_days)
    invoice.number = next_invoice_number(ctx, when.year)
    invoice.bill_to_name, invoice.bill_to_address = org.name, org.billing_address
    invoice.seller_name, invoice.seller_address = st.company_name, st.company_address
    invoice.footer = st.invoice_footer
    invoice.status, invoice.finalized_at = "final", now()
    invoice.finalized_by = ctx.user.id if ctx.user else None
    ctx.db.flush()
    ctx.db.refresh(invoice)
    audit.record(
        ctx.db,
        ctx.user,
        "invoice.finalize",
        invoice,
        before=before,
        after=audit.snapshot(invoice),
        organization_id=invoice.organization_id,
    )
    if st.auto_prepare_invoice_emails:  # prepared for review only; a person approves the send
        from app.notices import prepare_invoice_email

        prepare_invoice_email(ctx, invoice.id, manual=False)
    return invoice


def finalize_invoice_by_id(ctx: Ctx, invoice_id: int, invoice_date: date | None) -> Invoice:
    invoice = get_invoice(ctx.db, ctx.scope, invoice_id, lock=True)
    if invoice is None:
        raise NotFound("Invoice not found")
    if invoice.billing_run_id is not None:
        run = get_run(ctx.db, invoice.billing_run_id)
        if run and run.status in ("draft", "reviewed"):
            raise Conflict("This invoice belongs to a billing run; finalize the run instead")
    return finalize_invoice(ctx, invoice, invoice_date)


def void_invoice(ctx: Ctx, invoice_id: int, reason: str | None) -> Invoice:
    invoice = get_invoice(ctx.db, ctx.scope, invoice_id, lock=True)
    if invoice is None:
        raise NotFound("Invoice not found")
    if invoice.status == "void":
        raise Conflict("Already void")
    if invoice.status == "final":
        from app import payments  # local import: payments imports this module

        payments.ensure_can_void_invoice(ctx, invoice)
    if invoice.status == "final" and not (reason and len(reason.strip()) >= 3):
        raise Conflict("A reason is required to void a finalized invoice")
    was = invoice.status
    before = audit.snapshot(invoice)
    lines = invoice_lines(ctx.db, ctx.scope, invoice.id)
    invoice.status, invoice.voided_at, invoice.void_reason = "void", now(), reason
    invoice.voided_by = ctx.user.id if ctx.user else None
    ctx.db.flush()
    line_ids = [line.id for line in lines]
    _release(ctx, line_ids)  # time and charges can be billed again
    for line in lines:
        line.voided = True  # frees the agreement period
    ctx.db.flush()
    ctx.db.refresh(invoice)
    if was == "draft":
        _touch_run(ctx, invoice)
    audit.record(
        ctx.db,
        ctx.user,
        "invoice.void",
        invoice,
        before=before,
        after=audit.snapshot(invoice),
        organization_id=invoice.organization_id,
        detail={"was": was, "reason": reason},
    )
    return invoice


# =========================================================================================
# Monthly billing runs
# =========================================================================================
def parse_period(period: str) -> tuple[date, date]:
    year, month = int(period[:4]), int(period[5:7])
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def create_run(ctx: Ctx, period: str) -> BillingRun:
    start, end = parse_period(period)
    t = today(ctx)
    next_month = date(t.year + (t.month == 12), t.month % 12 + 1, 1)
    if start > next_month:
        raise Conflict("Billing runs can be created for the current or next month at most")
    if live_run_for_period(ctx.db, start):
        raise Conflict(f"A billing run for {period} already exists. Cancel it to start over")
    run = BillingRun(
        period_start=start,
        period_end=end,
        status="draft",
        created_by=ctx.user.id if ctx.user else None,
    )
    ctx.db.add(run)
    _flush(ctx, f"A billing run for {period} already exists")
    ctx.db.refresh(run)
    orgs = orgs_with_billables(ctx.db, ctx.scope, start, end)
    run_warnings: list[str] = []
    run_level: list[str] = []  # shown on the run itself (per-invoice ones live on invoices)
    for org in orgs:
        if org.archived_at:
            note = f"{org.name} is archived but has billable items; skipped"
            run_warnings.append(note)
            run_level.append(note)
            continue
        invoice = _new_draft(ctx, org, run=run, period=(start, end))
        warnings = _pull_agreements(ctx, invoice, org, start, end)
        warnings += _pull_time(ctx, invoice, org, end)
        _pull_charges(ctx, invoice, org, end)
        if not invoice_lines(ctx.db, ctx.scope, invoice.id):
            # nothing billable after all (e.g. only rate-less time): keep it visible for review
            invoice.warnings = warnings + ["Nothing could be billed for this organization"]
            invoice.status, invoice.voided_at = "void", now()
            invoice.void_reason = "Nothing to bill"
            ctx.db.flush()
            run_warnings += [f"{org.name}: {w}" for w in invoice.warnings]
            continue
        invoice.warnings = warnings
        recalc(ctx, invoice)
        run_warnings += [f"{org.name}: {w}" for w in warnings]
    run.warnings = run_level
    ctx.db.flush()
    audit.record(
        ctx.db,
        ctx.user,
        "billing_run.create",
        run,
        after=audit.snapshot(run),
        detail={"period": period, "warnings": run_warnings},
    )
    return run


def run_warnings(ctx: Ctx, run: BillingRun) -> list[str]:
    out: list[str] = list(run.warnings or [])
    for inv in run_invoices(ctx.db, ctx.scope, run.id):
        out += [f"{inv.organization.name}: {w}" for w in inv.warnings]
    return out


def review_run(ctx: Ctx, run_id: int) -> BillingRun:
    run = get_run(ctx.db, run_id, lock=True)
    if run is None:
        raise NotFound("Billing run not found")
    if run.status != "draft":
        raise Conflict(f"Run is {run.status}; only a draft run can be marked reviewed")
    live = run_invoices(ctx.db, ctx.scope, run.id, include_void=False)
    if not live:
        raise Conflict("The run has no invoices to review")
    before = audit.snapshot(run)
    run.status, run.reviewed_at = "reviewed", now()
    run.reviewed_by = ctx.user.id if ctx.user else None
    ctx.db.flush()
    audit.record(
        ctx.db,
        ctx.user,
        "billing_run.review",
        run,
        before=before,
        after=audit.snapshot(run),
        detail={"invoices": len(live), "total_cents": sum(i.total_cents for i in live)},
    )
    return run


def finalize_run(ctx: Ctx, run_id: int, invoice_date: date | None) -> BillingRun:
    """All-or-nothing: if any invoice cannot be finalized, NOTHING is (the request rolls back)."""
    run = get_run(ctx.db, run_id, lock=True)
    if run is None:
        raise NotFound("Billing run not found")
    if run.status != "reviewed":
        raise Conflict("Review the run first: only a reviewed run can be finalized")
    before = audit.snapshot(run)
    invoices = run_invoices(ctx.db, ctx.scope, run.id, include_void=False)
    invoices.sort(key=lambda i: (i.organization.name.lower(), i.id))
    for inv in invoices:
        ctx.db.refresh(inv)
        try:
            finalize_invoice(ctx, inv, invoice_date)
        except Conflict as exc:
            raise Conflict(f"{inv.organization.name}: {exc}") from exc
    run.status, run.finalized_at = "finalized", now()
    run.finalized_by = ctx.user.id if ctx.user else None
    ctx.db.flush()
    audit.record(
        ctx.db,
        ctx.user,
        "billing_run.finalize",
        run,
        before=before,
        after=audit.snapshot(run),
        detail={"invoices": [i.number for i in invoices]},
    )
    return run


def cancel_run(ctx: Ctx, run_id: int) -> BillingRun:
    run = get_run(ctx.db, run_id, lock=True)
    if run is None:
        raise NotFound("Billing run not found")
    if run.status not in ("draft", "reviewed"):
        raise Conflict(f"A {run.status} run cannot be cancelled; void its invoices instead")
    before = audit.snapshot(run)
    run.status = "cancelled"  # first, so voiding the drafts doesn't churn the review state
    ctx.db.flush()
    for inv in run_invoices(ctx.db, ctx.scope, run.id, include_void=False):
        void_invoice(ctx, inv.id, "Billing run cancelled")
    audit.record(
        ctx.db, ctx.user, "billing_run.cancel", run, before=before, after=audit.snapshot(run)
    )
    return run
