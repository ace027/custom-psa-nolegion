"""Billing reports. Read-only; every figure is derived from finalized (immutable) records or, for
'unbilled' and 'contracted', from the live open items. Money is integer cents; CSV shows dollars."""

import csv
import io
from calendar import monthrange
from datetime import date

from sqlalchemy import func, or_, select

from app import audit
from app import payment_repo as prepo
from app.billing import today
from app.deps import Ctx
from app.errors import Conflict
from app.models import (
    Agreement,
    Expense,
    Invoice,
    InvoiceLine,
    OrgWorkTypeRate,
    ProductCharge,
    TimeEntry,
    WorkType,
)
from app.money import hours, line_amounts, marked_up
from app.payments import payment_state

KINDS = ("time", "product", "agreement", "manual")


def month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    idx = d.year * 12 + (d.month - 1) + n
    return date(idx // 12, idx % 12 + 1, 1)


def month_end(d: date) -> date:
    return d.replace(day=monthrange(d.year, d.month)[1])


def _months(start: date, end: date) -> list[date]:
    out, cur = [], month_start(start)
    while cur <= end:
        out.append(cur)
        cur = add_months(cur, 1)
    return out


def default_range(ctx: Ctx, start: date | None, end: date | None) -> tuple[date, date]:
    end = end or today(ctx)
    start = start or add_months(month_start(end), -11)
    if start > end:
        raise Conflict("The start date is after the end date")
    if len(_months(start, end)) > 60:
        raise Conflict("Choose a range of 60 months or less")
    return start, end


# ---- revenue ----------------------------------------------------------------------------
def revenue(ctx: Ctx, start: date | None, end: date | None) -> dict:
    """Finalized, non-void invoices by invoice date: by client and by month, split by line kind."""
    start, end = default_range(ctx, start, end)
    month = func.date_trunc("month", Invoice.invoice_date).label("m")
    stmt = ctx.scope.apply(
        select(
            Invoice.organization_id,
            month,
            InvoiceLine.kind,
            func.sum(InvoiceLine.amount_cents),
            func.sum(InvoiceLine.tax_cents),
        )
        .join(InvoiceLine, InvoiceLine.invoice_id == Invoice.id)
        .where(
            Invoice.status == "final",
            InvoiceLine.voided.is_(False),
            Invoice.invoice_date >= start,
            Invoice.invoice_date <= end,
        )
        .group_by(Invoice.organization_id, month, InvoiceLine.kind),
        Invoice.organization_id,
    )
    counts_stmt = ctx.scope.apply(
        select(Invoice.organization_id, month, func.count())
        .where(
            Invoice.status == "final", Invoice.invoice_date >= start, Invoice.invoice_date <= end
        )
        .group_by(Invoice.organization_id, month),
        Invoice.organization_id,
    )

    def blank() -> dict:
        return dict(
            invoices=0,
            tax_cents=0,
            subtotal_cents=0,
            total_cents=0,
            **{k + "_cents": 0 for k in KINDS},
        )

    by_client: dict[int, dict] = {}
    by_month = {m: blank() for m in _months(start, end)}

    def add(bucket: dict, kind: str, amount: int, tax: int) -> None:
        bucket[kind + "_cents"] += amount
        bucket["subtotal_cents"] += amount
        bucket["tax_cents"] += tax
        bucket["total_cents"] += amount + tax

    for org_id, m, kind, amount, tax in ctx.db.execute(stmt):
        c = by_client.setdefault(org_id, blank())
        add(c, kind, int(amount), int(tax))
        add(by_month[m.date()], kind, int(amount), int(tax))
    for org_id, m, n in ctx.db.execute(counts_stmt):
        by_client.setdefault(org_id, blank())["invoices"] += n
        by_month[m.date()]["invoices"] += n
    names = {o.id: o.name for o in _orgs(ctx, list(by_client))}
    clients = sorted(
        (
            {"organization_id": i, "organization_name": names.get(i, f"#{i}"), **v}
            for i, v in by_client.items()
        ),
        key=lambda r: (-r["total_cents"], r["organization_name"].lower()),
    )
    total = blank()
    for row in by_client.values():
        for k, v in row.items():
            total[k] += v
    return dict(
        start=start,
        end=end,
        clients=clients,
        months=[{"month": m, **v} for m, v in sorted(by_month.items())],
        totals=total,
    )


def _orgs(ctx: Ctx, ids: list[int]):
    from app.models import Organization

    if not ids:
        return []
    stmt = ctx.scope.apply(select(Organization).where(Organization.id.in_(ids)), Organization.id)
    return list(ctx.db.execute(stmt).unique().scalars())


# ---- unbilled work ----------------------------------------------------------------------
def unbilled(ctx: Ctx, through: date | None) -> dict:
    """Billable time and one-off charges not yet on an invoice, priced at today's rates."""
    through = through or today(ctx)
    time_rows = ctx.db.execute(
        ctx.scope.apply(
            select(
                TimeEntry.organization_id,
                TimeEntry.work_type_id,
                func.count(),
                func.sum(TimeEntry.minutes_billable),
                func.min(TimeEntry.work_date),
            )
            .where(
                TimeEntry.billable.is_(True),
                TimeEntry.voided_at.is_(None),
                TimeEntry.invoice_line_id.is_(None),
                TimeEntry.minutes_billable > 0,
                TimeEntry.work_date <= through,
            )
            .group_by(TimeEntry.organization_id, TimeEntry.work_type_id),
            TimeEntry.organization_id,
        )
    ).all()
    work_types = {w.id: w for w in ctx.db.execute(select(WorkType)).scalars()}
    overrides = {
        (r.organization_id, r.work_type_id): r.rate_cents
        for r in ctx.db.execute(
            ctx.scope.apply(select(OrgWorkTypeRate), OrgWorkTypeRate.organization_id)
        ).scalars()
    }
    rows: dict[int, dict] = {}

    def row(org_id: int) -> dict:
        return rows.setdefault(
            org_id,
            dict(
                organization_id=org_id,
                time_entries=0,
                billable_minutes=0,
                time_value_cents=0,
                unpriced_minutes=0,
                oldest_work_date=None,
                charges=0,
                charges_cents=0,
                expenses=0,
                expenses_cents=0,
            ),
        )

    for org_id, wt_id, n, minutes, oldest in time_rows:
        r = row(org_id)
        r["time_entries"] += n
        r["billable_minutes"] += int(minutes)
        r["oldest_work_date"] = min(filter(None, [r["oldest_work_date"], oldest]))
        rate = overrides.get((org_id, wt_id), work_types[wt_id].rate_cents)
        if rate is None:
            r["unpriced_minutes"] += int(minutes)
        else:
            r["time_value_cents"] += line_amounts(hours(int(minutes)), rate, 0)[0]
    charges = ctx.db.execute(
        ctx.scope.apply(
            select(ProductCharge).where(
                ProductCharge.invoice_line_id.is_(None),
                ProductCharge.voided_at.is_(None),
                ProductCharge.charged_on <= through,
            ),
            ProductCharge.organization_id,
        )
    ).scalars()
    for c in charges:
        r = row(c.organization_id)
        r["charges"] += 1
        r["charges_cents"] += line_amounts(c.quantity, c.unit_price_cents, 0)[0]
        r["oldest_work_date"] = min(filter(None, [r["oldest_work_date"], c.charged_on]))
    for x in ctx.db.execute(
        ctx.scope.apply(
            select(Expense).where(
                Expense.billable.is_(True),
                Expense.invoice_line_id.is_(None),
                Expense.voided_at.is_(None),
                Expense.expense_date <= through,
            ),
            Expense.organization_id,
        )
    ).scalars():
        r = row(x.organization_id)
        r["expenses"] += 1
        r["expenses_cents"] += marked_up(x.amount_cents, x.markup_bp)
        r["oldest_work_date"] = min(filter(None, [r["oldest_work_date"], x.expense_date]))
    names = {o.id: o.name for o in _orgs(ctx, list(rows))}
    out = sorted(
        (
            {
                **v,
                "organization_name": names.get(i, f"#{i}"),
                "total_cents": v["time_value_cents"] + v["charges_cents"] + v["expenses_cents"],
            }
            for i, v in rows.items()
        ),
        key=lambda r: (-r["total_cents"], r["organization_name"].lower()),
    )
    keys = (
        "time_entries",
        "billable_minutes",
        "time_value_cents",
        "unpriced_minutes",
        "charges",
        "charges_cents",
        "expenses",
        "expenses_cents",
        "total_cents",
    )
    return dict(through=through, rows=out, totals={k: sum(r[k] for r in out) for k in keys})


# ---- recurring revenue ------------------------------------------------------------------
def recurring(ctx: Ctx, months: int) -> dict:
    """Per month: what agreements *contract* for it (current quantity and price, the same rule the
    monthly run uses) and what was actually *invoiced* on agreement lines for that period."""
    if not 1 <= months <= 36:
        raise Conflict("Choose between 1 and 36 months")
    end_month = month_start(today(ctx))
    first = add_months(end_month, -(months - 1))
    agreements = list(
        ctx.db.execute(
            ctx.scope.apply(
                select(Agreement).where(
                    Agreement.start_date <= month_end(end_month),
                    or_(Agreement.end_date.is_(None), Agreement.end_date >= first),
                ),
                Agreement.organization_id,
            )
        )
        .unique()
        .scalars()
    )
    pm = func.date_trunc("month", InvoiceLine.period_start).label("m")
    invoiced = {
        m.date(): (int(total), n)
        for m, total, n in ctx.db.execute(
            ctx.scope.apply(
                select(
                    pm,
                    func.sum(InvoiceLine.amount_cents),
                    func.count(func.distinct(Invoice.organization_id)),
                )
                .join(Invoice, Invoice.id == InvoiceLine.invoice_id)
                .where(
                    Invoice.status == "final",
                    InvoiceLine.kind == "agreement",
                    InvoiceLine.voided.is_(False),
                    InvoiceLine.period_start >= first,
                    InvoiceLine.period_start <= month_end(end_month),
                )
                .group_by(pm),
                Invoice.organization_id,
            )
        )
    }
    out = []
    for m in _months(first, end_month):
        last = month_end(m)
        live = [
            a
            for a in agreements
            if a.start_date <= last and (a.end_date is None or a.end_date >= m)
        ]
        contracted = sum(a.quantity * a.unit_price_cents for a in live)
        billed, clients = invoiced.get(m, (0, 0))
        out.append(
            dict(
                month=m,
                contracted_cents=contracted,
                agreements=len(live),
                clients=len({a.organization_id for a in live if a.quantity > 0}),
                invoiced_cents=billed,
            )
        )
    return dict(months=out)


# ---- invoice export ---------------------------------------------------------------------
def invoice_rows(ctx: Ctx, start: date | None, end: date | None) -> list[dict]:
    """Every finalized or voided invoice with an invoice date in range, oldest first."""
    start, end = default_range(ctx, start, end)
    stmt = ctx.scope.apply(
        select(Invoice).where(
            Invoice.status.in_(("final", "void")),
            Invoice.invoice_date >= start,
            Invoice.invoice_date <= end,
        ),
        Invoice.organization_id,
    )
    invoices = list(
        ctx.db.execute(stmt.order_by(Invoice.invoice_date, Invoice.id)).unique().scalars()
    )
    amounts = prepo.amounts_for(ctx.db, [i.id for i in invoices])
    on = today(ctx)
    out = []
    for inv in invoices:
        st = payment_state(inv, *amounts[inv.id], on)
        out.append(
            dict(
                number=inv.number,
                client=inv.organization.name,
                status=inv.status,
                invoice_date=inv.invoice_date,
                due_date=inv.due_date,
                subtotal_cents=inv.subtotal_cents,
                tax_cents=inv.tax_cents,
                total_cents=inv.total_cents,
                paid_cents=st["paid_cents"],
                written_off_cents=st["written_off_cents"],
                balance_cents=st["balance_cents"],
                payment_status=st["payment_status"],
                void_reason=inv.void_reason,
            )
        )
    return out


# ---- CSV --------------------------------------------------------------------------------
def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    text = str(value)
    # a spreadsheet would run a cell that starts like a formula: neutralise it (client-controlled)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def dollars(cents: int | None) -> str:
    if cents is None:
        return ""
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) // 100}.{abs(cents) % 100:02d}"


def to_csv(header: list[str], rows: list[list], money_cols: set[int] = frozenset()) -> str:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(header)
    for r in rows:
        w.writerow([dollars(v) if i in money_cols else _cell(v) for i, v in enumerate(r)])
    return buf.getvalue()


def record_export(ctx: Ctx, report: str, params: dict, rows: int) -> None:
    audit.record(
        ctx.db,
        ctx.user,
        "report.export",
        detail={"report": report, "params": {k: str(v) for k, v in params.items()}, "rows": rows},
    )
