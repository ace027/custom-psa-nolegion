import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app import permissions as P
from app import repositories as repo
from app import ticket_services as svc
from app.config import get_settings
from app.deps import Ctx, require
from app.models import EmailMessage
from app.schemas import (
    AttachmentOut,
    BulkTicketsIn,
    BulkTicketsOut,
    DashboardOut,
    ErrorOut,
    NoteIn,
    NoteOut,
    Page,
    TicketIn,
    TicketOut,
    TicketPatch,
    TimeIn,
    TimeOut,
    TimePatch,
)
from app.sla import Calendar
from app.ticket_views import ticket_out

router = APIRouter(tags=["tickets"])
ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}


def _view(ctx: Ctx):
    s = repo.get_settings_row(ctx.db)
    cal, now = Calendar.from_settings(s, repo.holiday_exceptions(ctx.db)), svc.now()
    return lambda t: ticket_out(t, cal, s.sla_at_risk_percent, now)


def _ticket_or_404(ctx: Ctx, ticket_id: int):
    t = repo.get_ticket(ctx.db, ctx.scope, ticket_id)
    if t is None:
        raise HTTPException(404, "Ticket not found")
    return t


@router.get("/tickets", response_model=Page[TicketOut], summary="List and filter tickets")
def list_tickets(
    status: str | None = Query(None, description="Comma-separated statuses"),
    status_id: int | None = Query(None, description="A specific named status"),
    type_id: int | None = Query(None, description="A ticket type"),
    open_only: bool = False,
    queue_id: int | None = None,
    assignee_id: int | None = None,
    unassigned: bool = False,
    organization_id: int | None = None,
    priority_id: int | None = None,
    needs_triage: bool = False,
    q: str | None = Query(None, description="Subject text or ticket number"),
    sort: str = Query("updated", pattern="^(updated|created|number|priority|due)$"),
    descending: bool = True,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: Ctx = require(P.TICKET_READ),
):
    statuses = [s for s in (status or "").split(",") if s] or None
    items, total = repo.list_tickets(
        ctx.db,
        ctx.scope,
        statuses=statuses,
        status_id=status_id,
        type_id=type_id,
        open_only=open_only,
        queue_id=queue_id,
        assignee_id=assignee_id,
        unassigned=unassigned,
        organization_id=organization_id,
        priority_id=priority_id,
        needs_triage=needs_triage,
        q=q,
        limit=limit,
        offset=offset,
        sort=sort,
        descending=descending,
    )
    view = _view(ctx)
    return Page(items=[view(t) for t in items], total=total, limit=limit, offset=offset)


@router.post(
    "/tickets", response_model=TicketOut, status_code=201, responses=ERR, summary="Create a ticket"
)
def create_ticket(body: TicketIn, ctx: Ctx = require(P.TICKET_WRITE)):
    ticket = svc.create_ticket(ctx, body.model_dump())
    return _view(ctx)(ticket)


@router.post(
    "/tickets/bulk",
    response_model=BulkTicketsOut,
    responses=ERR,
    summary="Change status, assignee, queue or priority on up to 100 tickets at once",
)
def bulk_tickets(body: BulkTicketsIn, ctx: Ctx = require(P.TICKET_WRITE)):
    updated, failed = svc.bulk_update(
        ctx, body.ticket_ids, body.changes.model_dump(exclude_unset=True)
    )
    return BulkTicketsOut(updated=updated, failed=failed)


@router.get("/tickets/{ticket_id}", response_model=TicketOut, responses=ERR, summary="Get a ticket")
def get_ticket(ticket_id: int, ctx: Ctx = require(P.TICKET_READ)):
    return _view(ctx)(_ticket_or_404(ctx, ticket_id))


@router.patch(
    "/tickets/{ticket_id}",
    response_model=TicketOut,
    responses=ERR,
    summary="Update a ticket: status, assignee, priority, triage, etc.",
)
def update_ticket(ticket_id: int, body: TicketPatch, ctx: Ctx = require(P.TICKET_WRITE)):
    ticket = svc.update_ticket(ctx, ticket_id, body.model_dump(exclude_unset=True))
    return _view(ctx)(ticket)


# ---- notes ----
def _note_out(ctx: Ctx, notes) -> list[NoteOut]:
    emails = repo.email_status_map(
        ctx.db, [n.email_message_id for n in notes if n.email_message_id]
    )
    out = []
    for n in notes:
        email: EmailMessage | None = emails.get(n.email_message_id)
        status = None
        if email:
            status = email.send_status if email.direction == "out" else "received"
        out.append(
            NoteOut(
                id=n.id,
                ticket_id=n.ticket_id,
                author_user_id=n.author_user_id,
                author_name=n.author.display_name if n.author else None,
                author_email=n.author_email,
                visibility=n.visibility,
                source=n.source,
                body=n.body,
                created_at=n.created_at,
                email_status=status,
            )
        )
    return out


@router.get(
    "/tickets/{ticket_id}/notes",
    response_model=list[NoteOut],
    responses=ERR,
    summary="List a ticket's notes (internal and customer-visible)",
)
def list_notes(ticket_id: int, ctx: Ctx = require(P.TICKET_READ)):
    _ticket_or_404(ctx, ticket_id)
    return _note_out(ctx, repo.list_notes(ctx.db, ctx.scope, ticket_id))


@router.post(
    "/tickets/{ticket_id}/notes",
    response_model=NoteOut,
    status_code=201,
    responses=ERR,
    summary="Add a note; customer-visible notes can be emailed",
)
def add_note(ticket_id: int, body: NoteIn, ctx: Ctx = require(P.TICKET_WRITE)):
    note = svc.add_note(ctx, ticket_id, body.body, body.visibility, body.send_email)
    return _note_out(ctx, [note])[0]


# ---- time ----
@router.get(
    "/tickets/{ticket_id}/time",
    response_model=list[TimeOut],
    responses=ERR,
    summary="List a ticket's time entries",
)
def list_time(ticket_id: int, include_voided: bool = False, ctx: Ctx = require(P.TICKET_READ)):
    _ticket_or_404(ctx, ticket_id)
    return repo.list_time_entries(ctx.db, ctx.scope, ticket_id, include_voided)


@router.post(
    "/tickets/{ticket_id}/time",
    response_model=TimeOut,
    status_code=201,
    responses={**ERR, 403: {"model": ErrorOut}},
    summary="Log time on a ticket",
)
def add_time(ticket_id: int, body: TimeIn, ctx: Ctx = require(P.TIME_WRITE)):
    return svc.add_time(ctx, ticket_id, body.model_dump())


@router.patch(
    "/time-entries/{entry_id}",
    response_model=TimeOut,
    responses={**ERR, 403: {"model": ErrorOut}},
    summary="Edit a time entry",
)
def update_time(entry_id: int, body: TimePatch, ctx: Ctx = require(P.TIME_WRITE)):
    return svc.update_time(ctx, entry_id, body.model_dump(exclude_unset=True))


@router.post(
    "/time-entries/{entry_id}/void",
    response_model=TimeOut,
    responses={**ERR, 403: {"model": ErrorOut}},
    summary="Void a time entry (kept for the audit trail, excluded from billing)",
)
def void_time(entry_id: int, ctx: Ctx = require(P.TIME_WRITE)):
    return svc.void_time(ctx, entry_id)


# ---- attachments ----
@router.get(
    "/tickets/{ticket_id}/attachments",
    response_model=list[AttachmentOut],
    responses=ERR,
    summary="List attachments received on a ticket",
)
def list_attachments(ticket_id: int, ctx: Ctx = require(P.TICKET_READ)):
    _ticket_or_404(ctx, ticket_id)
    return repo.list_attachments(ctx.db, ctx.scope, ticket_id)


@router.get(
    "/attachments/{attachment_id}/download",
    response_class=FileResponse,
    responses=ERR,
    summary="Download an attachment (always as a download, never inline)",
)
def download_attachment(attachment_id: int, ctx: Ctx = require(P.TICKET_READ)):
    att = repo.get_attachment(ctx.db, ctx.scope, attachment_id)
    if att is None:
        raise HTTPException(404, "Attachment not found")
    base = Path(get_settings().attachments_dir).resolve()
    path = (base / att.storage_key).resolve()
    if base not in path.parents or not path.is_file():  # path-traversal guard
        raise HTTPException(404, "Attachment file is missing")
    safe_name = re.sub(r"[^\w.\- ]", "_", att.filename).lstrip(".") or "attachment"
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=safe_name,
        headers={"X-Content-Type-Options": "nosniff"},
    )


# ---- dashboard ----
@router.get(
    "/dashboard",
    response_model=DashboardOut,
    summary="My tickets, unassigned tickets, and tickets at risk of breaching SLA",
)
def dashboard(ctx: Ctx = require(P.TICKET_READ)):
    view = _view(ctx)
    rows = [view(t) for t in repo.open_tickets(ctx.db, ctx.scope)]
    mine = [t for t in rows if t.assignee_id == ctx.user.id]
    unassigned = [t for t in rows if t.assignee_id is None]
    risk = [t for t in rows if t.sla_state in ("breached", "at_risk")]
    risk.sort(key=lambda t: (t.sla_state != "breached", t.priority_rank, t.created_at))
    unassigned.sort(key=lambda t: (t.priority_rank, t.created_at))
    mine.sort(key=lambda t: (t.priority_rank, t.created_at))
    return DashboardOut(
        my_open=mine[:50],
        unassigned=unassigned[:50],
        sla_at_risk=risk[:50],
        counts={
            "open": len(rows),
            "mine": len(mine),
            "unassigned": len(unassigned),
            "sla_at_risk": len(risk),
            "needs_triage": sum(1 for t in rows if t.needs_triage),
        },
    )
