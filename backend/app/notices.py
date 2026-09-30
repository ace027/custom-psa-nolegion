"""Client statements and payment reminders.

Everything here follows one principle: **nothing is emailed to a client without a person's
approval**. The system PREPARES notices (reminders on a schedule, a monthly batch of statements);
a person reviews, optionally edits, and SENDS or DISMISSES each one. Sending queues an ordinary
outbound email (with PDF attachments) for the mail worker.

Safety rules (each has tests):
  * a stage is issued at most once per invoice (DB unique index), never a lower stage after a higher
  * a client is not re-reminded within `reminder_min_gap_days`, and never if flagged do_not_remind
  * a pending notice whose numbers changed (a payment arrived) cannot be sent until refreshed
  * no recipient (no billing/primary contact with an email) means BLOCKED, never a guess
  * a sent/dismissed/expired notice and a statement are frozen records (DB triggers)
"""

import re
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import audit
from app import billing_repo as brepo
from app import payment_repo as prepo
from app import repositories as repo
from app.billing import today
from app.deps import Ctx
from app.errors import Conflict, NotFound
from app.invoice_pdf import render_invoice_pdf
from app.models import (
    BillingNotice,
    BillingNoticeInvoice,
    Contact,
    EmailMessage,
    Organization,
    OutboundAttachment,
    Payment,
    ReminderStage,
    Statement,
)
from app.money import format_money
from app.payments import bucket_for
from app.statement_pdf import render_statement_pdf
from app.ticket_services import now

PLACEHOLDERS = {
    "client",
    "company",
    "contact_name",
    "invoice_list",
    "invoice_count",
    "total_due",
    "oldest_days_late",
    "as_of",
    "overdue_total",
    "credit",
}
MAX_INVOICE_ATTACHMENTS = 10
STATEMENT_LOOKBACK_DAYS = 90


# =========================================================================================
# Templates
# =========================================================================================
def validate_template(text: str) -> None:
    unknown = sorted(set(re.findall(r"\{(\w+)\}", text)) - PLACEHOLDERS)
    if unknown:
        raise Conflict(
            f"Unknown placeholder {{{unknown[0]}}}. Allowed: "
            + ", ".join("{" + p + "}" for p in sorted(PLACEHOLDERS))
        )


def render(text: str, values: dict) -> str:
    """Substitute {name} placeholders. Deliberately NOT str.format: no attribute or index access."""
    return re.sub(r"\{(\w+)\}", lambda m: str(values.get(m.group(1), m.group(0))), text)


def update_stage(ctx: Ctx, stage_id: int, data: dict) -> ReminderStage:
    stage = ctx.db.get(ReminderStage, stage_id)
    if stage is None:
        raise NotFound("Reminder stage not found")
    for key in ("subject", "body"):
        if data.get(key) is not None:
            validate_template(data[key])
    before = audit.snapshot(stage)
    for key, value in data.items():
        if value is not None:
            setattr(stage, key, value)
    try:
        ctx.db.flush()
    except IntegrityError as exc:  # duplicate days_past_due
        ctx.db.rollback()
        raise Conflict("Another stage already uses that number of days") from exc
    ctx.db.refresh(stage)
    audit.record(
        ctx.db, ctx.user, "reminder_stage.update", stage, before=before, after=audit.snapshot(stage)
    )
    return stage


# =========================================================================================
# Recipients
# =========================================================================================
def resolve_recipients(ctx: Ctx, org_id: int) -> tuple[list[str], str, str | None]:
    """-> (emails, greeting name, blocked_reason). Billing contacts, else the primary contact."""
    contacts = [c for c in repo.list_contacts(ctx.db, ctx.scope, org_id, False) if c.email]
    chosen: list[Contact] = [c for c in contacts if c.is_billing_contact] or [
        c for c in contacts if c.is_primary
    ]
    if not chosen:
        return [], "", "No billing or primary contact with an email address on this client"
    emails = list(dict.fromkeys(c.email.strip() for c in chosen))
    name = chosen[0].name.split()[0] if len(chosen) == 1 else ""
    return emails, name, None


def _greeting(name: str, client: str) -> str:
    return name or f"{client} team"


# =========================================================================================
# Statements
# =========================================================================================
def build_statement(ctx: Ctx, org: Organization) -> dict:
    on = today(ctx)
    invoices = prepo.open_invoices(ctx.db, ctx.scope, org.id)
    amounts = prepo.amounts_for(ctx.db, [i.id for i in invoices])
    aging = dict(current=0, d1_30=0, d31_60=0, d61_90=0, d90_plus=0)
    keys = {
        "current_cents": "current",
        "d1_30_cents": "d1_30",
        "d31_60_cents": "d31_60",
        "d61_90_cents": "d61_90",
        "d90_plus_cents": "d90_plus",
    }
    rows, overdue = [], 0
    for inv in invoices:
        applied, written_off = amounts[inv.id]
        balance = inv.total_cents - applied - written_off
        days = (on - inv.due_date).days
        aging[keys[bucket_for(days)]] += balance
        if days > 0:
            overdue += balance
        rows.append(
            dict(
                number=inv.number,
                invoice_date=inv.invoice_date.isoformat(),
                due_date=inv.due_date.isoformat(),
                total_cents=inv.total_cents,
                settled_cents=applied + written_off,
                balance_cents=balance,
                days_past_due=max(days, 0),
            )
        )
    prev = ctx.db.execute(
        select(Statement)
        .where(Statement.organization_id == org.id)
        .order_by(Statement.as_of.desc(), Statement.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    since = prev.as_of if prev and prev.as_of < on else on - timedelta(days=STATEMENT_LOOKBACK_DAYS)
    pays = (
        ctx.db.execute(
            select(Payment)
            .where(
                Payment.organization_id == org.id,
                Payment.status == "active",
                Payment.received_on >= since,
            )
            .order_by(Payment.received_on, Payment.id)
        )
        .unique()
        .scalars()
    )
    settings = repo.get_settings_row(ctx.db)
    total = sum(r["balance_cents"] for r in rows)
    return dict(
        as_of=on.isoformat(),
        payments_since=since.isoformat(),
        seller_name=settings.company_name,
        seller_address=settings.company_address,
        footer=settings.invoice_footer,
        client_name=org.name,
        client_address=org.billing_address,
        invoices=rows,
        aging=aging,
        total_due_cents=total,
        overdue_cents=overdue,
        credit_cents=prepo.credit_by_org(ctx.db, ctx.scope).get(org.id, 0),
        payments=[
            dict(
                received_on=p.received_on.isoformat(),
                method=p.method,
                reference=p.reference,
                amount_cents=p.amount_cents,
            )
            for p in pays
        ],
    )


def create_statement(ctx: Ctx, org_id: int) -> Statement:
    org = repo.get_organization(ctx.db, ctx.scope, org_id)
    if org is None:
        raise NotFound("Organization not found")
    snap = build_statement(ctx, org)
    statement = Statement(
        organization_id=org.id,
        as_of=date.fromisoformat(snap["as_of"]),
        snapshot=snap,
        created_by=ctx.user.id if ctx.user else None,
    )
    ctx.db.add(statement)
    ctx.db.flush()
    ctx.db.refresh(statement)
    audit.record(
        ctx.db,
        ctx.user,
        "statement.create",
        statement,
        organization_id=org.id,
        detail={"as_of": snap["as_of"], "total_due_cents": snap["total_due_cents"]},
    )
    return statement


def get_statement(ctx: Ctx, statement_id: int) -> Statement:
    stmt = ctx.scope.apply(
        select(Statement).where(Statement.id == statement_id), Statement.organization_id
    )
    s = ctx.db.execute(stmt).scalar_one_or_none()
    if s is None:
        raise NotFound("Statement not found")
    return s


def list_statements(ctx: Ctx, org_id: int) -> list[Statement]:
    stmt = ctx.scope.apply(
        select(Statement).where(Statement.organization_id == org_id), Statement.organization_id
    )
    return list(ctx.db.execute(stmt.order_by(Statement.id.desc())).scalars())


def _statement_values(ctx: Ctx, org: Organization, snap: dict, name: str) -> dict:
    settings = repo.get_settings_row(ctx.db)
    return dict(
        client=org.name,
        company=settings.company_name or "",
        contact_name=_greeting(name, org.name),
        as_of=snap["as_of"],
        total_due=format_money(snap["total_due_cents"]),
        overdue_total=format_money(snap["overdue_cents"]),
        credit=format_money(snap["credit_cents"]),
        invoice_list="",
        invoice_count=str(len(snap["invoices"])),
        oldest_days_late="0",
    )


def _new_statement_notice(
    ctx: Ctx, org: Organization, statement: Statement, *, manual: bool, batch_month: date | None
) -> BillingNotice:
    emails, name, blocked = resolve_recipients(ctx, org.id)
    settings = repo.get_settings_row(ctx.db)
    values = _statement_values(ctx, org, statement.snapshot, name)
    notice = BillingNotice(
        kind="statement",
        organization_id=org.id,
        statement_id=statement.id,
        manual=manual,
        batch_month=batch_month,
        subject=render(settings.statement_subject, values),
        body_text=render(settings.statement_body, values),
        to_emails=emails,
        blocked_reason=blocked,
        created_by=ctx.user.id if ctx.user else None,
    )
    ctx.db.add(notice)
    ctx.db.flush()
    ctx.db.refresh(notice)
    audit.record(
        ctx.db,
        ctx.user,
        "notice.create",
        notice,
        organization_id=org.id,
        detail={"kind": "statement", "manual": manual, "blocked": bool(blocked)},
    )
    return notice


def email_statement(ctx: Ctx, statement_id: int, send: bool) -> BillingNotice:
    statement = get_statement(ctx, statement_id)
    org = repo.get_organization(ctx.db, ctx.scope, statement.organization_id)
    notice = _new_statement_notice(ctx, org, statement, manual=True, batch_month=None)
    if send:
        send_notice(ctx, notice.id)
    return notice


def prepare_statement_batch(ctx: Ctx, month: date | None = None) -> list[BillingNotice]:
    """One pending statement notice per client with a balance, once per month (idempotent)."""
    first = (month or today(ctx)).replace(day=1)
    created: list[BillingNotice] = []
    seen = {
        r[0]
        for r in ctx.db.execute(
            select(BillingNotice.organization_id).where(
                BillingNotice.kind == "statement", BillingNotice.batch_month == first
            )
        )
    }
    for inv in prepo.open_invoices(ctx.db, ctx.scope):
        org = inv.organization
        if org.id in seen or org.archived_at:
            continue
        seen.add(org.id)
        statement = create_statement(ctx, org.id)
        created.append(_new_statement_notice(ctx, org, statement, manual=False, batch_month=first))
    return created


# =========================================================================================
# Reminders
# =========================================================================================
def _stages(ctx: Ctx) -> list[ReminderStage]:
    return list(
        ctx.db.execute(select(ReminderStage).order_by(ReminderStage.days_past_due)).scalars()
    )


def _overdue_invoices(ctx: Ctx, org_id: int | None = None):
    """[(invoice, balance, days_past_due)] for open invoices past their due date."""
    on = today(ctx)
    invoices = [i for i in prepo.open_invoices(ctx.db, ctx.scope, org_id) if i.due_date < on]
    amounts = prepo.amounts_for(ctx.db, [i.id for i in invoices])
    return [(i, i.total_cents - sum(amounts[i.id]), (on - i.due_date).days) for i in invoices]


def _invoice_list_text(items) -> str:
    return "\n".join(
        f"  {inv.number}   due {inv.due_date}   {days} day{'s' if days != 1 else ''} past due   "
        f"balance {format_money(balance)}"
        for inv, balance, days in items
    )


def _reminder_values(ctx: Ctx, org: Organization, name: str, items) -> dict:
    settings = repo.get_settings_row(ctx.db)
    total = sum(b for _, b, _ in items)
    return dict(
        client=org.name,
        company=settings.company_name or "",
        contact_name=_greeting(name, org.name),
        invoice_list=_invoice_list_text(items),
        invoice_count=str(len(items)),
        total_due=format_money(total),
        oldest_days_late=str(max((d for *_, d in items), default=0)),
        as_of=today(ctx).isoformat(),
        overdue_total=format_money(total),
        credit=format_money(prepo.credit_by_org(ctx.db, ctx.scope).get(org.id, 0)),
    )


def _issued_stage_days(ctx: Ctx, invoice_ids: list[int]) -> dict[int, int]:
    """invoice id -> highest stage (days_past_due) ever issued for it."""
    if not invoice_ids:
        return {}
    rows = ctx.db.execute(
        select(BillingNoticeInvoice.invoice_id, ReminderStage.days_past_due)
        .join(ReminderStage, ReminderStage.id == BillingNoticeInvoice.stage_id)
        .where(BillingNoticeInvoice.invoice_id.in_(invoice_ids))
    )
    out: dict[int, int] = {}
    for inv_id, days in rows:
        out[inv_id] = max(out.get(inv_id, -1), days)
    return out


def _stage_for(stages: list[ReminderStage], days_late: int) -> ReminderStage | None:
    eligible = [s for s in stages if s.enabled and s.days_past_due <= days_late]
    return max(eligible, key=lambda s: s.days_past_due) if eligible else None


def _make_reminder(
    ctx: Ctx, org: Organization, items, *, tone: ReminderStage, new_stage: dict, manual: bool
) -> BillingNotice:
    emails, name, blocked = resolve_recipients(ctx, org.id)
    values = _reminder_values(ctx, org, name, items)
    notice = BillingNotice(
        kind="reminder",
        organization_id=org.id,
        stage_id=tone.id,
        manual=manual,
        subject=render(tone.subject, values),
        body_text=render(tone.body, values),
        to_emails=emails,
        blocked_reason=blocked,
        created_by=ctx.user.id if ctx.user else None,
    )
    ctx.db.add(notice)
    ctx.db.flush()
    for inv, balance, days in items:
        ctx.db.add(
            BillingNoticeInvoice(
                notice_id=notice.id,
                invoice_id=inv.id,
                organization_id=org.id,
                stage_id=new_stage.get(inv.id),
                balance_cents=balance,
                days_past_due=days,
            )
        )
    ctx.db.flush()
    ctx.db.refresh(notice)
    audit.record(
        ctx.db,
        ctx.user,
        "notice.create",
        notice,
        organization_id=org.id,
        detail={
            "kind": "reminder",
            "stage": tone.name,
            "manual": manual,
            "invoices": [i.number for i, _, _ in items],
            "blocked": bool(blocked),
        },
    )
    return notice


def prepare_reminders(ctx: Ctx) -> list[BillingNotice]:
    """Work out which overdue invoices are due a reminder stage and queue one notice per client."""
    settings = repo.get_settings_row(ctx.db)
    stages = _stages(ctx)
    on = now()
    by_org: dict[int, list] = {}
    for item in _overdue_invoices(ctx):
        by_org.setdefault(item[0].organization_id, []).append(item)
    created: list[BillingNotice] = []
    for org_id, items in by_org.items():
        org = items[0][0].organization
        if org.do_not_remind or org.archived_at:
            continue
        recent = ctx.db.execute(
            select(BillingNotice.id)
            .where(
                BillingNotice.organization_id == org_id,
                BillingNotice.kind == "reminder",
                BillingNotice.status.in_(("pending", "sent")),
                (BillingNotice.created_at >= on - timedelta(days=settings.reminder_min_gap_days))
                | (BillingNotice.status == "pending"),
            )
            .limit(1)
        ).first()
        if recent:
            continue
        issued = _issued_stage_days(ctx, [i.id for i, _, _ in items])
        new_stage: dict[int, ReminderStage] = {}
        for inv, _, days in items:
            stage = _stage_for(stages, days)
            if stage and stage.days_past_due > issued.get(inv.id, -1):
                new_stage[inv.id] = stage
        if not new_stage:
            continue
        tone = max(new_stage.values(), key=lambda s: s.days_past_due)
        created.append(
            _make_reminder(
                ctx,
                org,
                items,
                tone=tone,
                new_stage={k: v.id for k, v in new_stage.items()},
                manual=False,
            )
        )
    return created


def create_manual_reminder(ctx: Ctx, org_id: int, invoice_ids: list[int] | None) -> BillingNotice:
    org = repo.get_organization(ctx.db, ctx.scope, org_id)
    if org is None:
        raise NotFound("Organization not found")
    if ctx.db.execute(
        select(BillingNotice.id).where(
            BillingNotice.organization_id == org_id,
            BillingNotice.kind == "reminder",
            BillingNotice.status == "pending",
        )
    ).first():
        raise Conflict("A reminder for this client is already waiting for review")
    on = today(ctx)
    open_items = []
    invoices = prepo.open_invoices(ctx.db, ctx.scope, org_id)
    amounts = prepo.amounts_for(ctx.db, [i.id for i in invoices])
    for inv in invoices:
        if invoice_ids is None and inv.due_date >= on:
            continue
        if invoice_ids is not None and inv.id not in invoice_ids:
            continue
        open_items.append((inv, inv.total_cents - sum(amounts[inv.id]), (on - inv.due_date).days))
    if invoice_ids is not None and len(open_items) != len(set(invoice_ids)):
        raise Conflict("Some of those invoices are not open invoices for this client")
    if not open_items:
        raise Conflict("This client has no overdue invoices to remind them about")
    stages = [s for s in _stages(ctx) if s.enabled] or _stages(ctx)
    oldest = max(d for *_, d in open_items)
    tone = _stage_for(stages, oldest) or stages[0]
    return _make_reminder(ctx, org, open_items, tone=tone, new_stage={}, manual=True)


# =========================================================================================
# Review queue: get, edit, refresh, send, dismiss
# =========================================================================================
def get_notice(ctx: Ctx, notice_id: int, lock: bool = False) -> BillingNotice:
    stmt = ctx.scope.apply(
        select(BillingNotice).where(BillingNotice.id == notice_id), BillingNotice.organization_id
    )
    if lock:
        stmt = stmt.with_for_update(of=BillingNotice)
    n = ctx.db.execute(stmt).unique().scalar_one_or_none()
    if n is None:
        raise NotFound("Notice not found")
    return n


def notice_invoices(ctx: Ctx, notice_id: int) -> list[BillingNoticeInvoice]:
    stmt = ctx.scope.apply(
        select(BillingNoticeInvoice).where(BillingNoticeInvoice.notice_id == notice_id),
        BillingNoticeInvoice.organization_id,
    )
    return list(
        ctx.db.execute(
            stmt.order_by(BillingNoticeInvoice.days_past_due.desc(), BillingNoticeInvoice.id)
        ).scalars()
    )


def is_stale(ctx: Ctx, notice: BillingNotice) -> bool:
    """Have the numbers this notice quotes changed since it was prepared?"""
    if notice.status != "pending":
        return False
    if notice.kind == "statement":
        org = repo.get_organization(ctx.db, ctx.scope, notice.organization_id)
        fresh = build_statement(ctx, org)
        old = ctx.db.get(Statement, notice.statement_id).snapshot
        return (fresh["total_due_cents"], fresh["credit_cents"], len(fresh["invoices"])) != (
            old["total_due_cents"],
            old["credit_cents"],
            len(old["invoices"]),
        )
    current = {
        inv.id: balance for inv, balance, _ in _overdue_invoices(ctx, notice.organization_id)
    }
    return any(
        current.get(r.invoice_id) != r.balance_cents for r in notice_invoices(ctx, notice.id)
    )


def update_notice(ctx: Ctx, notice_id: int, subject: str | None, body_text: str | None):
    notice = get_notice(ctx, notice_id, lock=True)
    if notice.status != "pending":
        raise Conflict(f"This notice is {notice.status}; only pending notices can be edited")
    before = audit.snapshot(notice)
    if subject is not None:
        if not subject.strip():
            raise Conflict("The subject cannot be empty")
        notice.subject = subject.strip()
    if body_text is not None:
        if not body_text.strip():
            raise Conflict("The message cannot be empty")
        notice.body_text = body_text
    ctx.db.flush()
    ctx.db.refresh(notice)
    audit.record(
        ctx.db,
        ctx.user,
        "notice.edit",
        notice,
        before=before,
        after=audit.snapshot(notice),
        organization_id=notice.organization_id,
    )
    return notice


def refresh_notice(ctx: Ctx, notice_id: int) -> BillingNotice:
    """Re-read balances and recipients and re-render the message (discarding manual edits)."""
    notice = get_notice(ctx, notice_id, lock=True)
    if notice.status != "pending":
        raise Conflict(f"This notice is {notice.status}; only pending notices can be refreshed")
    org = notice.organization
    emails, name, blocked = resolve_recipients(ctx, org.id)
    notice.to_emails, notice.blocked_reason = emails, blocked
    if notice.kind == "statement":
        statement = create_statement(ctx, org.id)
        notice.statement_id = statement.id
        values = _statement_values(ctx, org, statement.snapshot, name)
        settings = repo.get_settings_row(ctx.db)
        notice.subject = render(settings.statement_subject, values)
        notice.body_text = render(settings.statement_body, values)
    else:
        current = {i.id: (i, b, d) for i, b, d in _overdue_invoices(ctx, org.id)}
        old_rows = notice_invoices(ctx, notice.id)
        keep = [r for r in old_rows if r.invoice_id in current]
        if not keep:
            notice.status, notice.decided_at = "expired", now()
            ctx.db.flush()
            audit.record(
                ctx.db,
                ctx.user,
                "notice.expire",
                notice,
                organization_id=org.id,
                detail={"reason": "nothing left overdue"},
            )
            return notice
        for row in old_rows:
            ctx.db.delete(row)
        ctx.db.flush()
        items = []
        for row in keep:
            inv, balance, days = current[row.invoice_id]
            items.append((inv, balance, days))
            ctx.db.add(
                BillingNoticeInvoice(
                    notice_id=notice.id,
                    invoice_id=inv.id,
                    organization_id=org.id,
                    stage_id=row.stage_id,
                    balance_cents=balance,
                    days_past_due=days,
                )
            )
        for inv, balance, days in current.values():  # newly overdue invoices join (info only)
            if inv.id not in {r.invoice_id for r in keep}:
                items.append((inv, balance, days))
                ctx.db.add(
                    BillingNoticeInvoice(
                        notice_id=notice.id,
                        invoice_id=inv.id,
                        organization_id=org.id,
                        stage_id=None,
                        balance_cents=balance,
                        days_past_due=days,
                    )
                )
        tone = notice.stage or _stage_for(_stages(ctx), max(d for *_, d in items))
        values = _reminder_values(ctx, org, name, items)
        notice.subject, notice.body_text = render(tone.subject, values), render(tone.body, values)
    ctx.db.flush()
    ctx.db.refresh(notice)
    audit.record(ctx.db, ctx.user, "notice.refresh", notice, organization_id=org.id)
    return notice


def _attachments_for(ctx: Ctx, notice: BillingNotice) -> list[tuple[str, bytes]]:
    settings = repo.get_settings_row(ctx.db)
    if notice.kind == "statement":
        snap = ctx.db.get(Statement, notice.statement_id).snapshot
        return [(f"Statement-{snap['as_of']}.pdf", render_statement_pdf(snap))]
    rows = notice_invoices(ctx, notice.id)
    if len(rows) > MAX_INVOICE_ATTACHMENTS:  # too many to attach: send an account statement
        statement = create_statement(ctx, notice.organization_id)
        notice.statement_id = statement.id
        return [(f"Statement-{statement.as_of}.pdf", render_statement_pdf(statement.snapshot))]
    out = []
    for row in rows:
        inv = brepo.get_invoice(ctx.db, ctx.scope, row.invoice_id)
        lines = brepo.invoice_lines(ctx.db, ctx.scope, inv.id)
        out.append((f"{inv.number}.pdf", render_invoice_pdf(inv, lines, settings)))
    return out


def send_notice(ctx: Ctx, notice_id: int) -> BillingNotice:
    """Approve: queue the email (with PDFs). The mail worker delivers it."""
    notice = get_notice(ctx, notice_id, lock=True)
    if notice.status != "pending":
        raise Conflict(f"This notice is already {notice.status}")
    mailbox = repo.get_mailbox_status(ctx.db)
    if mailbox.mailbox is None:
        raise Conflict("Email is not configured, so nothing can be sent (see docs/MAIL_SETUP.md)")
    org = notice.organization
    if org.do_not_remind and notice.kind == "reminder":
        raise Conflict("This client is marked 'do not remind'")
    emails, _, blocked = resolve_recipients(ctx, org.id)
    if blocked:
        raise Conflict(blocked)
    if is_stale(ctx, notice):
        raise Conflict("The balances changed since this was prepared. Refresh it before sending")
    if notice.kind == "reminder" and not notice_invoices(ctx, notice.id):
        raise Conflict("This reminder has no invoices")
    attachments = _attachments_for(ctx, notice)
    email = EmailMessage(
        direction="out",
        organization_id=org.id,
        to_emails=emails,
        subject=notice.subject[:998],
        body_text=notice.body_text,
        send_status="pending",
    )
    ctx.db.add(email)
    ctx.db.flush()
    for name, data in attachments:
        ctx.db.add(
            OutboundAttachment(
                email_message_id=email.id,
                organization_id=org.id,
                filename=name,
                content_type="application/pdf",
                data=data,
            )
        )
    before = audit.snapshot(notice)
    notice.to_emails, notice.blocked_reason = emails, None
    notice.status, notice.email_message_id = "sent", email.id
    notice.decided_by, notice.decided_at = ctx.user.id if ctx.user else None, now()
    ctx.db.flush()
    ctx.db.refresh(notice)
    audit.record(
        ctx.db,
        ctx.user,
        "notice.send",
        notice,
        before=before,
        after=audit.snapshot(notice),
        organization_id=org.id,
        detail={"to": emails, "attachments": [n for n, _ in attachments], "kind": notice.kind},
    )
    return notice


def dismiss_notice(ctx: Ctx, notice_id: int, reason: str) -> BillingNotice:
    notice = get_notice(ctx, notice_id, lock=True)
    if notice.status != "pending":
        raise Conflict(f"This notice is already {notice.status}")
    before = audit.snapshot(notice)
    notice.status, notice.dismiss_reason = "dismissed", reason.strip()
    notice.decided_by, notice.decided_at = ctx.user.id if ctx.user else None, now()
    ctx.db.flush()
    ctx.db.refresh(notice)
    audit.record(
        ctx.db,
        ctx.user,
        "notice.dismiss",
        notice,
        before=before,
        after=audit.snapshot(notice),
        organization_id=notice.organization_id,
        detail={"reason": reason},
    )
    return notice


def list_notices(ctx: Ctx, *, status, kind, org_id, limit, offset):
    from sqlalchemy import func

    stmt = ctx.scope.apply(select(BillingNotice), BillingNotice.organization_id)
    if status:
        stmt = stmt.where(BillingNotice.status == status)
    if kind:
        stmt = stmt.where(BillingNotice.kind == kind)
    if org_id is not None:
        stmt = stmt.where(BillingNotice.organization_id == org_id)
    total = ctx.db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = ctx.db.execute(stmt.order_by(BillingNotice.id.desc()).limit(limit).offset(offset))
    return list(rows.unique().scalars()), total


# =========================================================================================
# Scheduled preparation (called by the worker; also idempotent when run by hand)
# =========================================================================================
def run_scheduled(ctx: Ctx) -> dict:
    settings = repo.get_settings_row(ctx.db)
    on = today(ctx)
    result = {"reminders": 0, "statements": 0}
    if settings.auto_prepare_reminders and settings.reminders_prepared_on != on:
        result["reminders"] = len(prepare_reminders(ctx))
        settings.reminders_prepared_on = on
    if settings.auto_prepare_statements and settings.statements_prepared_month != on.replace(day=1):
        result["statements"] = len(prepare_statement_batch(ctx))
        settings.statements_prepared_month = on.replace(day=1)
    ctx.db.flush()
    return result
