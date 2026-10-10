"""Client portal API. Signed-in endpoints see only the contact's own organization; the two
unauthenticated ones (request / redeem a sign-in link) reveal nothing about who has access."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app import audit
from app import billing_repo as brepo
from app import portal as svc
from app import repositories as repo
from app.asset_schemas import PortalAssetsOut
from app.auth import portal_sessions
from app.config import get_settings
from app.context import client_ip_var
from app.invoice_pdf import render_invoice_pdf
from app.notices import build_statement
from app.portal_deps import PortalCtx, billing_only, devices_only, portal_required, public_session
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

router = APIRouter(prefix="/portal", tags=["portal"])
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
    contact = portal_sessions.consume_link_token(db, body.token) if enabled else None
    if contact is None:
        audit.record_auth_event("portal.login_failed", detail={"reason": "bad_or_used_link"})
        raise HTTPException(status_code=401, detail="This link has expired or was already used")
    cookie = portal_sessions.create_session(
        db, contact, client_ip_var.get(), request.headers.get("user-agent")
    )
    db.flush()
    audit.record_auth_event("portal.login", detail={"contact_id": contact.id})
    s = get_settings()
    response.set_cookie(
        s.portal_cookie_name, cookie, max_age=s.portal_session_hours * 3600, **_cookie_args()
    )
    ctx = PortalCtx(db=db, user=None, scope=Scope.orgs(contact.organization_id), contact=contact)
    return svc.me(ctx)


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


@router.post(
    "/tickets/{ticket_id}/reply",
    status_code=201,
    response_model=PortalTicketDetail,
    responses=ERR,
    summary="Add a reply to a ticket (reopens it if it was waiting or resolved)",
)
def reply(ticket_id: int, body: PortalReplyIn, ctx: PortalCtx = portal_required()):
    return svc.reply(ctx, ticket_id, body.body)
