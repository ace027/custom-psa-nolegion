"""Management report metrics: SLA performance, utilisation, receivables aging, profitability.

Read-only. Money is integer cents, percentages are integer basis points (bp), durations are
whole minutes. Dates are business time zone dates (Settings.timezone).

METRIC DICTIONARY (the definitions agreed in the Phase 11 CONTEXT)

Percentages: bp = round_half_up(numerator * 10000 / denominator); null when the denominator is 0.
Durations: p50 / p90 by nearest rank on the sorted list (rank = ceil(q * n), 1-based); null when
there are no values.

SLA performance (by priority, organization or assignee)
  Population  tickets created in the range (business time zone dates).
  First response  the response time is first_responded_at, else the resolution time (resolving a
    ticket ends its first-response clock; owner decision 2026-11-02). met: response <=
    sla_first_response_due. breached: response > due, or no response and now > due. pending: no
    response and not yet due. no_sla: the ticket has no due date. met_bp = met / (met +
    breached); pending and no_sla are counted separately and are not in the percentage.
  Resolution  the same with resolved_at (closed_at when resolved_at is null) against
    sla_resolution_due.
  Durations  business minutes (sla.business_minutes_between with the SLA calendar) from created_at
    to the first response / to resolution; the resolution duration minus sla_paused_minutes,
    floored at 0.

Utilisation (per staff user)
  capacity_minutes  for each date in the range that is not a holiday: the user's working hours
    for that weekday (UserWorkHours, else the business hours in Settings), minus approved time off
    overlapping that day's working window.
  logged_minutes  minutes_actual of non-voided time entries (work_date in range) plus non-voided
    internal time entries.
  billable_minutes  minutes_actual of non-voided time entries flagged billable.
  automation_minutes  non-voided entry_type 'automation' minutes_actual, reported on their own
    (owner decision 2026-10-30): never in logged, billable, utilisation or labour cost.
  utilisation_bp = logged / capacity; billable_bp = billable / capacity.
  Users listed: active users who may log time, plus anyone who logged time in the range.

Aging  payments.receivables: open balance of finalized invoices (total minus active payment
  applications, write-offs and credit memo applications) in buckets of days past the due date,
  plus unused client credit. As of today (business time zone).

Profitability (per client)
  revenue  exactly reports.revenue(range).subtotal_cents (finalized, non-void invoices, non-voided
    lines, amount excluding tax, by invoice date).
  labour cost  per non-voided time entry (work_date in range) round_cents(minutes_actual *
    users.cost_rate_cents / 60), summed per entry. A user without a cost rate counts as 0 and the
    minutes are reported in minutes_without_cost_rate.
  goods cost  inventory items delivered to the client in range (delivered_on): quantity *
    unit_cost_cents; plus non-voided product charges dated in range that no inventory item points
    to and whose product has a cost: round_cents(quantity * products.cost_cents). Such charges
    without a known cost are counted in charges_without_cost.
  expense cost  amount_cents of the client's non-voided expenses dated in range.
  cost = labour + goods + expenses; margin = revenue - cost; margin_bp = margin / revenue, null
  when revenue <= 0. Internal time is not attributed to clients.

By agreement (group='agreement', Phase 17; docs/REPORTS.md)
  rows per (client, agreement) plus a 'No agreement' row per client. Revenue: lines carrying an
  agreement_id, plus lines holding time entries attached to it (split by billed minutes when the
  entries differ). Labour cost: time attached to it. Goods and expenses: 'No agreement'. The rows
  add up to the client view to the cent. Utilisation adds ticket minutes per agreement.

Lineage: tickets, time_entries, internal_time_entries, user_work_hours, user_time_off, holidays,
settings, invoices/invoice_lines (through reports.revenue), payments/payment_applications/
write_offs/credit_memo_applications (through payments.receivables), inventory_items,
product_charges, products, expenses, users.cost_rate_cents.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select

from app import availability, reports
from app import permissions as P
from app import repositories as repo
from app.deps import Ctx
from app.errors import Conflict
from app.models import (
    Agreement,
    Expense,
    Holiday,
    InternalTimeEntry,
    InventoryItem,
    Invoice,
    InvoiceLine,
    Organization,
    Priority,
    Product,
    ProductCharge,
    PurchaseOrderLine,
    Ticket,
    TimeEntry,
    User,
    UserTimeOff,
    UserWorkHours,
)
from app.money import round_cents
from app.payments import receivables
from app.sla import business_minutes_between
from app.ticket_services import calendar, now

SlaGroup = Literal["priority", "organization", "assignee"]
ProfitGroup = Literal["client", "agreement"]
NO_AGREEMENT = "No agreement"
RowKey = tuple[int, int | None]  # (organization_id, agreement_id); None = 'No agreement'
REPORTS = ("sla", "utilisation", "aging", "profitability")


# ---- shared helpers ---------------------------------------------------------------------
def bp(numerator: int, denominator: int) -> int | None:
    """Basis points, round half up; None when the denominator is 0."""
    if denominator == 0:
        return None
    return round_cents(Decimal(numerator) * 10000 / Decimal(denominator))


def percentile(sorted_values: list[int], q: int) -> int | None:
    """Nearest rank: the value at 1-based rank ceil(q/100 * n); None for an empty list."""
    n = len(sorted_values)
    if n == 0:
        return None
    return sorted_values[max(1, -(-q * n // 100)) - 1]


def _bounds(start: date, end: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """[start, end] as local dates -> a half-open [lo, hi) interval of aware datetimes."""
    lo = datetime(start.year, start.month, start.day, tzinfo=tz)
    nxt = end + timedelta(days=1)
    return lo, datetime(nxt.year, nxt.month, nxt.day, tzinfo=tz)


def _names(ctx: Ctx, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    stmt = ctx.scope.apply(
        select(Organization.id, Organization.name).where(Organization.id.in_(ids)),
        Organization.id,
    )
    return {i: n for i, n in ctx.db.execute(stmt)}


def _check_group(group: str) -> None:
    if group not in ("client", "agreement"):
        raise Conflict("Group by client or agreement")


def _agreement_fields(ctx: Ctx, keys) -> dict[RowKey, dict]:
    """(organization_id, agreement_id or None) -> the row's client and agreement identity."""
    orgs = _names(ctx, {o for o, _ in keys})
    aids = {a for _, a in keys if a is not None}
    agreements = {}
    if aids:
        stmt = ctx.scope.apply(
            select(Agreement.id, Agreement.name, Agreement.type).where(Agreement.id.in_(aids)),
            Agreement.organization_id,
        )
        agreements = {i: (n, t) for i, n, t in ctx.db.execute(stmt)}
    out = {}
    for o, a in keys:
        name, kind = agreements.get(a, (f"#{a}", None)) if a is not None else (NO_AGREEMENT, None)
        out[(o, a)] = dict(
            organization_id=o,
            organization_name=orgs.get(o, f"#{o}"),
            agreement_id=a,
            agreement_name=name,
            agreement_type=kind,
        )
    return out


def _agreement_order(r: dict) -> tuple:
    """Client by name, then its agreements by name, 'No agreement' last."""
    return (
        r["organization_name"].lower(),
        r["organization_id"],
        r["agreement_id"] is None,
        r["agreement_name"].lower(),
        r["agreement_id"] or 0,
    )


# ---- SLA --------------------------------------------------------------------------------
class _Clock:
    """Tallies one SLA clock (first response or resolution) for a group of tickets."""

    def __init__(self) -> None:
        self.met = self.breached = self.pending = self.no_sla = 0
        self.durations: list[int] = []

    def add(self, due: datetime | None, end: datetime | None, at: datetime) -> None:
        if due is None:
            self.no_sla += 1
        elif end is not None:
            if end <= due:
                self.met += 1
            else:
                self.breached += 1
        elif at > due:
            self.breached += 1
        else:
            self.pending += 1

    def out(self) -> dict:
        d = sorted(self.durations)
        return dict(
            met=self.met,
            breached=self.breached,
            pending=self.pending,
            no_sla=self.no_sla,
            met_bp=bp(self.met, self.met + self.breached),
            p50_minutes=percentile(d, 50),
            p90_minutes=percentile(d, 90),
        )


class _Group:
    def __init__(self, key: int | None, label: str, order) -> None:
        self.key, self.label, self.order = key, label, order
        self.n = 0
        self.first_response = _Clock()
        self.resolution = _Clock()

    def out(self) -> dict:
        return dict(
            key=self.key,
            label=self.label,
            n=self.n,
            first_response=self.first_response.out(),
            resolution=self.resolution.out(),
        )


def sla(ctx: Ctx, start: date | None, end: date | None, group: SlaGroup = "priority") -> dict:
    if group not in ("priority", "organization", "assignee"):
        raise Conflict("Group by priority, organization or assignee")
    start, end = reports.default_range(ctx, start, end)
    cal = calendar(ctx)
    lo, hi = _bounds(start, end, cal.tz)
    at = now()
    stmt = ctx.scope.apply(
        select(
            Ticket.organization_id,
            Ticket.priority_id,
            Ticket.assignee_id,
            Ticket.created_at,
            Ticket.sla_first_response_due,
            Ticket.sla_resolution_due,
            Ticket.first_responded_at,
            Ticket.resolved_at,
            Ticket.closed_at,
            Ticket.sla_paused_minutes,
            Priority.name,
            Priority.rank,
            Organization.name,
            User.display_name,
        )
        .join(Priority, Priority.id == Ticket.priority_id)
        .outerjoin(Organization, Organization.id == Ticket.organization_id)
        .outerjoin(User, User.id == Ticket.assignee_id)
        .where(Ticket.created_at >= lo, Ticket.created_at < hi),
        Ticket.organization_id,
    )
    groups: dict[int | None, _Group] = {}
    total = _Group(None, "Total", 0)
    for r in ctx.db.execute(stmt):
        org_id, prio_id, assignee_id, created, fr_due, res_due = r[:6]
        responded, resolved, closed, paused, prio_name, prio_rank, org_name, user_name = r[6:]
        if group == "priority":
            key, label, order = prio_id, prio_name, (prio_rank, prio_name.lower())
        elif group == "organization":
            key, label = org_id, org_name or "No client"
            order = (1 if org_id is None else 0, label.lower())
        else:
            key, label = assignee_id, user_name or "Unassigned"
            order = (1 if assignee_id is None else 0, label.lower())
        g = groups.setdefault(key, _Group(key, label, order))
        res_end = resolved or closed
        # Resolving a ticket also ends its first-response clock (owner decision 2026-11-02).
        responded = responded or res_end
        for bucket in (g, total):
            bucket.n += 1
            bucket.first_response.add(fr_due, responded, at)
            bucket.resolution.add(res_due, res_end, at)
            if responded is not None:
                bucket.first_response.durations.append(
                    business_minutes_between(created, responded, cal)
                )
            if res_end is not None:
                bucket.resolution.durations.append(
                    max(0, business_minutes_between(created, res_end, cal) - paused)
                )
    rows = [g.out() for g in sorted(groups.values(), key=lambda g: g.order)]
    totals = total.out()
    totals.pop("key"), totals.pop("label")
    return dict(range=dict(start=start, end=end), group=group, rows=rows, totals=totals)


# ---- utilisation ------------------------------------------------------------------------
def _zone(user_tz: str | None, settings_tz: str) -> ZoneInfo:
    for name in (user_tz, settings_tz):
        if not name:
            continue
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            continue
    return ZoneInfo("UTC")


def _minutes_by_agreement(ctx: Ctx, start: date, end: date) -> list[dict]:
    """Ticket time per (client, agreement): labour logged and billable minutes, automation minutes
    on their own. Internal time belongs to no client, so it is not in these rows."""
    labour = TimeEntry.entry_type == "labour"
    stmt = ctx.scope.apply(
        select(
            TimeEntry.organization_id,
            TimeEntry.agreement_id,
            func.coalesce(func.sum(TimeEntry.minutes_actual).filter(labour), 0),
            func.coalesce(
                func.sum(TimeEntry.minutes_actual).filter(labour, TimeEntry.billable.is_(True)), 0
            ),
            func.coalesce(
                func.sum(TimeEntry.minutes_actual).filter(TimeEntry.entry_type == "automation"), 0
            ),
        )
        .where(
            TimeEntry.entry_type.in_(("labour", "automation")),
            TimeEntry.voided_at.is_(None),
            TimeEntry.work_date >= start,
            TimeEntry.work_date <= end,
        )
        .group_by(TimeEntry.organization_id, TimeEntry.agreement_id),
        TimeEntry.organization_id,
    )
    sums = {(o, a): (int(lg), int(bl), int(au)) for o, a, lg, bl, au in ctx.db.execute(stmt)}
    fields = _agreement_fields(ctx, sums)
    rows = [
        dict(**fields[k], logged_minutes=lg, billable_minutes=bl, automation_minutes=au)
        for k, (lg, bl, au) in sums.items()
    ]
    return sorted(rows, key=_agreement_order)


def utilisation(
    ctx: Ctx, start: date | None, end: date | None, group: ProfitGroup = "client"
) -> dict:
    _check_group(group)
    start, end = reports.default_range(ctx, start, end)
    db = ctx.db
    settings = repo.get_settings_row(db)

    logged: dict[int, int] = defaultdict(int)
    billable: dict[int, int] = defaultdict(int)
    automation: dict[int, int] = defaultdict(int)
    te = ctx.scope.apply(
        select(
            TimeEntry.user_id,
            func.sum(TimeEntry.minutes_actual),
            func.sum(TimeEntry.minutes_actual).filter(TimeEntry.billable.is_(True)),
        )
        .where(
            # owner decision 2026-10-30: utilisation counts labour only
            TimeEntry.entry_type == "labour",
            TimeEntry.voided_at.is_(None),
            TimeEntry.work_date >= start,
            TimeEntry.work_date <= end,
        )
        .group_by(TimeEntry.user_id),
        TimeEntry.organization_id,
    )
    for uid, minutes, bill in db.execute(te):
        logged[uid] += int(minutes or 0)
        billable[uid] += int(bill or 0)
    auto = ctx.scope.apply(
        select(TimeEntry.user_id, func.sum(TimeEntry.minutes_actual))
        .where(
            TimeEntry.entry_type == "automation",
            TimeEntry.voided_at.is_(None),
            TimeEntry.work_date >= start,
            TimeEntry.work_date <= end,
        )
        .group_by(TimeEntry.user_id),
        TimeEntry.organization_id,
    )
    for uid, minutes in db.execute(auto):
        automation[uid] += int(minutes or 0)
    internal = (
        select(InternalTimeEntry.user_id, func.sum(InternalTimeEntry.minutes))
        .where(
            InternalTimeEntry.voided_at.is_(None),
            InternalTimeEntry.work_date >= start,
            InternalTimeEntry.work_date <= end,
        )
        .group_by(InternalTimeEntry.user_id)
    )
    for uid, minutes in db.execute(internal):
        logged[uid] += int(minutes or 0)

    users = [
        u
        for u in db.execute(
            select(User.id, User.display_name, User.timezone, User.role, User.is_active)
        )
        if u.id in logged
        or u.id in automation
        or (u.is_active and P.has_permission(u.role, P.TIME_WRITE))
    ]
    hours: dict[int, dict[int, tuple[int, int]]] = defaultdict(dict)
    for uid, weekday, s, e in db.execute(
        select(
            UserWorkHours.user_id,
            UserWorkHours.weekday,
            UserWorkHours.start_minute,
            UserWorkHours.end_minute,
        )
    ):
        hours[uid][weekday] = (s, e)
    default_week = availability.default_weekly(settings)
    # every holiday date is a non-working day for capacity (the CONTEXT rule)
    closed = {
        d: None
        for d in db.execute(
            select(Holiday.on_date).where(
                Holiday.on_date >= start - timedelta(days=1),
                Holiday.on_date <= end + timedelta(days=1),
            )
        ).scalars()
    }
    wide_lo = datetime.combine(start - timedelta(days=2), datetime.min.time(), ZoneInfo("UTC"))
    wide_hi = datetime.combine(end + timedelta(days=3), datetime.min.time(), ZoneInfo("UTC"))
    time_off: dict[int, list[tuple[datetime, datetime]]] = defaultdict(list)
    for uid, s, e in db.execute(
        select(UserTimeOff.user_id, UserTimeOff.starts_at, UserTimeOff.ends_at).where(
            UserTimeOff.status == "approved",
            UserTimeOff.starts_at < wide_hi,
            UserTimeOff.ends_at > wide_lo,
        )
    ):
        time_off[uid].append((s, e))

    rows = []
    for u in users:
        tz = _zone(u.timezone, settings.timezone)
        lo, hi = _bounds(start, end, tz)
        windows = availability.free_windows(
            lo, hi, tz, hours.get(u.id) or default_week, closed, time_off.get(u.id, [])
        )
        capacity = int(sum((b - a).total_seconds() for a, b in windows) // 60)
        rows.append(
            dict(
                user_id=u.id,
                name=u.display_name,
                capacity_minutes=capacity,
                logged_minutes=logged.get(u.id, 0),
                billable_minutes=billable.get(u.id, 0),
                automation_minutes=automation.get(u.id, 0),
                utilisation_bp=bp(logged.get(u.id, 0), capacity),
                billable_bp=bp(billable.get(u.id, 0), capacity),
            )
        )
    rows.sort(key=lambda r: (r["name"].lower(), r["user_id"]))
    cap = sum(r["capacity_minutes"] for r in rows)
    log_ = sum(r["logged_minutes"] for r in rows)
    bil = sum(r["billable_minutes"] for r in rows)
    auto_total = sum(r["automation_minutes"] for r in rows)
    totals = dict(
        capacity_minutes=cap,
        logged_minutes=log_,
        billable_minutes=bil,
        automation_minutes=auto_total,
        utilisation_bp=bp(log_, cap),
        billable_bp=bp(bil, cap),
    )
    agreements = _minutes_by_agreement(ctx, start, end) if group == "agreement" else None
    return dict(
        range=dict(start=start, end=end),
        group=group,
        rows=rows,
        totals=totals,
        agreements=agreements,
    )


# ---- aging ------------------------------------------------------------------------------
def aging(ctx: Ctx) -> dict:
    d = receivables(ctx)
    return dict(as_of=d["as_of"], rows=d["rows"], totals=d["totals"])


# ---- profitability ----------------------------------------------------------------------
def _split(amount: int, weights: dict) -> dict:
    """Split amount cents in proportion to weights; the rounding remainder goes to the largest
    weight, so the shares always add up to amount exactly."""
    total = sum(weights.values())
    shares = {k: amount * w // total for k, w in weights.items()}
    shares[max(weights, key=weights.__getitem__)] += amount - sum(shares.values())
    return shares


def _revenue_by_agreement(ctx: Ctx, start: date, end: date) -> dict[RowKey, int]:
    """The same lines as reports.revenue (finalized, non-void invoices in range, non-voided
    lines, excluding tax) keyed by (client, agreement). A line with an agreement_id is that
    agreement's (agreement fees, block lines, prorations); any other line with time entries on it
    goes to the agreement of those entries, split by billed minutes when they differ; everything
    else (manual, product, project lines) is the client's 'No agreement' revenue."""
    in_range = (
        Invoice.status == "final",
        InvoiceLine.voided.is_(False),
        Invoice.invoice_date >= start,
        Invoice.invoice_date <= end,
    )
    lines = ctx.scope.apply(
        select(
            InvoiceLine.id,
            Invoice.organization_id,
            InvoiceLine.agreement_id,
            InvoiceLine.amount_cents,
        )
        .join(Invoice, Invoice.id == InvoiceLine.invoice_id)
        .where(*in_range),
        Invoice.organization_id,
    )
    billed = TimeEntry.minutes_billable - TimeEntry.block_minutes_covered
    time_on_lines = ctx.scope.apply(
        select(
            TimeEntry.invoice_line_id,
            TimeEntry.agreement_id,
            func.sum(billed),
            func.count(),
        )
        .join(InvoiceLine, InvoiceLine.id == TimeEntry.invoice_line_id)
        .join(Invoice, Invoice.id == InvoiceLine.invoice_id)
        .where(*in_range, InvoiceLine.agreement_id.is_(None))
        .group_by(TimeEntry.invoice_line_id, TimeEntry.agreement_id)
        .order_by(TimeEntry.invoice_line_id, TimeEntry.agreement_id.nulls_last()),
        Invoice.organization_id,
    )
    minutes: dict[int, dict[int | None, int]] = defaultdict(dict)
    counts: dict[int, dict[int | None, int]] = defaultdict(dict)
    for line_id, aid, m, n in ctx.db.execute(time_on_lines):
        minutes[line_id][aid] = int(m or 0)
        counts[line_id][aid] = n
    revenue: dict[RowKey, int] = defaultdict(int)
    for line_id, org_id, aid, amount in ctx.db.execute(lines):
        if aid is not None or line_id not in minutes:
            revenue[(org_id, aid)] += amount
            continue
        weights = minutes[line_id] if sum(minutes[line_id].values()) > 0 else counts[line_id]
        for entry_aid, share in _split(amount, weights).items():
            revenue[(org_id, entry_aid)] += share
    return revenue


def profitability(
    ctx: Ctx, start: date | None, end: date | None, group: ProfitGroup = "client"
) -> dict:
    """group 'client': one row per client. group 'agreement': one row per (client, agreement)
    plus a 'No agreement' row per client; the rows add up to the client view to the cent."""
    _check_group(group)
    by_agreement = group == "agreement"
    start, end = reports.default_range(ctx, start, end)
    db = ctx.db
    if by_agreement:
        revenue: dict[RowKey, int] = _revenue_by_agreement(ctx, start, end)
    else:
        revenue = {
            (c["organization_id"], None): c["subtotal_cents"]
            for c in reports.revenue(ctx, start, end)["clients"]
        }
    labour: dict[RowKey, int] = defaultdict(int)
    no_rate: dict[RowKey, int] = defaultdict(int)
    # shortcut: goods and expenses are never on an agreement's invoice line today, so they stay
    # in the client's 'No agreement' row; attribute them if billing ever ties them to one.
    goods: dict[RowKey, int] = defaultdict(int)
    expenses: dict[RowKey, int] = defaultdict(int)
    no_cost: dict[RowKey, int] = defaultdict(int)

    # one row per distinct (minutes, rate): the rounding is still applied per entry
    time_rows = ctx.scope.apply(
        select(
            TimeEntry.organization_id,
            TimeEntry.agreement_id,
            TimeEntry.minutes_actual,
            User.cost_rate_cents,
            func.count(),
        )
        .join(User, User.id == TimeEntry.user_id)
        .where(
            # owner decision 2026-10-30: labour cost counts labour entries only
            TimeEntry.entry_type == "labour",
            TimeEntry.voided_at.is_(None),
            TimeEntry.work_date >= start,
            TimeEntry.work_date <= end,
        )
        .group_by(
            TimeEntry.organization_id,
            TimeEntry.agreement_id,
            TimeEntry.minutes_actual,
            User.cost_rate_cents,
        ),
        TimeEntry.organization_id,
    )
    for org_id, aid, minutes, rate, n in db.execute(time_rows):
        key = (org_id, aid if by_agreement else None)
        if rate is None:
            no_rate[key] += minutes * n
        else:
            labour[key] += round_cents(Decimal(minutes) * rate / 60) * n

    item_rows = ctx.scope.apply(
        select(
            InventoryItem.organization_id,
            func.sum(InventoryItem.quantity * InventoryItem.unit_cost_cents),
        )
        .where(
            InventoryItem.organization_id.is_not(None),
            InventoryItem.delivered_on >= start,
            InventoryItem.delivered_on <= end,
        )
        .group_by(InventoryItem.organization_id),
        InventoryItem.organization_id,
    )
    for org_id, cost in db.execute(item_rows):
        goods[(org_id, None)] += int(cost)

    charge_rows = ctx.scope.apply(
        select(
            ProductCharge.organization_id,
            ProductCharge.quantity,
            Product.cost_cents,
            func.count(),
        )
        .outerjoin(Product, Product.id == ProductCharge.product_id)
        .where(
            ProductCharge.voided_at.is_(None),
            ProductCharge.charged_on >= start,
            ProductCharge.charged_on <= end,
            ~select(InventoryItem.id)
            .where(InventoryItem.product_charge_id == ProductCharge.id)
            .exists(),
            # billed at PO order: its goods cost is counted per item at delivery above
            ~select(PurchaseOrderLine.id)
            .where(PurchaseOrderLine.product_charge_id == ProductCharge.id)
            .exists(),
        )
        .group_by(ProductCharge.organization_id, ProductCharge.quantity, Product.cost_cents),
        ProductCharge.organization_id,
    )
    for org_id, qty, unit_cost, n in db.execute(charge_rows):
        if unit_cost is None:
            no_cost[(org_id, None)] += n
        else:
            goods[(org_id, None)] += round_cents(Decimal(qty) * unit_cost) * n

    expense_rows = ctx.scope.apply(
        select(Expense.organization_id, func.sum(Expense.amount_cents))
        .where(
            Expense.organization_id.is_not(None),
            Expense.voided_at.is_(None),
            Expense.expense_date >= start,
            Expense.expense_date <= end,
        )
        .group_by(Expense.organization_id),
        Expense.organization_id,
    )
    for org_id, amount in db.execute(expense_rows):
        expenses[(org_id, None)] += int(amount)

    keys = set(revenue) | set(labour) | set(no_rate) | set(goods) | set(expenses) | set(no_cost)
    if by_agreement:
        fields = _agreement_fields(ctx, keys)
    else:
        names = _names(ctx, {o for o, _ in keys})
        fields = {
            (o, a): dict(
                organization_id=o,
                organization_name=names.get(o, f"#{o}"),
                agreement_id=None,
                agreement_name=None,
                agreement_type=None,
            )
            for o, a in keys
        }
    rows = []
    for i in keys:
        cost = labour[i] + goods[i] + expenses[i]
        rev = revenue.get(i, 0)
        rows.append(
            dict(
                **fields[i],
                revenue_cents=rev,
                labour_cost_cents=labour[i],
                goods_cost_cents=goods[i],
                expense_cost_cents=expenses[i],
                cost_cents=cost,
                margin_cents=rev - cost,
                margin_bp=bp(rev - cost, rev) if rev > 0 else None,
                minutes_without_cost_rate=no_rate[i],
                charges_without_cost=no_cost[i],
            )
        )
    if by_agreement:
        rows.sort(key=_agreement_order)
    else:
        rows.sort(key=lambda r: (-r["revenue_cents"], r["organization_name"].lower()))
    sums = {
        k: sum(r[k] for r in rows)
        for k in (
            "revenue_cents",
            "labour_cost_cents",
            "goods_cost_cents",
            "expense_cost_cents",
            "cost_cents",
            "margin_cents",
            "minutes_without_cost_rate",
            "charges_without_cost",
        )
    }
    sums["margin_bp"] = (
        bp(sums["margin_cents"], sums["revenue_cents"]) if sums["revenue_cents"] > 0 else None
    )
    return dict(range=dict(start=start, end=end), group=group, rows=rows, totals=sums)


# ---- CSV --------------------------------------------------------------------------------
def pct(value: int | None) -> str:
    """Basis points as '87.50%'. A negative value is written '(12.50%)': a leading minus would be
    neutralised by the spreadsheet formula guard in reports.to_csv."""
    if value is None:
        return ""
    text = f"{abs(value) // 100}.{abs(value) % 100:02d}%"
    return f"({text})" if value < 0 else text


def _sla_csv(d: dict) -> tuple[list[str], list[list], set[int]]:
    header = ["group", "tickets"]
    for clock in ("first_response", "resolution"):
        header += [
            f"{clock}_met",
            f"{clock}_breached",
            f"{clock}_pending",
            f"{clock}_no_sla",
            f"{clock}_met_pct",
            f"{clock}_p50_minutes",
            f"{clock}_p90_minutes",
        ]

    def line(label: str, n: int, row: dict) -> list:
        out: list = [label, n]
        for clock in ("first_response", "resolution"):
            c = row[clock]
            out += [
                c["met"],
                c["breached"],
                c["pending"],
                c["no_sla"],
                pct(c["met_bp"]),
                c["p50_minutes"],
                c["p90_minutes"],
            ]
        return out

    rows = [line(r["label"], r["n"], r) for r in d["rows"]]
    rows.append(line("Total", sum(r["n"] for r in d["rows"]), d["totals"]))
    return header, rows, set()


def _utilisation_csv(d: dict) -> tuple[list[str], list[list], set[int]]:
    if d["agreements"] is not None:
        keys = ["logged_minutes", "billable_minutes", "automation_minutes"]
        rows = [
            [r["organization_name"], r["agreement_name"], r["agreement_type"]]
            + [r[k] for k in keys]
            for r in d["agreements"]
        ]
        rows.append(["Total", "", ""] + [sum(r[k] for r in d["agreements"]) for k in keys])
        return ["client", "agreement", "agreement_type", *keys], rows, set()
    header = [
        "user",
        "capacity_minutes",
        "logged_minutes",
        "billable_minutes",
        "utilisation_pct",
        "billable_pct",
        "automation_minutes",
    ]

    def line(name: str, r: dict) -> list:
        return [
            name,
            r["capacity_minutes"],
            r["logged_minutes"],
            r["billable_minutes"],
            pct(r["utilisation_bp"]),
            pct(r["billable_bp"]),
            r["automation_minutes"],
        ]

    rows = [line(r["name"], r) for r in d["rows"]] + [line("Total", d["totals"])]
    return header, rows, set()


def _aging_csv(d: dict) -> tuple[list[str], list[list], set[int]]:
    header = [
        "client",
        "current",
        "1-30",
        "31-60",
        "61-90",
        "90+",
        "total_open",
        "credit",
        "open_invoices",
        "overdue_invoices",
        "oldest_days_past_due",
    ]
    rows = [
        [
            r["organization_name"],
            r["current_cents"],
            r["d1_30_cents"],
            r["d31_60_cents"],
            r["d61_90_cents"],
            r["d90_plus_cents"],
            r["total_open_cents"],
            r["credit_cents"],
            r["open_invoice_count"],
            r["overdue_invoice_count"],
            r["oldest_days_past_due"],
        ]
        for r in d["rows"] + [d["totals"]]
    ]
    return header, rows, set(range(1, 8))


def _profitability_csv(d: dict) -> tuple[list[str], list[list], set[int]]:
    header = [
        "revenue",
        "labour_cost",
        "goods_cost",
        "expense_cost",
        "cost",
        "margin",
        "margin_pct",
        "minutes_without_cost_rate",
        "charges_without_cost",
    ]

    def line(r: dict) -> list:
        return [
            r["revenue_cents"],
            r["labour_cost_cents"],
            r["goods_cost_cents"],
            r["expense_cost_cents"],
            r["cost_cents"],
            r["margin_cents"],
            pct(r["margin_bp"]),
            r["minutes_without_cost_rate"],
            r["charges_without_cost"],
        ]

    if d["group"] == "agreement":
        rows = [
            [r["organization_name"], r["agreement_name"], r["agreement_type"]] + line(r)
            for r in d["rows"]
        ]
        rows.append(["Total", "", ""] + line(d["totals"]))
        return ["client", "agreement", "agreement_type", *header], rows, set(range(3, 9))
    rows = [[r["organization_name"]] + line(r) for r in d["rows"]]
    rows.append(["Total"] + line(d["totals"]))
    return ["client", *header], rows, set(range(1, 7))


def csv_for(
    ctx: Ctx,
    report: str,
    start: date | None,
    end: date | None,
    group: SlaGroup = "priority",
    by: ProfitGroup = "client",
) -> tuple[str, str]:
    """(filename, CSV text) for one report; used by the routes and the scheduled emails.
    group applies to sla; by (client or agreement) to utilisation and profitability."""
    if report == "aging":
        d = aging(ctx)
        name = f"aging-{d['as_of']}.csv"
        header, rows, money = _aging_csv(d)
    elif report in ("sla", "utilisation", "profitability"):
        if report == "sla":
            d = sla(ctx, start, end, group)
            header, rows, money = _sla_csv(d)
            tag = f"sla-by-{group}"
        elif report == "utilisation":
            d = utilisation(ctx, start, end, by)
            header, rows, money = _utilisation_csv(d)
            tag = report if by == "client" else f"{report}-by-agreement"
        else:
            d = profitability(ctx, start, end, by)
            header, rows, money = _profitability_csv(d)
            tag = report if by == "client" else f"{report}-by-agreement"
        name = f"{tag}-{d['range']['start']}-{d['range']['end']}.csv"
    else:
        raise Conflict(f"Unknown report: {report}")
    return name, reports.to_csv(header, rows, money)
