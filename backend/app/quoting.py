"""New-client quoting: onsite survey -> transparent price -> approval -> proposal -> agreement.

Pricing (docs/QUOTING.md):
  base     = users x per-user rate + priced devices x per-class rate        (integer cents)
  uplift   = SUM of the factors that apply, in basis points (added, never compounded)
  price    = round_half_up(base x (10000 + uplift) / 10000)                 (rounded once)
A tech may change the price, with a reason; an adjusted quote needs an admin's approval.
Rates and counts are frozen into the quote's snapshot, so later rate-card edits never alter it.
"""

import calendar
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import audit
from app import repositories as repo
from app.billing import create_agreement, today
from app.deps import Ctx
from app.errors import Conflict, NotFound
from app.models import (
    Agreement,
    EmailMessage,
    InvoiceLine,
    OutboundAttachment,
    Quote,
    QuoteSettings,
    SiteSurvey,
    SurveyApp,
    SurveyDevice,
)
from app.money import BP, format_money, round_cents
from app.permissions import QUOTE_MANAGE, has_permission
from app.quote_pdf import render_quote_pdf
from app.ticket_services import now

CLASSES = ("workstation", "server", "network", "other")
CLASS_LABELS = {
    "workstation": "Workstations",
    "server": "Servers",
    "network": "Network devices",
    "other": "Other devices",
}
EDITABLE = ("draft", "needs_approval", "approved")
OPEN = ("draft", "needs_approval", "approved", "sent")


# ---- pure pricing --------------------------------------------------------------------------
def derive_warranty(end: date | None, status: str, on: date) -> str:
    """A warranty end date, when known, decides the status; otherwise the tech's answer stands."""
    if end is not None:
        return "in_warranty" if end >= on else "out_of_warranty"
    return status


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def contract_end(start: date, term_months: int) -> date:
    return add_months(start, term_months) - timedelta(days=1)


def compute(qs: QuoteSettings, survey: SiteSurvey) -> dict:
    """-> the snapshot: every number and reason the quote shows. No clock, no database."""
    rates = {
        "per_user": qs.per_user_rate_cents,
        "workstation": qs.workstation_rate_cents,
        "server": qs.server_rate_cents,
        "network": qs.network_rate_cents,
        "other": qs.other_rate_cents,
    }
    by_class = {c: {"count": 0, "out": 0, "unknown": 0} for c in CLASSES}
    for d in survey.devices:
        if not d.priced:
            continue
        row = by_class[d.device_class]
        row["count"] += 1
        if d.warranty_status != "in_warranty":  # unknown counts as out: flagged, never hidden
            row["out"] += 1
        if d.warranty_status == "unknown":
            row["unknown"] += 1
    priced = sum(r["count"] for r in by_class.values())
    out = sum(r["out"] for r in by_class.values())
    unknown = sum(r["unknown"] for r in by_class.values())

    lines = []
    if survey.user_count and rates["per_user"]:
        lines.append(("Users", survey.user_count, rates["per_user"]))
    for c in CLASSES:
        if by_class[c]["count"] and rates[c]:
            lines.append((CLASS_LABELS[c], by_class[c]["count"], rates[c]))
    base_lines = [
        {"description": d, "quantity": q, "unit_cents": u, "amount_cents": q * u}
        for d, q, u in lines
    ]
    base = sum(line["amount_cents"] for line in base_lines)

    servers = by_class["server"]
    legacy = [a.name for a in survey.apps if a.legacy]
    pct = f"{round(out * 100 / priced)}%" if priced else "0%"
    factors = [
        {
            "key": "hardware",
            "label": "Hardware out of warranty",
            "applies": priced > 0 and out * 2 > priced,  # strictly MORE than half
            "bp": qs.hardware_uplift_bp,
            "reason": f"{out} of {priced} priced devices ({pct}) are out of warranty"
            + (f"; {unknown} have no warranty information" if unknown else ""),
        },
        {
            "key": "server",
            "label": "Server out of warranty",
            "applies": servers["out"] > 0,
            "bp": qs.server_uplift_bp,
            "reason": f"{servers['out']} of {servers['count']} servers are out of warranty",
        },
        {
            "key": "legacy_app",
            "label": "Legacy line-of-business application",
            "applies": bool(legacy),
            "bp": qs.legacy_app_uplift_bp,
            "reason": ("Legacy application: " + ", ".join(legacy)) if legacy else "None reported",
        },
    ]
    uplift_bp = sum(f["bp"] for f in factors if f["applies"])
    price = round_cents(Decimal(base) * (10000 + uplift_bp) / BP)
    return {
        "rates": rates,
        "users": survey.user_count,
        "sites": survey.site_count,
        "devices": {"priced": priced, "out": out, "unknown": unknown, "by_class": by_class},
        "apps": [{"name": a.name, "legacy": a.legacy} for a in survey.apps],
        "base_lines": base_lines,
        "factors": factors,
        "base_cents": base,
        "uplift_bp": uplift_bp,
        "price_cents": price,
        "intro_text": qs.intro_text,
    }


# ---- rate card ------------------------------------------------------------------------------
def get_quote_settings(ctx: Ctx) -> QuoteSettings:
    return ctx.db.get(QuoteSettings, 1)


def update_quote_settings(ctx: Ctx, data: dict) -> QuoteSettings:
    qs = get_quote_settings(ctx)
    before = audit.snapshot(qs)
    for key, value in data.items():
        setattr(qs, key, value)
    ctx.db.flush()
    ctx.db.refresh(qs)
    audit.record(
        ctx.db, ctx.user, "quote_settings.update", qs, before=before, after=audit.snapshot(qs)
    )
    return qs


# ---- surveys --------------------------------------------------------------------------------
def _org(ctx: Ctx, org_id: int):
    org = repo.get_organization(ctx.db, ctx.scope, org_id)
    if org is None:
        raise NotFound("Organization not found")
    if org.archived_at is not None:
        raise Conflict("This organization is archived")
    return org


def get_survey(ctx: Ctx, survey_id: int) -> SiteSurvey:
    stmt = ctx.scope.apply(
        select(SiteSurvey).where(SiteSurvey.id == survey_id), SiteSurvey.organization_id
    )
    survey = ctx.db.execute(stmt).unique().scalar_one_or_none()
    if survey is None:
        raise NotFound("Survey not found")
    return survey


def list_surveys(ctx: Ctx, org_id: int | None, status: str | None) -> list[SiteSurvey]:
    stmt = ctx.scope.apply(select(SiteSurvey), SiteSurvey.organization_id)
    if org_id is not None:
        stmt = stmt.where(SiteSurvey.organization_id == org_id)
    if status:
        stmt = stmt.where(SiteSurvey.status == status)
    return list(ctx.db.execute(stmt.order_by(SiteSurvey.id.desc())).unique().scalars())


def create_survey(ctx: Ctx, org_id: int, data: dict) -> SiteSurvey:
    _org(ctx, org_id)
    survey = SiteSurvey(
        organization_id=org_id, created_by=ctx.user.id if ctx.user else None, **data
    )
    ctx.db.add(survey)
    ctx.db.flush()
    ctx.db.refresh(survey)
    audit.record(
        ctx.db,
        ctx.user,
        "survey.create",
        survey,
        after=audit.snapshot(survey),
        organization_id=org_id,
    )
    return survey


def _check_open(survey: SiteSurvey) -> None:
    if survey.status == "completed":
        raise Conflict("This survey is completed. Start a new survey to record changes")


def save_survey(ctx: Ctx, survey_id: int, data: dict) -> SiteSurvey:
    """Full replace of the survey's answers: the phone form autosaves the whole thing."""
    survey = get_survey(ctx, survey_id)
    _check_open(survey)
    on = today(ctx)
    before = audit.snapshot(survey)
    for key in ("user_count", "site_count", "notes", "scheduled_for", "tech_id"):
        if key in data:
            setattr(survey, key, data[key])
    survey.status = "in_progress"
    survey.devices.clear()
    survey.apps.clear()
    ctx.db.flush()
    for d in data["devices"]:
        d = dict(d)
        d["warranty_status"] = derive_warranty(d.get("warranty_end"), d["warranty_status"], on)
        survey.devices.append(SurveyDevice(organization_id=survey.organization_id, **d))
    for a in data["apps"]:
        survey.apps.append(SurveyApp(organization_id=survey.organization_id, **a))
    ctx.db.flush()
    ctx.db.expire(survey)
    survey = get_survey(ctx, survey_id)
    audit.record(
        ctx.db,
        ctx.user,
        "survey.save",
        survey,
        before=before,
        after=audit.snapshot(survey),
        organization_id=survey.organization_id,
        detail={"devices": len(survey.devices), "apps": len(survey.apps)},
    )
    return survey


def complete_survey(ctx: Ctx, survey_id: int) -> SiteSurvey:
    survey = get_survey(ctx, survey_id)
    _check_open(survey)
    if survey.user_count < 1 and not any(d.priced for d in survey.devices):
        raise Conflict("Record the user count and/or at least one priced device first")
    before = audit.snapshot(survey)
    survey.status, survey.completed_at = "completed", now()
    ctx.db.flush()
    ctx.db.refresh(survey)
    audit.record(
        ctx.db,
        ctx.user,
        "survey.complete",
        survey,
        before=before,
        after=audit.snapshot(survey),
        organization_id=survey.organization_id,
    )
    return survey


# ---- quotes ---------------------------------------------------------------------------------
def get_quote(ctx: Ctx, quote_id: int, *, lock: bool = False) -> Quote:
    stmt = ctx.scope.apply(select(Quote).where(Quote.id == quote_id), Quote.organization_id)
    if lock:
        stmt = stmt.with_for_update(of=Quote)
    quote = ctx.db.execute(stmt).unique().scalar_one_or_none()
    if quote is None:
        raise NotFound("Quote not found")
    return quote


def list_quotes(ctx: Ctx, org_id: int | None, status: str | None) -> list[Quote]:
    stmt = ctx.scope.apply(select(Quote), Quote.organization_id)
    if org_id is not None:
        stmt = stmt.where(Quote.organization_id == org_id)
    if status:
        stmt = stmt.where(Quote.status == status)
    return list(ctx.db.execute(stmt.order_by(Quote.id.desc())).unique().scalars())


def is_expired(ctx: Ctx, quote: Quote) -> bool:
    if quote.status != "sent" or quote.valid_until is None:
        return False
    return quote.valid_until < today(ctx)


def _validate_effective(effective: date | None, on: date) -> date:
    if effective is None:
        raise Conflict("A price change needs an effective date (the first day of a month)")
    if effective.day != 1 or effective <= on:
        raise Conflict("The effective date must be the first day of a future month")
    return effective


def _reprice_target(ctx: Ctx, org_id: int, agreement_id: int) -> Agreement:
    a = ctx.db.get(Agreement, agreement_id)
    if a is None or a.organization_id != org_id or not ctx.scope.allows(a.organization_id):
        raise NotFound("Agreement not found")
    if a.type != "flat":
        raise Conflict("Only flat-fee agreements can be repriced from a quote")
    return a


def _new_quote(
    ctx: Ctx,
    survey: SiteSurvey,
    *,
    kind: str,
    agreement_id: int | None,
    effective_date: date | None,
    notes: str | None,
    version: int = 1,
    replaces: int | None = None,
) -> Quote:
    if survey.status != "completed":
        raise Conflict("Complete the survey before quoting")
    qs = get_quote_settings(ctx)
    snap = compute(qs, survey)
    if snap["base_cents"] <= 0:
        raise Conflict("The rate card gives this environment no price. Set the rates first")
    if kind == "reprice":
        _reprice_target(ctx, survey.organization_id, agreement_id)
        effective_date = _validate_effective(effective_date, today(ctx))
    else:
        agreement_id = effective_date = None
    quote = Quote(
        organization_id=survey.organization_id,
        survey_id=survey.id,
        kind=kind,
        agreement_id=agreement_id,
        effective_date=effective_date,
        version=version,
        replaces_quote_id=replaces,
        snapshot=snap,
        base_cents=snap["base_cents"],
        uplift_bp=snap["uplift_bp"],
        computed_price_cents=snap["price_cents"],
        final_price_cents=snap["price_cents"],
        term_months=qs.term_months,
        notes=notes,
        created_by=ctx.user.id if ctx.user else None,
    )
    ctx.db.add(quote)
    try:
        ctx.db.flush()
    except IntegrityError as exc:
        raise Conflict("This survey already has an open quote. Revise or cancel it") from exc
    ctx.db.refresh(quote)
    audit.record(
        ctx.db,
        ctx.user,
        "quote.create",
        quote,
        after=audit.snapshot(quote),
        organization_id=quote.organization_id,
    )
    return quote


def create_quote(ctx: Ctx, survey_id: int, data: dict) -> Quote:
    survey = get_survey(ctx, survey_id)
    return _new_quote(
        ctx,
        survey,
        kind=data["kind"],
        agreement_id=data.get("agreement_id"),
        effective_date=data.get("effective_date"),
        notes=data.get("notes"),
    )


def _changed(ctx: Ctx, quote: Quote, action: str, before: dict, detail: dict | None = None):
    ctx.db.flush()
    ctx.db.refresh(quote)
    audit.record(
        ctx.db,
        ctx.user,
        action,
        quote,
        before=before,
        after=audit.snapshot(quote),
        organization_id=quote.organization_id,
        detail=detail,
    )
    return quote


def adjust_quote(ctx: Ctx, quote_id: int, data: dict) -> Quote:
    quote = get_quote(ctx, quote_id, lock=True)
    if quote.status not in EDITABLE:
        raise Conflict(f"A {quote.status} quote can't be edited. Revise it instead")
    before = audit.snapshot(quote)
    if "notes" in data:
        quote.notes = data["notes"]
    if "valid_until" in data:
        quote.valid_until = data["valid_until"]
    if "effective_date" in data and quote.kind == "reprice":
        quote.effective_date = _validate_effective(data["effective_date"], today(ctx))
    if data.get("final_price_cents") is not None:
        price = data["final_price_cents"]
        if price == quote.computed_price_cents:
            quote.final_price_cents, quote.adjustment_reason, quote.adjusted_by = price, None, None
        else:
            reason = (data.get("adjustment_reason") or quote.adjustment_reason or "").strip()
            if not reason:
                raise Conflict("Changing the price needs a reason")
            quote.final_price_cents, quote.adjustment_reason = price, reason
            quote.adjusted_by = ctx.user.id if ctx.user else None
    elif data.get("adjustment_reason") and quote.final_price_cents != quote.computed_price_cents:
        quote.adjustment_reason = data["adjustment_reason"].strip()
    # any edit voids an earlier approval/submission: what was approved must be what is sent
    quote.status = "draft"
    quote.approved_by = quote.approved_at = quote.submitted_at = None
    return _changed(ctx, quote, "quote.update", before)


def submit_quote(ctx: Ctx, quote_id: int) -> Quote:
    quote = get_quote(ctx, quote_id, lock=True)
    if quote.status != "draft":
        raise Conflict(f"Only a draft can be submitted (this one is {quote.status})")
    before = audit.snapshot(quote)
    quote.submitted_at = now()
    adjusted = quote.final_price_cents != quote.computed_price_cents
    is_approver = ctx.user is not None and has_permission(ctx.user.role, QUOTE_MANAGE)
    if not adjusted or is_approver:
        # untouched quotes follow the rate card; an approver's own change is already approved
        quote.status, quote.approved_at = "approved", now()
        quote.approved_by = ctx.user.id if (adjusted and ctx.user) else None
    else:
        quote.status = "needs_approval"
    return _changed(ctx, quote, "quote.submit", before)


def approve_quote(ctx: Ctx, quote_id: int) -> Quote:
    quote = get_quote(ctx, quote_id, lock=True)
    if quote.status != "needs_approval":
        raise Conflict("This quote isn't waiting for approval")
    if ctx.user is not None and quote.adjusted_by == ctx.user.id:
        raise Conflict("You can't approve your own price change")
    before = audit.snapshot(quote)
    quote.status, quote.approved_at = "approved", now()
    quote.approved_by = ctx.user.id if ctx.user else None
    return _changed(ctx, quote, "quote.approve", before)


def reject_quote(ctx: Ctx, quote_id: int, note: str) -> Quote:
    quote = get_quote(ctx, quote_id, lock=True)
    if quote.status != "needs_approval":
        raise Conflict("This quote isn't waiting for approval")
    before = audit.snapshot(quote)
    quote.status, quote.decision_note, quote.submitted_at = "draft", note, None
    return _changed(ctx, quote, "quote.reject", before, {"note": note})


def cancel_quote(ctx: Ctx, quote_id: int, note: str | None) -> Quote:
    quote = get_quote(ctx, quote_id, lock=True)
    if quote.status not in OPEN:
        raise Conflict(f"A {quote.status} quote can't be cancelled")
    before = audit.snapshot(quote)
    quote.status, quote.decision_note = "cancelled", note
    return _changed(ctx, quote, "quote.cancel", before)


def revise_quote(ctx: Ctx, quote_id: int) -> Quote:
    """New draft version from the same survey at today's rate card; the old one is closed."""
    old = get_quote(ctx, quote_id, lock=True)
    if old.status not in (*OPEN, "declined"):
        raise Conflict(f"A {old.status} quote can't be revised")
    survey = get_survey(ctx, old.survey_id)
    if old.status in OPEN:
        before = audit.snapshot(old)
        old.status, old.decision_note = "cancelled", f"Superseded by a revision of quote {old.id}"
        _changed(ctx, old, "quote.cancel", before)
    return _new_quote(
        ctx,
        survey,
        kind=old.kind,
        agreement_id=old.agreement_id,
        effective_date=old.effective_date if old.kind == "reprice" else None,
        notes=old.notes,
        version=old.version + 1,
        replaces=old.id,
    )


def recipients(ctx: Ctx, org_id: int) -> list[str]:
    contacts = [c for c in repo.list_contacts(ctx.db, ctx.scope, org_id, False) if c.email]
    chosen = [c for c in contacts if c.is_primary] or contacts
    return list(dict.fromkeys(c.email.strip() for c in chosen))


def proposal(ctx: Ctx, quote: Quote) -> dict:
    """What the client sees. Internal adjustment reasons and approvals are deliberately absent."""
    s = repo.get_settings_row(ctx.db)
    snap = quote.snapshot
    adjustment = quote.final_price_cents - quote.computed_price_cents
    return {
        "number": f"Q-{quote.id}",
        "version": quote.version,
        "seller_name": s.company_name,
        "seller_address": s.company_address,
        "client_name": quote.organization.name,
        "client_address": quote.organization.billing_address,
        "prepared": (quote.submitted_at or quote.created_at).date().isoformat(),
        "valid_until": quote.valid_until.isoformat() if quote.valid_until else None,
        "term_months": quote.term_months,
        "price_cents": quote.final_price_cents,
        "base_lines": snap["base_lines"],
        "base_cents": quote.base_cents,
        "factors": [f for f in snap["factors"] if f["applies"] and f["bp"] > 0],
        "uplift_bp": quote.uplift_bp,
        "adjustment_cents": adjustment,
        "environment": {
            "users": snap["users"],
            "sites": snap["sites"],
            "devices": snap["devices"],
        },
        "intro_text": snap.get("intro_text"),
        "kind": quote.kind,
        "effective_date": quote.effective_date.isoformat() if quote.effective_date else None,
    }


def quote_pdf(ctx: Ctx, quote_id: int) -> tuple[str, bytes]:
    quote = get_quote(ctx, quote_id)
    return f"Quote-Q{quote.id}-v{quote.version}.pdf", render_quote_pdf(proposal(ctx, quote))


def send_quote(ctx: Ctx, quote_id: int, send_email: bool, to_emails: list[str] | None) -> Quote:
    quote = get_quote(ctx, quote_id, lock=True)
    if quote.status != "approved":
        raise Conflict("Only an approved quote can be sent")
    before = audit.snapshot(quote)
    qs = get_quote_settings(ctx)
    quote.sent_at = now()
    if quote.valid_until is None or quote.valid_until < today(ctx):
        quote.valid_until = today(ctx) + timedelta(days=qs.valid_days)
    emails: list[str] = []
    if send_email:
        if repo.get_mailbox_status(ctx.db).mailbox is None:
            raise Conflict("Email is not configured (see docs/MAIL_SETUP.md). Download the PDF")
        emails = to_emails or recipients(ctx, quote.organization_id)
        if not emails:
            raise Conflict("No contact with an email address on this client; enter an address")
    quote.sent_to = ", ".join(emails) if emails else None  # before the freeze, not after
    quote.status = "sent"
    ctx.db.flush()
    if send_email:
        name, pdf = quote_pdf(ctx, quote.id)
        s = repo.get_settings_row(ctx.db)
        company = s.company_name or "Your IT provider"
        email = EmailMessage(
            direction="out",
            organization_id=quote.organization_id,
            to_emails=emails,
            subject=f"Managed services proposal from {company}",
            body_text=(
                f"Hello,\n\nThank you for having us visit. Our proposal is attached: "
                f"{format_money(quote.final_price_cents)} per month for {quote.term_months} "
                f"months, valid until {quote.valid_until.isoformat()}.\n\n"
                f"Reply to this email with any questions.\n\n{company}"
            ),
            send_status="pending",
        )
        ctx.db.add(email)
        ctx.db.flush()
        ctx.db.add(
            OutboundAttachment(
                email_message_id=email.id,
                organization_id=quote.organization_id,
                filename=name,
                content_type="application/pdf",
                data=pdf,
            )
        )
    return _changed(ctx, quote, "quote.send", before, {"emailed": send_email, "to": emails})


def decline_quote(ctx: Ctx, quote_id: int, note: str | None) -> Quote:
    quote = get_quote(ctx, quote_id, lock=True)
    if quote.status != "sent":
        raise Conflict("Only a sent quote can be marked declined")
    before = audit.snapshot(quote)
    quote.status, quote.decision_note = "declined", note
    quote.decided_at, quote.decided_by = now(), ctx.user.id if ctx.user else None
    return _changed(ctx, quote, "quote.decline", before)


def accept_quote(ctx: Ctx, quote_id: int, start_date: date | None, note: str | None) -> Quote:
    """Staff record the client's acceptance. New client -> active + flat agreement; a reprice
    ends the old agreement the day before and starts the new price on the effective date."""
    quote = get_quote(ctx, quote_id, lock=True)
    if quote.status != "sent":
        raise Conflict("Only a sent quote can be accepted")
    on = today(ctx)
    if is_expired(ctx, quote):
        raise Conflict("This quote has expired. Revise it to issue a current one")
    org = _org(ctx, quote.organization_id)
    before = audit.snapshot(quote)
    name = f"Managed services (quote Q-{quote.id})"
    taxable = get_quote_settings(ctx).agreement_taxable
    if quote.kind == "reprice":
        old = _reprice_target(ctx, quote.organization_id, quote.agreement_id)
        start = _validate_effective(quote.effective_date, on)
        if old.end_date is not None and old.end_date < start:
            raise Conflict("The agreement being repriced ends before the effective date")
        billed = ctx.db.execute(
            select(InvoiceLine.id)
            .where(
                InvoiceLine.agreement_id == old.id,
                InvoiceLine.voided.is_(False),
                InvoiceLine.period_start >= start,
            )
            .limit(1)
        ).first()
        if billed:
            raise Conflict("That agreement is already invoiced from the effective date on")
        end = old.end_date if old.end_date else contract_end(start, quote.term_months)
        old_before = audit.snapshot(old)
        old.end_date = start - timedelta(days=1)
        ctx.db.flush()
        audit.record(
            ctx.db,
            ctx.user,
            "agreement.update",
            old,
            before=old_before,
            after=audit.snapshot(old),
            organization_id=old.organization_id,
            detail={"reason": f"Repriced by quote Q-{quote.id}"},
        )
    else:
        start = start_date or on
        end = contract_end(start, quote.term_months)
        if org.status == "prospect":
            org_before = audit.snapshot(org)
            org.status = "active"
            ctx.db.flush()
            audit.record(
                ctx.db,
                ctx.user,
                "organization.update",
                org,
                before=org_before,
                after=audit.snapshot(org),
                organization_id=org.id,
                detail={"reason": f"Quote Q-{quote.id} accepted"},
            )
    agreement = create_agreement(
        ctx,
        {
            "organization_id": quote.organization_id,
            "name": name,
            "type": "flat",
            "unit_price_cents": quote.final_price_cents,
            "quantity": 1,
            "taxable": taxable,
            "start_date": start,
            "end_date": end,
            "notes": f"Created from quote Q-{quote.id}",
        },
    )
    quote.status, quote.decision_note = "accepted", note
    quote.decided_at, quote.decided_by = now(), ctx.user.id if ctx.user else None
    quote.resulting_agreement_id = agreement.id
    return _changed(ctx, quote, "quote.accept", before, {"agreement_id": agreement.id})
