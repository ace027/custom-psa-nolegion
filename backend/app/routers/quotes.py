"""New-client quoting: rate card, onsite surveys, quotes (docs/QUOTING.md)."""

from fastapi import APIRouter, Response

from app import permissions as P
from app import quoting as svc
from app.deps import Ctx, require
from app.quote_schemas import (
    NoteIn,
    OptionalNoteIn,
    QuoteAccept,
    QuoteCreate,
    QuoteOut,
    QuotePatch,
    QuoteSend,
    QuoteSettingsOut,
    QuoteSettingsPatch,
    SurveyCreate,
    SurveyOut,
    SurveySave,
)
from app.schemas import ErrorOut

router = APIRouter(tags=["quotes"])
ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}


def _survey_out(s) -> SurveyOut:
    out = SurveyOut.model_validate(s)
    out.organization_name = s.organization.name
    return out


def _quote_out(ctx: Ctx, q) -> QuoteOut:
    data = {c: getattr(q, c) for c in QuoteOut.model_fields if hasattr(q, c)}
    return QuoteOut(
        **{
            **data,
            "number": f"Q-{q.id}",
            "organization_name": q.organization.name,
            "is_expired": svc.is_expired(ctx, q),
        }
    )


# ---- rate card ----
@router.get("/quotes/settings", response_model=QuoteSettingsOut, summary="The quoting rate card")
def get_settings(ctx: Ctx = require(P.QUOTE_READ)):
    return svc.get_quote_settings(ctx)


@router.patch(
    "/quotes/settings",
    response_model=QuoteSettingsOut,
    summary="Edit the rate card, uplift percentages, term and validity",
)
def patch_settings(body: QuoteSettingsPatch, ctx: Ctx = require(P.QUOTE_MANAGE)):
    return svc.update_quote_settings(ctx, body.model_dump(exclude_unset=True, exclude_none=True))


# ---- surveys ----
@router.post(
    "/organizations/{org_id}/surveys",
    response_model=SurveyOut,
    status_code=201,
    responses=ERR,
    summary="Schedule an onsite survey for a prospect or client",
)
def create_survey(org_id: int, body: SurveyCreate, ctx: Ctx = require(P.QUOTE_WRITE)):
    return _survey_out(svc.create_survey(ctx, org_id, body.model_dump()))


@router.get("/surveys", response_model=list[SurveyOut], summary="List onsite surveys")
def list_surveys(
    organization_id: int | None = None,
    status: str | None = None,
    ctx: Ctx = require(P.QUOTE_READ),
):
    return [_survey_out(s) for s in svc.list_surveys(ctx, organization_id, status)]


@router.get("/surveys/{survey_id}", response_model=SurveyOut, responses=ERR, summary="One survey")
def get_survey(survey_id: int, ctx: Ctx = require(P.QUOTE_READ)):
    return _survey_out(svc.get_survey(ctx, survey_id))


@router.put(
    "/surveys/{survey_id}",
    response_model=SurveyOut,
    responses=ERR,
    summary="Save the survey answers (replaces devices and applications); autosave-friendly",
)
def save_survey(survey_id: int, body: SurveySave, ctx: Ctx = require(P.QUOTE_WRITE)):
    return _survey_out(svc.save_survey(ctx, survey_id, body.model_dump()))


@router.post(
    "/surveys/{survey_id}/complete",
    response_model=SurveyOut,
    responses=ERR,
    summary="Mark the survey completed (it can no longer be edited)",
)
def complete_survey(survey_id: int, ctx: Ctx = require(P.QUOTE_WRITE)):
    return _survey_out(svc.complete_survey(ctx, survey_id))


@router.post(
    "/surveys/{survey_id}/quote",
    response_model=QuoteOut,
    status_code=201,
    responses=ERR,
    summary="Price a completed survey: creates a draft quote with the full breakdown",
)
def create_quote(survey_id: int, body: QuoteCreate, ctx: Ctx = require(P.QUOTE_WRITE)):
    return _quote_out(ctx, svc.create_quote(ctx, survey_id, body.model_dump()))


# ---- quotes ----
@router.get("/quotes", response_model=list[QuoteOut], summary="List quotes")
def list_quotes(
    organization_id: int | None = None,
    status: str | None = None,
    ctx: Ctx = require(P.QUOTE_READ),
):
    return [_quote_out(ctx, q) for q in svc.list_quotes(ctx, organization_id, status)]


@router.get("/quotes/{quote_id}", response_model=QuoteOut, responses=ERR, summary="One quote")
def get_quote(quote_id: int, ctx: Ctx = require(P.QUOTE_READ)):
    return _quote_out(ctx, svc.get_quote(ctx, quote_id))


@router.patch(
    "/quotes/{quote_id}",
    response_model=QuoteOut,
    responses=ERR,
    summary="Adjust the price (reason required) or details; resets any approval",
)
def patch_quote(quote_id: int, body: QuotePatch, ctx: Ctx = require(P.QUOTE_WRITE)):
    return _quote_out(ctx, svc.adjust_quote(ctx, quote_id, body.model_dump(exclude_unset=True)))


@router.post(
    "/quotes/{quote_id}/submit",
    response_model=QuoteOut,
    responses=ERR,
    summary="Submit for approval (an unadjusted quote is approved automatically)",
)
def submit_quote(quote_id: int, ctx: Ctx = require(P.QUOTE_WRITE)):
    return _quote_out(ctx, svc.submit_quote(ctx, quote_id))


@router.post(
    "/quotes/{quote_id}/approve",
    response_model=QuoteOut,
    responses=ERR,
    summary="Approve an adjusted price (not your own change)",
)
def approve_quote(quote_id: int, ctx: Ctx = require(P.QUOTE_MANAGE)):
    return _quote_out(ctx, svc.approve_quote(ctx, quote_id))


@router.post(
    "/quotes/{quote_id}/reject",
    response_model=QuoteOut,
    responses=ERR,
    summary="Send an adjusted quote back to draft with a note",
)
def reject_quote(quote_id: int, body: NoteIn, ctx: Ctx = require(P.QUOTE_MANAGE)):
    return _quote_out(ctx, svc.reject_quote(ctx, quote_id, body.note))


@router.post(
    "/quotes/{quote_id}/send",
    response_model=QuoteOut,
    responses=ERR,
    summary="Mark an approved quote sent, optionally emailing the PDF; it is then frozen",
)
def send_quote(quote_id: int, body: QuoteSend, ctx: Ctx = require(P.QUOTE_WRITE)):
    return _quote_out(
        ctx, svc.send_quote(ctx, quote_id, body.send_email, [str(e) for e in body.to_emails or []])
    )


@router.post(
    "/quotes/{quote_id}/accept",
    response_model=QuoteOut,
    responses=ERR,
    summary="Record acceptance: activates the prospect and creates the flat-fee agreement",
)
def accept_quote(quote_id: int, body: QuoteAccept, ctx: Ctx = require(P.QUOTE_MANAGE)):
    return _quote_out(ctx, svc.accept_quote(ctx, quote_id, body.start_date, body.note))


@router.post(
    "/quotes/{quote_id}/decline",
    response_model=QuoteOut,
    responses=ERR,
    summary="Record that the client declined",
)
def decline_quote(quote_id: int, body: OptionalNoteIn, ctx: Ctx = require(P.QUOTE_MANAGE)):
    return _quote_out(ctx, svc.decline_quote(ctx, quote_id, body.note))


@router.post(
    "/quotes/{quote_id}/cancel",
    response_model=QuoteOut,
    responses=ERR,
    summary="Cancel an open quote",
)
def cancel_quote(quote_id: int, body: OptionalNoteIn, ctx: Ctx = require(P.QUOTE_WRITE)):
    return _quote_out(ctx, svc.cancel_quote(ctx, quote_id, body.note))


@router.post(
    "/quotes/{quote_id}/revise",
    response_model=QuoteOut,
    status_code=201,
    responses=ERR,
    summary="New draft version from the same survey at today's rates; closes the old one",
)
def revise_quote(quote_id: int, ctx: Ctx = require(P.QUOTE_WRITE)):
    return _quote_out(ctx, svc.revise_quote(ctx, quote_id))


@router.get(
    "/quotes/{quote_id}/pdf",
    response_class=Response,
    responses=ERR,
    summary="Download the client proposal as a PDF",
)
def quote_pdf(quote_id: int, ctx: Ctx = require(P.QUOTE_READ)):
    name, pdf = svc.quote_pdf(ctx, quote_id)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
