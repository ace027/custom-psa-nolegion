"""Client portal API. Signed-in endpoints see only the contact's own organization; the
unauthenticated ones (request / redeem a sign-in link, login options, Microsoft sign-in) reveal
nothing about who has access: every SSO denial ends on the same /portal?sso=denied redirect, and
every first (email-matched) Microsoft sign-in ends on /portal?sso=confirm whether or not mail went
out."""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from app import audit
from app import billing_repo as brepo
from app import portal as svc
from app import portal_files as pfiles
from app import repositories as repo
from app import ticket_services as tsvc
from app.asset_schemas import PortalAssetsOut
from app.auth import oidc, portal_sessions
from app.config import get_settings
from app.context import client_ip_var
from app.invoice_pdf import render_invoice_pdf
from app.notices import build_statement
from app.portal_deps import (
    PortalCtx,
    billing_only,
    devices_only,
    portal_enabled,
    portal_required,
    public_session,
)
from app.portal_schemas import (
    PortalAttachmentIn,
    PortalAttachmentOut,
    PortalContactPatch,
    PortalLoginOptionsOut,
)
from app.scheduling_schemas import PortalAppointmentOut
from app.schemas import (
    ErrorOut,
    PortalInvoiceDetail,
    PortalInvoiceOut,
    PortalLinkIn,
    PortalMeOut,
    PortalNoticeOut,
    PortalReplyIn,
    PortalTicketDetail,
    PortalTicketIn,
    PortalTicketOut,
    PortalVerifyIn,
)
from app.scope import Scope
from app.statement_pdf import render_statement_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portal", tags=["portal"])
SSO_CONFIRM_COOKIE = "psa_portal_sso_confirm"
SSO_CONFIRM_PATH = "/api/v1/portal"
ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}


def _cookie_args() -> dict:
    s = get_settings()
    return dict(path="/", httponly=True, secure=s.is_production, samesite="lax")


# ---- signing in (public) ----
@router.post(
    "/login-link",
    status_code=202,
    response_model=PortalNoticeOut,
    summary="Ask for a one-time sign-in link by email (always answers the same way)",
)
def request_link(body: PortalLinkIn, db: Session = Depends(public_session)):
    result = svc.request_link(db, body.email, client_ip_var.get())
    audit.record_auth_event(
        "portal.login_link_requested",
        detail={k: v for k, v in result.items() if v not in (None, False)},
    )
    return PortalNoticeOut(
        detail="If that address has portal access, a sign-in link is on its way. It works once."
    )


@router.post(
    "/verify",
    response_model=PortalMeOut,
    summary="Redeem a sign-in link and start a portal session",
)
def verify(
    body: PortalVerifyIn,
    request: Request,
    response: Response,
    db: Session = Depends(public_session),
):
    enabled = repo.get_settings_row(db).portal_enabled
    link = portal_sessions.consume_link_token(db, body.token) if enabled else None
    if link is None:
        audit.record_auth_event("portal.login_failed", detail={"reason": "bad_or_used_link"})
        raise HTTPException(status_code=401, detail="This link has expired or was already used")
    contact = link.contact
    login_detail: dict = {"contact_id": contact.id}
    if link.bind_entra_oid:
        # A confirmation link from a first Microsoft sign-in. Redeeming it proves control of the
        # contact's mailbox, so it always signs in; the oid is bound only if still consistent.
        login_detail["method"] = "sso_confirm"
        try:
            same_browser = portal_sessions.browser_matches(
                request.cookies.get(SSO_CONFIRM_COOKIE), link.bind_browser_hash
            )
            skipped = oidc.bind_confirmed_oid(
                db,
                contact,
                link.bind_entra_oid,
                link.bind_entra_tenant_id or "",
                same_browser=same_browser,
            )
        except oidc.PortalLoginDenied as e:
            db.rollback()  # also un-consumes the link; a retry re-checks and skips the bind
            audit.record_auth_event(
                "portal.login_failed", detail={"reason": e.reason, "method": "sso_confirm"}
            )
            raise HTTPException(
                status_code=401, detail="This link has expired or was already used"
            ) from None
        if skipped:
            audit.record_auth_event(
                "portal.sso_link_skipped", detail={"contact_id": contact.id, "reason": skipped}
            )
        else:
            audit.record_auth_event("portal.sso_linked", detail={"contact_id": contact.id})
        response.delete_cookie(SSO_CONFIRM_COOKIE, path=SSO_CONFIRM_PATH)
    cookie = portal_sessions.create_session(
        db, contact, client_ip_var.get(), request.headers.get("user-agent")
    )
    db.flush()
    audit.record_auth_event("portal.login", detail=login_detail)
    s = get_settings()
    response.set_cookie(
        s.portal_cookie_name, cookie, max_age=s.portal_session_hours * 3600, **_cookie_args()
    )
    ctx = PortalCtx(db=db, user=None, scope=Scope.orgs(contact.organization_id), contact=contact)
    return svc.me(ctx)


# ---- Sign in with Microsoft (multi-tenant portal app registration; docs/PORTAL_SSO.md) ----
def _sso_available(db: Session) -> bool:
    return get_settings().portal_sso_configured and portal_enabled(db)


@router.get(
    "/login-options",
    response_model=PortalLoginOptionsOut,
    summary="Which portal sign-in methods are available (public)",
)
def login_options(db: Session = Depends(public_session)):
    return PortalLoginOptionsOut(sso=_sso_available(db))


@router.get(
    "/sso/login",
    status_code=302,
    responses={404: {"model": ErrorOut}},
    summary="Start Sign in with Microsoft for the portal (redirects to Microsoft)",
)
async def sso_login(request: Request, db: Session = Depends(public_session)):
    if not _sso_available(db):
        raise HTTPException(status_code=404, detail="Not found")
    redirect_uri = f"{get_settings().public_url}/api/v1/portal/sso/callback"
    return await oidc.get_oauth().entra_portal.authorize_redirect(request, redirect_uri)


@router.get(
    "/sso/callback",
    status_code=303,
    summary="Microsoft redirect target for portal sign-in; starts a portal session",
)
async def sso_callback(request: Request, db: Session = Depends(public_session)):
    s = get_settings()
    denied = RedirectResponse(f"{s.public_url}/portal?sso=denied", status_code=303)

    def deny(reason: str) -> RedirectResponse:
        db.rollback()
        audit.record_auth_event("portal.login_failed", detail={"reason": reason, "method": "sso"})
        return denied

    if not s.portal_sso_configured:
        return deny("not_configured")
    if not portal_enabled(db):
        return deny("portal_disabled")
    try:
        token = await oidc.get_oauth().entra_portal.authorize_access_token(
            request, claims_options=oidc.portal_claims_options()
        )
        claims = dict(token.get("userinfo") or {})
    except Exception as exc:
        # The audit row records only a generic reason; the log keeps the cause (state mismatch,
        # bad issuer, expired code, network error) without the token itself.
        logger.warning("portal sign-in token exchange failed: %s: %s", type(exc).__name__, exc)
        return deny("token_exchange")
    try:
        match = oidc.resolve_contact_from_claims(db, claims)
    except oidc.PortalLoginDenied as e:
        return deny(e.reason)
    contact = match.contact
    if not match.bound:
        # Matched by the (unverified) email claim only: never sign in or bind on that. Email the
        # contact a one-time link that carries the pending binding. Every outcome, including rate
        # limiting and mail being off, ends on the same redirect. The binding is also tied to
        # THIS browser (cookie secret, hash on the token) so the mailbox owner clicking the link
        # elsewhere cannot link a Microsoft account they did not sign in with.
        secret, secret_hash = portal_sessions.new_browser_secret()
        result = svc.send_link(
            db,
            contact,
            client_ip_var.get(),
            bind_entra_oid=match.oid,
            bind_entra_tenant_id=match.tid,
            bind_browser_hash=secret_hash,
        )
        if result["reason"] == "rate_limited":
            audit.record_auth_event(
                "portal.sso_link_rate_limited", detail={"contact_id": contact.id}
            )
        else:
            audit.record_auth_event(
                "portal.sso_link_requested",
                detail={k: v for k, v in result.items() if v is not None},
            )
        confirm = RedirectResponse(f"{s.public_url}/portal?sso=confirm", status_code=303)
        if result["sent"]:
            confirm.set_cookie(
                SSO_CONFIRM_COOKIE,
                secret,
                max_age=s.portal_link_minutes * 60,
                **{**_cookie_args(), "path": SSO_CONFIRM_PATH},
            )
        return confirm
    cookie = portal_sessions.create_session(
        db, contact, client_ip_var.get(), request.headers.get("user-agent")
    )
    db.flush()
    audit.record_auth_event("portal.login", detail={"contact_id": contact.id, "method": "sso"})
    response = RedirectResponse(f"{s.public_url}/portal", status_code=303)
    response.set_cookie(
        s.portal_cookie_name, cookie, max_age=s.portal_session_hours * 3600, **_cookie_args()
    )
    return response


@router.post("/logout", status_code=204, summary="End the portal session")
def logout(request: Request, response: Response, ctx: PortalCtx = portal_required()):
    token = request.cookies.get(get_settings().portal_cookie_name)
    if token:
        portal_sessions.delete_session(ctx.db, token)
    audit.record_auth_event("portal.logout", detail={"contact_id": ctx.contact.id})
    response.delete_cookie(get_settings().portal_cookie_name, path="/")
    response.status_code = 204
    return response


@router.get(
    "/me", response_model=PortalMeOut, summary="The signed-in contact and what they can see"
)
def me(ctx: PortalCtx = portal_required()):
    return svc.me(ctx)


@router.patch(
    "/me/contact",
    response_model=PortalMeOut,
    summary="Edit your own name, phone and title (not your email); fields left out are kept",
)
def update_me(body: PortalContactPatch, ctx: PortalCtx = portal_required()):
    return svc.update_contact(ctx, body.model_dump(exclude_unset=True))


# ---- CSV exports ----
EXPORT_200 = {
    "content": {"text/csv": {}},
    "headers": {
        "X-Export-Truncated": {
            "description": "true when the export hit the row cap and older rows were left out",
            "schema": {"type": "string", "enum": ["true", "false"]},
        }
    },
}


def _csv(kind: str, export: tuple[str, bool]) -> Response:
    text, truncated = export
    return Response(
        text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{kind}-{date.today().isoformat()}.csv"',
            "X-Content-Type-Options": "nosniff",
            "X-Export-Truncated": "true" if truncated else "false",
        },
    )


@router.get(
    "/export/tickets.csv",
    responses={200: EXPORT_200},
    summary="Export your tickets as CSV",
)
def export_tickets(ctx: PortalCtx = portal_required()):
    return _csv("tickets", svc.export_tickets(ctx))


@router.get(
    "/export/invoices.csv",
    responses={200: EXPORT_200, 403: {"model": ErrorOut}},
    summary="Export your finalized invoices as CSV (billing contacts)",
)
def export_invoices(ctx: PortalCtx = portal_required()):
    billing_only(ctx)
    return _csv("invoices", svc.export_invoices(ctx))


@router.get(
    "/export/devices.csv",
    responses={200: EXPORT_200, 403: {"model": ErrorOut}},
    summary="Export your devices and warranty status as CSV (designated contacts only)",
)
def export_devices(ctx: PortalCtx = portal_required()):
    devices_only(ctx)
    return _csv("devices", svc.export_devices(ctx))


# ---- billing (billing contacts only) ----
@router.get(
    "/invoices",
    response_model=list[PortalInvoiceOut],
    summary="Your finalized invoices with payment status (billing contacts)",
)
def invoices(ctx: PortalCtx = portal_required()):
    billing_only(ctx)
    return svc.list_invoices(ctx)


@router.get(
    "/invoices/{invoice_id}",
    response_model=PortalInvoiceDetail,
    responses=ERR,
    summary="One invoice with its lines (billing contacts)",
)
def invoice(invoice_id: int, ctx: PortalCtx = portal_required()):
    billing_only(ctx)
    return svc.invoice_detail(ctx, invoice_id)


@router.get(
    "/invoices/{invoice_id}/pdf",
    responses={**ERR, 200: {"content": {"application/pdf": {}}}},
    summary="Download an invoice PDF (billing contacts)",
)
def invoice_pdf(invoice_id: int, ctx: PortalCtx = portal_required()):
    billing_only(ctx)
    inv = svc.get_final_invoice(ctx, invoice_id)
    lines = brepo.invoice_lines(ctx.db, ctx.scope, inv.id)
    data = render_invoice_pdf(inv, lines, repo.get_settings_row(ctx.db))
    return Response(
        data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{inv.number}.pdf"'},
    )


@router.get(
    "/statement/pdf",
    responses={200: {"content": {"application/pdf": {}}}},
    summary="Download your current account statement (billing contacts)",
)
def statement_pdf(ctx: PortalCtx = portal_required()):
    billing_only(ctx)
    org = repo.get_organization(ctx.db, ctx.scope, ctx.contact.organization_id)
    snap = build_statement(ctx, org)
    return Response(
        render_statement_pdf(snap),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Statement-{snap["as_of"]}.pdf"'},
    )


# ---- devices and warranty ----
@router.get(
    "/assets",
    response_model=PortalAssetsOut,
    responses={403: {"model": ErrorOut}},
    summary="Your devices and their warranty status (designated contacts only)",
)
def devices(ctx: PortalCtx = portal_required()):
    devices_only(ctx)
    return svc.list_devices(ctx)


# ---- appointments ----
@router.get(
    "/appointments",
    response_model=list[PortalAppointmentOut],
    summary="Your upcoming and recent appointments (client-visible, scheduled only)",
)
def appointments(ctx: PortalCtx = portal_required()):
    return svc.list_appointments(ctx, tsvc.now())


# ---- tickets ----
@router.get("/tickets", response_model=list[PortalTicketOut], summary="Your tickets")
def tickets(ctx: PortalCtx = portal_required()):
    return svc.list_tickets(ctx)


@router.post(
    "/tickets",
    status_code=201,
    response_model=PortalTicketOut,
    responses=ERR,
    summary="Open a new ticket",
)
def open_ticket(body: PortalTicketIn, ctx: PortalCtx = portal_required()):
    return svc.create_ticket(ctx, body.subject, body.description)


@router.get(
    "/tickets/{ticket_id}",
    response_model=PortalTicketDetail,
    responses=ERR,
    summary="A ticket with its customer-visible conversation",
)
def ticket(ticket_id: int, ctx: PortalCtx = portal_required()):
    return svc.ticket_detail(ctx, ticket_id)


@router.get(
    "/tickets/{ticket_id}/attachments",
    response_model=list[PortalAttachmentOut],
    responses=ERR,
    summary="Files you attached to a ticket through the portal",
)
def list_ticket_attachments(ticket_id: int, ctx: PortalCtx = portal_required()):
    return pfiles.list_for_ticket(ctx, ticket_id)


def upload_ticket_attachment(
    ticket_id: int, body: PortalAttachmentIn, ctx: PortalCtx = portal_required()
):
    return pfiles.upload(ctx, ticket_id, body.filename, body.content_base64)


router.add_api_route(
    "/tickets/{ticket_id}/attachments",
    upload_ticket_attachment,
    methods=["POST"],
    status_code=201,
    response_model=PortalAttachmentOut,
    responses={**ERR, 413: {"model": ErrorOut}, 415: {"model": ErrorOut}, 429: {"model": ErrorOut}},
    summary="Attach a file (base64) to one of your open tickets",
    route_class_override=pfiles.SizeLimitedRoute,
)


@router.get(
    "/attachments/{attachment_id}/download",
    response_class=FileResponse,
    responses=ERR,
    summary="Download a file attached through the portal (always as a download)",
)
def download_attachment(attachment_id: int, ctx: PortalCtx = portal_required()):
    path, name = pfiles.get_for_download(ctx, attachment_id)
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=name,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.post(
    "/tickets/{ticket_id}/reply",
    status_code=201,
    response_model=PortalTicketDetail,
    responses=ERR,
    summary="Add a reply to a ticket (reopens it if it was waiting or resolved)",
)
def reply(ticket_id: int, body: PortalReplyIn, ctx: PortalCtx = portal_required()):
    return svc.reply(ctx, ticket_id, body.body)
