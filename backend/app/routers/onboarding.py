"""Setup wizard: Microsoft admin consent (plan 19-02), then create, connect and verify the app
registrations and revoke the consent (plan 19-03). Admin role only, every step audited.

Always mounted; every route answers 404 unless ONBOARDING_ENABLED is set."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from app import audit, onboarding, onboarding_auth
from app import permissions as P
from app.config import get_settings
from app.deps import Ctx, require
from app.schemas import (
    ErrorOut,
    OnboardingAppExistsOut,
    OnboardingConnectIn,
    OnboardingConnectOut,
    OnboardingFinishOut,
    OnboardingMailAppIn,
    OnboardingMailAppOut,
    OnboardingPortalAppOut,
    OnboardingStatusOut,
)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

GUARD_RESPONSES = {403: {"model": ErrorOut}, 404: {"model": ErrorOut}}
# Graph failures: 409 sign in again / no Key Vault, 502 Graph or Key Vault failed, 503 throttled
GRAPH_RESPONSES = {
    **GUARD_RESPONSES,
    409: {"model": ErrorOut},
    502: {"model": ErrorOut},
    503: {"model": ErrorOut},
}
CREATE_RESPONSES = {
    **GRAPH_RESPONSES,
    409: {"model": OnboardingAppExistsOut, "description": "Not configured, or the app exists"},
}


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


def _exists(exc: onboarding.AppExists) -> JSONResponse:
    return JSONResponse({"detail": exc.detail, "app_id": exc.app_id}, status_code=409)


@router.get(
    "/status",
    response_model=OnboardingStatusOut,
    summary="Verify the staff SSO, portal SSO, mail and calendar registrations",
    responses=GUARD_RESPONSES,
)
def status(ctx: Ctx = require(P.CONFIG_MANAGE)):
    _admin_only(ctx)
    return OnboardingStatusOut(steps=onboarding.verify(ctx))


@router.post(
    "/portal-app",
    response_model=OnboardingPortalAppOut,
    summary="Create the client portal SSO app registration; its secret goes to Key Vault",
    responses=CREATE_RESPONSES,
)
def create_portal_app(ctx: Ctx = require(P.CONFIG_MANAGE)):
    _admin_only(ctx)
    try:
        return onboarding.create_portal_app(ctx)
    except onboarding.AppExists as exc:
        return _exists(exc)


@router.post(
    "/mail-app",
    response_model=OnboardingMailAppOut,
    summary="Create the Mail & Calendar app registration; its secret goes to Key Vault",
    responses=CREATE_RESPONSES,
)
def create_mail_app(body: OnboardingMailAppIn, ctx: Ctx = require(P.CONFIG_MANAGE)):
    _admin_only(ctx)
    try:
        return onboarding.create_mail_app(ctx, body.mailbox)
    except onboarding.AppExists as exc:
        return _exists(exc)


@router.post(
    "/connect",
    response_model=OnboardingConnectOut,
    summary="Connect an existing app registration after checking it is least privilege",
    responses=GRAPH_RESPONSES,
)
def connect(body: OnboardingConnectIn, ctx: Ctx = require(P.CONFIG_MANAGE)):
    _admin_only(ctx)
    return onboarding.connect_existing(ctx, body.kind, body.app_id, body.mailbox)


@router.post(
    "/finish",
    response_model=OnboardingFinishOut,
    summary="Revoke the setup wizard's admin consent and discard its token",
    responses=GRAPH_RESPONSES,
)
def finish(ctx: Ctx = require(P.CONFIG_MANAGE)):
    _admin_only(ctx)
    return OnboardingFinishOut(removed_scopes=onboarding.finish(ctx))
