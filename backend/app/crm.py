"""CRM: leads, opportunities, pipeline stages, the forecast and the quote link.

CRM amounts are estimates for forecasting only and never bill; agreements are still created only
by quoting.accept_quote, which calls on_quote_accepted to win the linked opportunities."""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app import audit, services
from app import repositories as repo
from app.deps import Ctx
from app.errors import Conflict, NotFound
from app.models import Agreement, Lead, Opportunity, OpportunityStage, Quote, User
from app.money import BP, round_cents
from app.ticket_services import calendar, now

LEAD_EDITABLE = ("name", "company", "email", "phone", "source", "status", "owner_id", "notes")
OPP_EDITABLE = (
    "name",
    "owner_id",
    "monthly_cents",
    "term_months",
    "expected_close_date",
    "notes",
)
BUCKET_MONTHS = 12


def _flush(ctx: Ctx, message: str) -> None:
    try:
        ctx.db.flush()
    except IntegrityError as exc:
        ctx.db.rollback()
        raise Conflict(message) from exc


def _check_owner(ctx: Ctx, owner_id: int | None) -> None:
    if owner_id is None:
        return
    user = repo.get_user(ctx.db, owner_id)
    if user is None or not user.is_active:
        raise Conflict("Owner must be an active user")


# ---- stages -----------------------------------------------------------------------------------
def list_stages(ctx: Ctx, include_inactive: bool = True) -> list[OpportunityStage]:
    stmt = select(OpportunityStage)
    if not include_inactive:
        stmt = stmt.where(OpportunityStage.active.is_(True))
    return list(
        ctx.db.execute(stmt.order_by(OpportunityStage.position, OpportunityStage.id)).scalars()
    )


def get_stage(ctx: Ctx, stage_id: int) -> OpportunityStage:
    stage = ctx.db.get(OpportunityStage, stage_id)
    if stage is None:
        raise NotFound("Stage not found")
    return stage


def first_open_stage(ctx: Ctx) -> OpportunityStage:
    stage = ctx.db.execute(
        select(OpportunityStage)
        .where(OpportunityStage.kind == "open", OpportunityStage.active.is_(True))
        .order_by(OpportunityStage.position, OpportunityStage.id)
        .limit(1)
    ).scalar_one_or_none()
    if stage is None:
        raise Conflict("No active open pipeline stage exists; add one under Settings")
    return stage


def _active_terminal(ctx: Ctx, kind: str) -> OpportunityStage:
    stage = ctx.db.execute(
        select(OpportunityStage).where(OpportunityStage.kind == kind, OpportunityStage.active)
    ).scalar_one_or_none()
    if stage is None:
        raise Conflict(f"No active {kind} stage exists; add one under Settings")
    return stage


def create_stage(ctx: Ctx, data: dict) -> OpportunityStage:
    stage = OpportunityStage(**data)
    ctx.db.add(stage)
    _flush(
        ctx,
        "A stage with that name already exists, or an active won / lost stage already exists",
    )
    audit.record(ctx.db, ctx.user, "opportunity_stage.create", stage, after=audit.snapshot(stage))
    return stage


def update_stage(ctx: Ctx, stage_id: int, data: dict) -> OpportunityStage:
    stage = get_stage(ctx, stage_id)
    before = audit.snapshot(stage)
    if data.get("active") is False and stage.active:
        others = ctx.db.execute(
            select(func.count())
            .select_from(OpportunityStage)
            .where(
                OpportunityStage.kind == stage.kind,
                OpportunityStage.active,
                OpportunityStage.id != stage.id,
            )
        ).scalar_one()
        if others == 0:
            raise Conflict(
                f"The only active {stage.kind} stage can't be deactivated; add another first"
                if stage.kind != "open"
                else "The only active open stage can't be deactivated; add another first"
            )
    if data.get("active") is True and not stage.active and stage.kind != "open":
        # activating a won / lost stage replaces the one now active (there is only ever one)
        for other in ctx.db.execute(
            select(OpportunityStage).where(
                OpportunityStage.kind == stage.kind, OpportunityStage.active
            )
        ).scalars():
            other.active = False
        ctx.db.flush()
    for key, value in data.items():
        setattr(stage, key, value)
    _flush(ctx, "A stage with that name already exists")
    ctx.db.refresh(stage)
    audit.record(
        ctx.db,
        ctx.user,
        "opportunity_stage.update",
        stage,
        before=before,
        after=audit.snapshot(stage),
    )
    return stage


# ---- leads ------------------------------------------------------------------------------------
def get_lead(ctx: Ctx, lead_id: int, *, lock: bool = False) -> Lead:
    stmt = select(Lead).where(Lead.id == lead_id)
    if lock:
        stmt = stmt.with_for_update()
    lead = ctx.db.execute(stmt).scalar_one_or_none()
    if lead is None:
        raise NotFound("Lead not found")
    return lead


def create_lead(ctx: Ctx, data: dict) -> Lead:
    _check_owner(ctx, data.get("owner_id"))
    lead = Lead(**{**data, "status": data.get("status") or "new"})
    ctx.db.add(lead)
    ctx.db.flush()
    ctx.db.refresh(lead)
    audit.record(ctx.db, ctx.user, "lead.create", lead, after=audit.snapshot(lead))
    return lead


def update_lead(ctx: Ctx, lead_id: int, data: dict) -> Lead:
    lead = get_lead(ctx, lead_id, lock=True)
    if lead.status == "converted":
        raise Conflict("A converted lead is read-only")
    if data.get("status") == "converted":
        raise Conflict("Use convert to turn a lead into an opportunity")
    _check_owner(ctx, data.get("owner_id"))
    before = audit.snapshot(lead)
    for key, value in data.items():
        if key in LEAD_EDITABLE:
            setattr(lead, key, value)
    ctx.db.flush()
    ctx.db.refresh(lead)
    audit.record(ctx.db, ctx.user, "lead.update", lead, before=before, after=audit.snapshot(lead))
    return lead


def list_leads(
    ctx: Ctx, status: str | None = None, owner_id: int | None = None, q: str | None = None
) -> list[Lead]:
    stmt = select(Lead)
    if status:
        stmt = stmt.where(Lead.status == status)
    if owner_id is not None:
        stmt = stmt.where(Lead.owner_id == owner_id)
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Lead.name).like(like),
                func.lower(func.coalesce(Lead.company, "")).like(like),
                func.lower(func.coalesce(Lead.email, "")).like(like),
            )
        )
    return list(ctx.db.execute(stmt.order_by(Lead.id.desc())).scalars())


def convert_lead(ctx: Ctx, lead_id: int, data: dict) -> Opportunity:
    """A qualified lead becomes a prospect organization, its primary contact and an open
    opportunity at the first open stage. A lead converts once."""
    lead = get_lead(ctx, lead_id, lock=True)
    if lead.status == "converted":
        raise Conflict("This lead has already been converted")
    if lead.status != "qualified":
        raise Conflict("Only a qualified lead can be converted")
    stage = first_open_stage(ctx)
    org = services.create_organization(
        ctx, {"name": (lead.company or lead.name).strip(), "status": "prospect"}
    )
    services.create_contact(
        ctx,
        org.id,
        {"name": lead.name, "email": lead.email, "phone": lead.phone, "is_primary": True},
    )
    owner_id = lead.owner_id or (ctx.user.id if ctx.user else None)
    opp = Opportunity(
        organization_id=org.id,
        name=data.get("name") or f"{org.name} - new managed services",
        kind="new",
        stage_id=stage.id,
        owner_id=owner_id,
        monthly_cents=data.get("monthly_cents", 0),
        term_months=data.get("term_months", 12),
        expected_close_date=data.get("expected_close_date"),
        notes=data.get("notes"),
    )
    ctx.db.add(opp)
    ctx.db.flush()
    before = audit.snapshot(lead)
    lead.status, lead.converted_organization_id, lead.converted_at = "converted", org.id, now()
    ctx.db.flush()
    audit.record(
        ctx.db,
        ctx.user,
        "lead.convert",
        lead,
        before=before,
        after=audit.snapshot(lead),
        detail={"organization_id": org.id, "opportunity_id": opp.id},
    )
    audit.record(
        ctx.db,
        ctx.user,
        "opportunity.create",
        opp,
        after=audit.snapshot(opp),
        organization_id=org.id,
    )
    ctx.db.refresh(opp)
    return opp


# ---- opportunities ----------------------------------------------------------------------------
def get_opportunity(ctx: Ctx, opp_id: int, *, lock: bool = False) -> Opportunity:
    stmt = ctx.scope.apply(
        select(Opportunity).where(Opportunity.id == opp_id), Opportunity.organization_id
    )
    if lock:
        stmt = stmt.with_for_update()
    opp = ctx.db.execute(stmt).scalar_one_or_none()
    if opp is None:
        raise NotFound("Opportunity not found")
    return opp


def is_open(ctx: Ctx, opp: Opportunity) -> bool:
    return get_stage(ctx, opp.stage_id).kind == "open"


def create_opportunity(ctx: Ctx, data: dict) -> Opportunity:
    if repo.get_organization(ctx.db, ctx.scope, data["organization_id"]) is None:
        raise NotFound("Organization not found")
    _check_owner(ctx, data.get("owner_id"))
    if data.get("stage_id") is None:
        stage = first_open_stage(ctx)
    else:
        stage = get_stage(ctx, data["stage_id"])
        if stage.kind != "open" or not stage.active:
            raise Conflict("A new opportunity must start in an active open stage")
    values = {k: v for k, v in data.items() if k != "stage_id"}
    if values.get("owner_id") is None and ctx.user is not None:
        values["owner_id"] = ctx.user.id
    opp = Opportunity(stage_id=stage.id, **values)
    ctx.db.add(opp)
    _flush(ctx, "That agreement does not belong to this client")
    ctx.db.refresh(opp)
    audit.record(
        ctx.db,
        ctx.user,
        "opportunity.create",
        opp,
        after=audit.snapshot(opp),
        organization_id=opp.organization_id,
    )
    return opp


def update_opportunity(ctx: Ctx, opp_id: int, data: dict) -> Opportunity:
    opp = get_opportunity(ctx, opp_id, lock=True)
    _check_owner(ctx, data.get("owner_id"))
    before = audit.snapshot(opp)
    for key, value in data.items():
        if key in OPP_EDITABLE:
            setattr(opp, key, value)
    ctx.db.flush()
    ctx.db.refresh(opp)
    audit.record(
        ctx.db,
        ctx.user,
        "opportunity.update",
        opp,
        before=before,
        after=audit.snapshot(opp),
        organization_id=opp.organization_id,
    )
    return opp


def move_stage(ctx: Ctx, opp_id: int, stage_id: int, lost_reason: str | None = None) -> Opportunity:
    opp = get_opportunity(ctx, opp_id, lock=True)
    stage = get_stage(ctx, stage_id)
    if not stage.active:
        raise Conflict("That stage is no longer in use")
    reason = (lost_reason or "").strip()
    if stage.kind == "lost" and not reason:
        raise Conflict("A lost reason is required to move an opportunity to a lost stage")
    before = audit.snapshot(opp)
    opp.stage_id = stage.id
    if stage.kind == "open":
        opp.closed_at, opp.lost_reason = None, None
    else:
        if opp.closed_at is None:
            opp.closed_at = now()
        opp.lost_reason = reason if stage.kind == "lost" else None
    ctx.db.flush()
    ctx.db.refresh(opp)
    audit.record(
        ctx.db,
        ctx.user,
        "opportunity.move",
        opp,
        before=before,
        after=audit.snapshot(opp),
        organization_id=opp.organization_id,
        detail={"stage": stage.name, "kind": stage.kind},
    )
    return opp


def list_opportunities(
    ctx: Ctx,
    stage_id: int | None = None,
    owner_id: int | None = None,
    organization_id: int | None = None,
    kind: str | None = None,
    open_only: bool = False,
) -> list[Opportunity]:
    stmt = ctx.scope.apply(select(Opportunity), Opportunity.organization_id)
    if stage_id is not None:
        stmt = stmt.where(Opportunity.stage_id == stage_id)
    if owner_id is not None:
        stmt = stmt.where(Opportunity.owner_id == owner_id)
    if organization_id is not None:
        stmt = stmt.where(Opportunity.organization_id == organization_id)
    if kind:
        stmt = stmt.where(Opportunity.kind == kind)
    if open_only:
        stmt = stmt.join(OpportunityStage, OpportunityStage.id == Opportunity.stage_id).where(
            OpportunityStage.kind == "open"
        )
    stmt = stmt.order_by(Opportunity.expected_close_date.asc().nulls_last(), Opportunity.id)
    return list(ctx.db.execute(stmt).scalars())


def link_quote(ctx: Ctx, opp_id: int, quote_id: int) -> Opportunity:
    from app.quoting import OPEN

    opp = get_opportunity(ctx, opp_id, lock=True)
    if not is_open(ctx, opp):
        raise Conflict("A closed opportunity can't be linked to a quote")
    quote = (
        ctx.db.execute(
            ctx.scope.apply(select(Quote).where(Quote.id == quote_id), Quote.organization_id)
        )
        .unique()
        .scalar_one_or_none()
    )
    if quote is None or quote.organization_id != opp.organization_id:
        raise Conflict("That quote belongs to a different client")
    if quote.status not in OPEN:
        raise Conflict(f"A {quote.status} quote can't be linked; revise it or pick another")
    before = audit.snapshot(opp)
    opp.quote_id = quote.id
    ctx.db.flush()
    ctx.db.refresh(opp)
    audit.record(
        ctx.db,
        ctx.user,
        "opportunity.link_quote",
        opp,
        before=before,
        after=audit.snapshot(opp),
        organization_id=opp.organization_id,
        detail={"quote_id": quote.id},
    )
    return opp


def on_quote_accepted(ctx: Ctx, quote: Quote, agreement: Agreement) -> list[Opportunity]:
    """Accepting a quote wins every open opportunity linked to it. A renewal opportunity keeps
    the agreement it renews; others record the agreement the quote created."""
    opps = list(
        ctx.db.execute(
            select(Opportunity)
            .join(OpportunityStage, OpportunityStage.id == Opportunity.stage_id)
            .where(Opportunity.quote_id == quote.id, OpportunityStage.kind == "open")
            .with_for_update(of=Opportunity)
        ).scalars()
    )
    if not opps:
        return []
    won = _active_terminal(ctx, "won")
    for opp in opps:
        before = audit.snapshot(opp)
        opp.stage_id, opp.closed_at, opp.lost_reason = won.id, now(), None
        if opp.agreement_id is None:
            opp.agreement_id = agreement.id
        ctx.db.flush()
        audit.record(
            ctx.db,
            ctx.user,
            "opportunity.won",
            opp,
            before=before,
            after=audit.snapshot(opp),
            organization_id=opp.organization_id,
            detail={"quote_id": quote.id, "agreement_id": agreement.id},
        )
    return opps


# ---- forecast ---------------------------------------------------------------------------------
def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _bucket(key: str, label: str) -> dict:
    return {
        "key": key,
        "label": label,
        "count": 0,
        "monthly_cents": 0,
        "weighted_monthly_cents": 0,
        "contract_value_cents": 0,
    }


def _add(bucket: dict, monthly: int, weighted: int, term: int) -> None:
    bucket["count"] += 1
    bucket["monthly_cents"] += monthly
    bucket["weighted_monthly_cents"] += weighted
    bucket["contract_value_cents"] += monthly * term


def forecast(ctx: Ctx, today: date) -> dict:
    """Open opportunities by expected close month: overdue, the next 12 months, later, no date."""
    buckets = {"overdue": _bucket("overdue", "Overdue")}
    for i in range(BUCKET_MONTHS):
        y, m = divmod(today.month - 1 + i, 12)
        d = date(today.year + y, m + 1, 1)
        buckets[_month_key(d)] = _bucket(_month_key(d), d.strftime("%b %Y"))
    buckets["later"] = _bucket("later", "Later")
    buckets["no_date"] = _bucket("no_date", "No date")
    total = _bucket("total", "Total")

    rows = ctx.db.execute(
        ctx.scope.apply(
            select(Opportunity, OpportunityStage.probability_bp, OpportunityStage.kind).join(
                OpportunityStage, OpportunityStage.id == Opportunity.stage_id
            ),
            Opportunity.organization_id,
        )
    ).all()
    tz = calendar(ctx).tz
    month_start = today.replace(day=1)
    quarter_start = date(today.year, 3 * ((today.month - 1) // 3) + 1, 1)
    won_month, won_quarter = _bucket("month", "This month"), _bucket("quarter", "This quarter")
    for opp, bp, kind in rows:
        if kind == "won" and opp.closed_at is not None:
            closed = opp.closed_at.astimezone(tz).date()
            for start, target in ((month_start, won_month), (quarter_start, won_quarter)):
                if start <= closed <= today:
                    _add(target, opp.monthly_cents, opp.monthly_cents, opp.term_months)
            continue
        if kind != "open":
            continue
        weighted = round_cents(Decimal(opp.monthly_cents) * bp / BP)
        d = opp.expected_close_date
        if d is None:
            key = "no_date"
        elif d < today:
            key = "overdue"
        else:
            key = _month_key(d) if _month_key(d) in buckets else "later"
        _add(buckets[key], opp.monthly_cents, weighted, opp.term_months)
        _add(total, opp.monthly_cents, weighted, opp.term_months)
    return {
        "buckets": list(buckets.values()),
        "total": total,
        "won_this_month": won_month,
        "won_this_quarter": won_quarter,
    }


def user_name(ctx: Ctx, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    user = ctx.db.get(User, user_id)
    return user.display_name if user else None
