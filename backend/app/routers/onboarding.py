"""Setup wizard: Microsoft admin consent (plan 19-02). Admin role only, every step audited.

Always mounted; every route answers 404 unless ONBOARDING_ENABLED is set."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app import audit, onboarding_auth
from app import permissions as P
from app.config import get_settings
from app.deps import Ctx, require
from app.schemas import ErrorOut

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

GUARD_RESPONSES = {403: {"model": ErrorOut}, 404: {"model": ErrorOut}}


class ConsentStartOut(BaseModel):
    url: str


def _admin_only(ctx: Ctx) -> None:
    if not get_settings().onboarding_enabled:
        raise HTTPException(404, "Not found")
    # CONFIG_MANAGE alone is not enough: the wizard acts with directory-wide power. API keys are
    # refused too: consent is an interactive browser flow.
    if ctx.user is None or ctx.user.role != "admin" or ctx.api_key_id is not None:
        raise HTTPException(403, "Only an administrator can run setup")


@router.get(
    "/consent/start",
    response_model=ConsentStartOut,
    summary="Start the one-time Microsoft admin consent for the setup wizard",
    responses={**GUARD_RESPONSES, 503: {"model": ErrorOut}},
)
def consent_start(request: Request, ctx: Ctx = require(P.CONFIG_MANAGE)):
    _admin_only(ctx)
    url = onboarding_auth.start(ctx, request.session)
    audit.record(ctx.db, ctx.user, "onboarding.consent_started")
    return ConsentStartOut(url=url)


@router.get(
    "/consent/callback",
    summary="Microsoft consent redirect target; stores the encrypted token",
    responses={**GUARD_RESPONSES, 400: {"model": ErrorOut}},
)
def consent_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    ctx: Ctx = require(P.CONFIG_MANAGE),
):
    _admin_only(ctx)
    base = f"{get_settings().public_url}/setup"
    if error:  # denied or failed at Microsoft: no code to exchange
        request.session.pop(onboarding_auth.SESSION_KEY, None)
        audit.record(ctx.db, ctx.user, "onboarding.consent_failed", detail={"reason": error[:100]})
        return RedirectResponse(f"{base}?consent=error", status_code=303)
    try:
        onboarding_auth.callback(ctx, request.session, code or "", state or "")
    except HTTPException:
        # The request transaction rolls back on this 400, so audit in its own transaction.
        audit.record_auth_event(
            "onboarding.consent_rejected", user_id=ctx.user.id, detail={"reason": "bad_state"}
        )
        raise
    except onboarding_auth.ConsentFailed as failed:
        audit.record(
            ctx.db, ctx.user, "onboarding.consent_failed", detail={"reason": failed.reason}
        )
        return RedirectResponse(f"{base}?consent=error", status_code=303)
    audit.record(ctx.db, ctx.user, "onboarding.consent_granted")
    return RedirectResponse(f"{base}?consent=ok", status_code=303)
