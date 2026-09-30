"""Statements, payment reminders and the review queue that gates every client email."""

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import select

from app import billing_repo as brepo
from app import notices as svc
from app import permissions as P
from app.deps import Ctx, require
from app.models import EmailMessage, ReminderStage
from app.schemas import (
    EmailStatementIn,
    ErrorOut,
    NoticeInvoiceOut,
    NoticeOut,
    NoticePatch,
    NoticeSendIn,
    Page,
    PrepareOut,
    ReasonIn,
    ReminderIn,
    ReminderStageOut,
    ReminderStagePatch,
    SendResult,
    StatementOut,
)
from app.statement_pdf import render_statement_pdf

router = APIRouter(tags=["statements-reminders"])
ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}


# ---- reminder stages ----
@router.get(
    "/billing/reminder-stages",
    response_model=list[ReminderStageOut],
    summary="The reminder schedule: stages, days past due, and message text",
)
def list_stages(ctx: Ctx = require(P.BILLING_READ)):
    return (
        ctx.db.execute(select(ReminderStage).order_by(ReminderStage.days_past_due)).scalars().all()
    )


@router.patch(
    "/billing/reminder-stages/{stage_id}",
    response_model=ReminderStageOut,
    responses=ERR,
    summary="Edit a reminder stage (days, text, enabled)",
)
def patch_stage(stage_id: int, body: ReminderStagePatch, ctx: Ctx = require(P.BILLING_WRITE)):
    return svc.update_stage(ctx, stage_id, body.model_dump(exclude_unset=True))


# ---- statements ----
def _statement_out(s) -> StatementOut:
    snap = s.snapshot
    return StatementOut(
        id=s.id,
        organization_id=s.organization_id,
        as_of=s.as_of,
        created_at=s.created_at,
        total_due_cents=snap["total_due_cents"],
        overdue_cents=snap["overdue_cents"],
        credit_cents=snap["credit_cents"],
        invoice_count=len(snap["invoices"]),
        snapshot=snap,
    )


@router.post(
    "/organizations/{org_id}/statements",
    response_model=StatementOut,
    status_code=201,
    responses=ERR,
    summary="Generate an account statement (a frozen snapshot)",
)
def create_statement(org_id: int, ctx: Ctx = require(P.BILLING_WRITE)):
    return _statement_out(svc.create_statement(ctx, org_id))


@router.get(
    "/organizations/{org_id}/statements",
    response_model=list[StatementOut],
    responses=ERR,
    summary="A client's past statements, newest first",
)
def list_statements(org_id: int, ctx: Ctx = require(P.BILLING_READ)):
    return [_statement_out(s) for s in svc.list_statements(ctx, org_id)]


@router.get(
    "/statements/{statement_id}",
    response_model=StatementOut,
    responses=ERR,
    summary="One statement",
)
def get_statement(statement_id: int, ctx: Ctx = require(P.BILLING_READ)):
    return _statement_out(svc.get_statement(ctx, statement_id))


@router.get(
    "/statements/{statement_id}/pdf",
    response_class=Response,
    responses=ERR,
    summary="Download the statement as a PDF",
)
def statement_pdf(statement_id: int, ctx: Ctx = require(P.BILLING_READ)):
    s = svc.get_statement(ctx, statement_id)
    return Response(
        render_statement_pdf(s.snapshot),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="Statement-{s.as_of}.pdf"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/statements/{statement_id}/email",
    response_model=NoticeOut,
    status_code=201,
    responses=ERR,
    summary="Prepare (or, with send=true, send) a statement email",
)
def email_statement(statement_id: int, body: EmailStatementIn, ctx: Ctx = require(P.BILLING_WRITE)):
    if body.send and not P.has_permission(ctx.user.role, P.BILLING_FINALIZE):
        raise HTTPException(403, "Not permitted")
    return _notice_out(ctx, svc.email_statement(ctx, statement_id, body.send))


# ---- notices (the review queue) ----
def _notice_out(ctx: Ctx, n) -> NoticeOut:
    rows = svc.notice_invoices(ctx, n.id)
    numbers = {}
    for r in rows:
        inv = brepo.get_invoice(ctx.db, ctx.scope, r.invoice_id)
        numbers[r.invoice_id] = (inv.number, inv.due_date) if inv else (None, None)
    total = sum(r.balance_cents for r in rows)
    if n.kind == "statement" and n.statement_id:
        total = svc.get_statement(ctx, n.statement_id).snapshot["total_due_cents"]
    email = ctx.db.get(EmailMessage, n.email_message_id) if n.email_message_id else None
    return NoticeOut(
        id=n.id,
        kind=n.kind,
        organization_id=n.organization_id,
        organization_name=n.organization.name,
        status=n.status,
        manual=n.manual,
        stage_name=n.stage.name if n.stage else None,
        subject=n.subject,
        body_text=n.body_text,
        to_emails=list(n.to_emails or []),
        blocked_reason=n.blocked_reason,
        statement_id=n.statement_id,
        stale=svc.is_stale(ctx, n),
        total_due_cents=total,
        created_at=n.created_at,
        decided_at=n.decided_at,
        dismiss_reason=n.dismiss_reason,
        email_status=email.send_status if email else None,
        invoices=[
            NoticeInvoiceOut(
                invoice_id=r.invoice_id,
                number=numbers[r.invoice_id][0],
                due_date=numbers[r.invoice_id][1],
                balance_cents=r.balance_cents,
                days_past_due=r.days_past_due,
                new_stage=r.stage_id is not None,
            )
            for r in rows
        ],
    )


@router.get(
    "/billing-notices",
    response_model=Page[NoticeOut],
    summary="The review queue: pending, sent and dismissed reminders and statements",
)
def list_notices(
    status: str | None = Query(None, pattern="^(pending|sent|dismissed|expired)$"),
    kind: str | None = Query(None, pattern="^(reminder|statement)$"),
    organization_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: Ctx = require(P.BILLING_READ),
):
    items, total = svc.list_notices(
        ctx, status=status, kind=kind, org_id=organization_id, limit=limit, offset=offset
    )
    return Page(items=[_notice_out(ctx, n) for n in items], total=total, limit=limit, offset=offset)


@router.get(
    "/billing-notices/{notice_id}", response_model=NoticeOut, responses=ERR, summary="One notice"
)
def get_notice(notice_id: int, ctx: Ctx = require(P.BILLING_READ)):
    return _notice_out(ctx, svc.get_notice(ctx, notice_id))


@router.patch(
    "/billing-notices/{notice_id}",
    response_model=NoticeOut,
    responses=ERR,
    summary="Edit a pending notice's subject or message",
)
def patch_notice(notice_id: int, body: NoticePatch, ctx: Ctx = require(P.BILLING_WRITE)):
    return _notice_out(ctx, svc.update_notice(ctx, notice_id, body.subject, body.body_text))


@router.post(
    "/billing-notices/{notice_id}/refresh",
    response_model=NoticeOut,
    responses=ERR,
    summary="Re-read balances and recipients and rebuild the message (drops your edits)",
)
def refresh_notice(notice_id: int, ctx: Ctx = require(P.BILLING_WRITE)):
    return _notice_out(ctx, svc.refresh_notice(ctx, notice_id))


@router.post(
    "/billing-notices/{notice_id}/send",
    response_model=NoticeOut,
    responses=ERR,
    summary="APPROVE: queue this email to the client (with PDF attachments)",
)
def send_notice(notice_id: int, ctx: Ctx = require(P.BILLING_FINALIZE)):
    return _notice_out(ctx, svc.send_notice(ctx, notice_id))


@router.post(
    "/billing-notices/send",
    response_model=list[SendResult],
    summary="Approve several notices; each succeeds or fails on its own",
)
def send_many(body: NoticeSendIn, ctx: Ctx = require(P.BILLING_FINALIZE)):
    results = []
    for notice_id in body.ids:
        try:
            with ctx.db.begin_nested():
                svc.send_notice(ctx, notice_id)
            results.append(SendResult(id=notice_id, ok=True))
        except Exception as exc:  # NotFound / Conflict: report, keep going
            results.append(SendResult(id=notice_id, ok=False, error=str(exc)))
    return results


@router.post(
    "/billing-notices/{notice_id}/dismiss",
    response_model=NoticeOut,
    responses=ERR,
    summary="Decide NOT to send this (reason required); it will not be prepared again",
)
def dismiss_notice(notice_id: int, body: ReasonIn, ctx: Ctx = require(P.BILLING_FINALIZE)):
    return _notice_out(ctx, svc.dismiss_notice(ctx, notice_id, body.reason))


@router.post(
    "/billing-notices/prepare-reminders",
    response_model=PrepareOut,
    summary="Prepare reminders now for everything that is due one (nothing is sent)",
)
def prepare_reminders(ctx: Ctx = require(P.BILLING_WRITE)):
    created = svc.prepare_reminders(ctx)
    return PrepareOut(created=len(created), notice_ids=[n.id for n in created])


@router.post(
    "/billing-notices/prepare-statements",
    response_model=PrepareOut,
    summary="Prepare this month's statements for every client with a balance (nothing is sent)",
)
def prepare_statements(ctx: Ctx = require(P.BILLING_WRITE)):
    created = svc.prepare_statement_batch(ctx)
    return PrepareOut(created=len(created), notice_ids=[n.id for n in created])


@router.post(
    "/organizations/{org_id}/reminders",
    response_model=NoticeOut,
    status_code=201,
    responses=ERR,
    summary="Prepare a reminder for one client right now (for your review)",
)
def manual_reminder(org_id: int, body: ReminderIn, ctx: Ctx = require(P.BILLING_WRITE)):
    return _notice_out(ctx, svc.create_manual_reminder(ctx, org_id, body.invoice_ids))
