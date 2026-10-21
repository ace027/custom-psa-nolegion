"""CRM: leads, the sales pipeline, the forecast and renewal reminders."""

from fastapi import APIRouter

from app import crm as svc
from app import permissions as P
from app import renewals
from app.billing import today
from app.crm_schemas import (
    ForecastOut,
    LeadConvert,
    LeadIn,
    LeadOut,
    LeadPatch,
    OpportunityIn,
    OpportunityOut,
    OpportunityPatch,
    QuoteLink,
    ReminderOut,
    ReminderStatus,
    StageIn,
    StageMove,
    StageOut,
    StagePatch,
)
from app.deps import Ctx, require
from app.models import Agreement, Opportunity
from app.schemas import ErrorOut

router = APIRouter(tags=["crm"])
ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}
NOT_NULL = ("name", "monthly_cents", "term_months")


def _lead_out(ctx: Ctx, lead) -> LeadOut:
    out = LeadOut.model_validate(lead)
    out.owner_name = svc.user_name(ctx, lead.owner_id)
    return out


def _opp_out(ctx: Ctx, opp: Opportunity) -> OpportunityOut:
    from app.models import Organization

    stage = svc.get_stage(ctx, opp.stage_id)
    agreement = ctx.db.get(Agreement, opp.agreement_id) if opp.agreement_id else None
    data = {c: getattr(opp, c) for c in OpportunityOut.model_fields if hasattr(opp, c)}
    return OpportunityOut(
        **{
            **data,
            "organization_name": ctx.db.get(Organization, opp.organization_id).name,
            "stage_name": stage.name,
            "stage_kind": stage.kind,
            "probability_bp": stage.probability_bp,
            "owner_name": svc.user_name(ctx, opp.owner_id),
            "quote_number": f"Q-{opp.quote_id}" if opp.quote_id else None,
            "agreement_name": agreement.name if agreement else None,
        }
    )


def _patch(body) -> dict:
    data = body.model_dump(exclude_unset=True)
    return {k: v for k, v in data.items() if v is not None or (k not in NOT_NULL)}


# ---- leads ----
@router.get("/crm/leads", response_model=list[LeadOut], summary="List sales leads")
def list_leads(
    status: str | None = None,
    owner_id: int | None = None,
    q: str | None = None,
    ctx: Ctx = require(P.CRM_READ),
):
    return [_lead_out(ctx, x) for x in svc.list_leads(ctx, status, owner_id, q)]


@router.post(
    "/crm/leads",
    response_model=LeadOut,
    status_code=201,
    responses=ERR,
    summary="Add a sales lead",
)
def create_lead(body: LeadIn, ctx: Ctx = require(P.CRM_WRITE)):
    return _lead_out(ctx, svc.create_lead(ctx, body.model_dump()))


@router.patch(
    "/crm/leads/{lead_id}",
    response_model=LeadOut,
    responses=ERR,
    summary="Edit a lead (a converted lead is read-only)",
)
def update_lead(lead_id: int, body: LeadPatch, ctx: Ctx = require(P.CRM_WRITE)):
    return _lead_out(ctx, svc.update_lead(ctx, lead_id, _patch(body)))


@router.post(
    "/crm/leads/{lead_id}/convert",
    response_model=OpportunityOut,
    status_code=201,
    responses=ERR,
    summary="Convert a qualified lead to a prospect client, contact and opportunity",
)
def convert_lead(lead_id: int, body: LeadConvert, ctx: Ctx = require(P.CRM_WRITE)):
    return _opp_out(ctx, svc.convert_lead(ctx, lead_id, body.model_dump(exclude_unset=True)))


# ---- opportunities ----
@router.get("/crm/opportunities", response_model=list[OpportunityOut], summary="List opportunities")
def list_opportunities(
    stage_id: int | None = None,
    owner_id: int | None = None,
    organization_id: int | None = None,
    kind: str | None = None,
    open_only: bool = False,
    ctx: Ctx = require(P.CRM_READ),
):
    rows = svc.list_opportunities(ctx, stage_id, owner_id, organization_id, kind, open_only)
    return [_opp_out(ctx, o) for o in rows]


@router.post(
    "/crm/opportunities",
    response_model=OpportunityOut,
    status_code=201,
    responses=ERR,
    summary="Add an opportunity for a client",
)
def create_opportunity(body: OpportunityIn, ctx: Ctx = require(P.CRM_WRITE)):
    return _opp_out(ctx, svc.create_opportunity(ctx, body.model_dump()))


@router.get(
    "/crm/opportunities/{opp_id}",
    response_model=OpportunityOut,
    responses=ERR,
    summary="One opportunity",
)
def get_opportunity(opp_id: int, ctx: Ctx = require(P.CRM_READ)):
    return _opp_out(ctx, svc.get_opportunity(ctx, opp_id))


@router.patch(
    "/crm/opportunities/{opp_id}",
    response_model=OpportunityOut,
    responses=ERR,
    summary="Edit an opportunity",
)
def update_opportunity(opp_id: int, body: OpportunityPatch, ctx: Ctx = require(P.CRM_WRITE)):
    return _opp_out(ctx, svc.update_opportunity(ctx, opp_id, _patch(body)))


@router.post(
    "/crm/opportunities/{opp_id}/stage",
    response_model=OpportunityOut,
    responses=ERR,
    summary="Move an opportunity to a pipeline stage (lost needs a reason)",
)
def move_stage(opp_id: int, body: StageMove, ctx: Ctx = require(P.CRM_WRITE)):
    return _opp_out(ctx, svc.move_stage(ctx, opp_id, body.stage_id, body.lost_reason))


@router.post(
    "/crm/opportunities/{opp_id}/quote",
    response_model=OpportunityOut,
    responses=ERR,
    summary="Link a quote of the same client; accepting it wins the opportunity",
)
def link_quote(opp_id: int, body: QuoteLink, ctx: Ctx = require(P.CRM_WRITE)):
    return _opp_out(ctx, svc.link_quote(ctx, opp_id, body.quote_id))


# ---- forecast ----
@router.get(
    "/crm/forecast",
    response_model=ForecastOut,
    summary="Pipeline forecast by expected close month",
)
def get_forecast(ctx: Ctx = require(P.CRM_READ)):
    return svc.forecast(ctx, today(ctx))


# ---- stages ----
@router.get("/crm/stages", response_model=list[StageOut], summary="Pipeline stages")
def list_stages(ctx: Ctx = require(P.CRM_READ)):
    return svc.list_stages(ctx)


@router.post(
    "/crm/stages",
    response_model=StageOut,
    status_code=201,
    responses=ERR,
    summary="Add a pipeline stage",
)
def create_stage(body: StageIn, ctx: Ctx = require(P.CONFIG_MANAGE)):
    return svc.create_stage(ctx, body.model_dump())


@router.patch(
    "/crm/stages/{stage_id}",
    response_model=StageOut,
    responses=ERR,
    summary="Edit or deactivate a pipeline stage",
)
def update_stage(stage_id: int, body: StagePatch, ctx: Ctx = require(P.CONFIG_MANAGE)):
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    return svc.update_stage(ctx, stage_id, data)


# ---- renewals ----
@router.get(
    "/crm/renewals", response_model=list[ReminderOut], summary="Agreement renewal reminders"
)
def list_renewals(status: ReminderStatus | None = None, ctx: Ctx = require(P.CRM_READ)):
    return renewals.list_reminders(ctx, status)


@router.post(
    "/crm/renewals/{reminder_id}/dismiss",
    response_model=ReminderOut,
    responses=ERR,
    summary="Dismiss a renewal reminder",
)
def dismiss_renewal(reminder_id: int, ctx: Ctx = require(P.CRM_WRITE)):
    return renewals.dismiss(ctx, reminder_id)
