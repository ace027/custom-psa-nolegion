"""Ticket business rules: creation, status/SLA transitions, triage, notes, time.

Works for people (Ctx.user set) and for the mail worker (Ctx.user None = system actor).
"""

from datetime import UTC, date, datetime

from sqlalchemy import update

from app import audit
from app import repositories as repo
from app.deps import Ctx
from app.errors import Conflict, Forbidden, NotFound
from app.models import (
    CLOCK_STOPPED,
    Attachment,
    Category,
    EmailMessage,
    Priority,
    Queue,
    Ticket,
    TicketNote,
    TimeEntry,
    WorkType,
)
from app.sla import Calendar, business_minutes_between, compute_due_dates

ASSIGNABLE_ROLES = ("admin", "tech")


def calendar(ctx: Ctx) -> Calendar:
    return Calendar.from_settings(repo.get_settings_row(ctx.db))


def now() -> datetime:
    return datetime.now(UTC)


def billable_minutes(actual: int, billable: bool, increment: int) -> int:
    """Round UP to the configured increment (default 15). Non-billable entries bill 0."""
    if not billable:
        return 0
    return -(-actual // increment) * increment


# ---- reference validation -----------------------------------------------------------------
def _active(ctx: Ctx, model, obj_id: int | None, label: str):
    if obj_id is None:
        return None
    obj = repo.get_lookup(ctx.db, model, obj_id)
    if obj is None or obj.archived_at is not None:
        raise Conflict(f"Unknown or archived {label}")
    return obj


def _check_assignee(ctx: Ctx, user_id: int | None) -> None:
    if user_id is None:
        return
    user = repo.get_user(ctx.db, user_id)
    if user is None or not user.is_active or user.role not in ASSIGNABLE_ROLES:
        raise Conflict("Assignee must be an active admin or tech")


def _check_org_refs(ctx: Ctx, org_id: int | None, contact_id: int | None, site_id: int | None):
    if contact_id is not None:
        contact = repo.get_contact(ctx.db, ctx.scope, contact_id)
        if contact is None or contact.organization_id != org_id or contact.archived_at:
            raise Conflict("Contact does not belong to this organization")
    if site_id is not None:
        site = repo.get_site(ctx.db, ctx.scope, site_id)
        if site is None or site.organization_id != org_id or site.archived_at:
            raise Conflict("Site does not belong to this organization")


# ---- SLA -----------------------------------------------------------------------------------
def recompute_sla(ctx: Ctx, ticket: Ticket) -> None:
    ticket.sla_first_response_due, ticket.sla_resolution_due = compute_due_dates(
        ticket, calendar(ctx)
    )


def _apply_status(ctx: Ctx, ticket: Ticket, new: str) -> None:
    old = ticket.status
    if new == old:
        return
    t = now()
    was_stopped, will_stop = old in CLOCK_STOPPED, new in CLOCK_STOPPED
    if not was_stopped and will_stop:
        ticket.sla_paused_at = t
    elif was_stopped and not will_stop and ticket.sla_paused_at:
        ticket.sla_paused_minutes += business_minutes_between(
            ticket.sla_paused_at, t, calendar(ctx)
        )
        ticket.sla_paused_at = None
        recompute_sla(ctx, ticket)
    ticket.resolved_at = (
        t if new == "resolved" else (ticket.resolved_at if new == "closed" else None)
    )
    ticket.closed_at = t if new == "closed" else None
    ticket.status = new


def _mark_first_response(ticket: Ticket) -> None:
    if ticket.first_responded_at is None:
        ticket.first_responded_at = now()


# ---- tickets -------------------------------------------------------------------------------
def create_ticket(
    ctx: Ctx, data: dict, *, source: str = "ui", requester_email: str | None = None
) -> Ticket:
    org_id = data.get("organization_id")
    if org_id is not None and repo.get_organization(ctx.db, ctx.scope, org_id) is None:
        raise NotFound("Organization not found")
    _check_org_refs(ctx, org_id, data.get("contact_id"), data.get("site_id"))
    _check_assignee(ctx, data.get("assignee_id"))
    queue = _active(ctx, Queue, data.get("queue_id"), "queue") or repo.get_default(ctx.db, Queue)
    priority = _active(ctx, Priority, data.get("priority_id"), "priority") or repo.get_default(
        ctx.db, Priority
    )
    if queue is None or priority is None:
        raise Conflict("No default queue/priority configured")
    _active(ctx, Category, data.get("category_id"), "category")

    fields = {
        k: v
        for k, v in data.items()
        if k
        in (
            "organization_id",
            "contact_id",
            "site_id",
            "category_id",
            "assignee_id",
            "subject",
            "description",
        )
    }
    ticket = Ticket(
        **fields,
        queue_id=queue.id,
        priority_id=priority.id,
        source=source,
        requester_email=requester_email,
        created_by_user_id=ctx.user.id if ctx.user else None,
    )
    ctx.db.add(ticket)
    ctx.db.flush()
    ctx.db.refresh(ticket)  # server defaults: number, created_at
    recompute_sla(ctx, ticket)
    ctx.db.flush()
    audit.record(
        ctx.db,
        ctx.user,
        "ticket.create",
        ticket,
        after=audit.snapshot(ticket),
        organization_id=ticket.organization_id,
        detail={"source": source},
    )
    if ticket.assignee_id:
        from app import notifications

        notifications.notify(
            ctx, ticket.assignee_id, ticket, "assigned", now().isoformat(), actor=ctx.user
        )
    return ticket


def _propagate_org(ctx: Ctx, ticket: Ticket, org_id: int) -> None:
    for model in (TicketNote, Attachment, EmailMessage):
        ctx.db.execute(
            update(model).where(model.ticket_id == ticket.id).values(organization_id=org_id)
        )


def update_ticket(ctx: Ctx, ticket_id: int, data: dict) -> Ticket:
    ticket = repo.get_ticket(ctx.db, ctx.scope, ticket_id)
    if ticket is None:
        raise NotFound("Ticket not found")
    before = audit.snapshot(ticket)
    detail: dict = {}

    if "organization_id" in data and data["organization_id"] != ticket.organization_id:
        if ticket.organization_id is not None:
            raise Conflict("A ticket's organization can only be set while it is unmatched")
        if (
            data["organization_id"] is None
            or repo.get_organization(ctx.db, ctx.scope, data["organization_id"]) is None
        ):
            raise NotFound("Organization not found")
        ticket.organization_id = data["organization_id"]
        _propagate_org(ctx, ticket, ticket.organization_id)
        detail["triage"] = True
    org_id = ticket.organization_id

    if "contact_id" in data or "site_id" in data:
        _check_org_refs(ctx, org_id, data.get("contact_id"), data.get("site_id"))
    if data.get("assignee_id") is not None:
        _check_assignee(ctx, data["assignee_id"])
    if data.get("queue_id") is not None:
        _active(ctx, Queue, data["queue_id"], "queue")
    if data.get("category_id") is not None:
        _active(ctx, Category, data["category_id"], "category")
    for required in ("queue_id", "priority_id", "subject"):
        if required in data and data[required] is None:
            raise Conflict(f"{required} cannot be cleared")
    if data.get("priority_id") is not None:
        _active(ctx, Priority, data["priority_id"], "priority")

    for key in (
        "subject",
        "description",
        "contact_id",
        "site_id",
        "queue_id",
        "category_id",
        "assignee_id",
        "priority_id",
    ):
        if key in data:
            setattr(ticket, key, data[key])
    ctx.db.flush()
    ctx.db.refresh(ticket)  # so ticket.priority reflects a changed priority_id
    if "priority_id" in data and data["priority_id"] != before["priority_id"]:
        recompute_sla(ctx, ticket)
    if "status" in data and data["status"] is not None:
        _apply_status(ctx, ticket, data["status"])
    if ticket.status == "new" and ticket.assignee_id and "assignee_id" in data:
        _apply_status(ctx, ticket, "open")  # picking up a new ticket opens it
    ctx.db.flush()
    ctx.db.refresh(ticket)
    audit.record(
        ctx.db,
        ctx.user,
        "ticket.triage" if detail else "ticket.update",
        ticket,
        before=before,
        after=audit.snapshot(ticket),
        organization_id=ticket.organization_id,
        detail=detail or None,
    )
    if ticket.assignee_id and ticket.assignee_id != before["assignee_id"]:
        from app import notifications

        notifications.notify(
            ctx, ticket.assignee_id, ticket, "assigned", now().isoformat(), actor=ctx.user
        )
    return ticket


# ---- notes ---------------------------------------------------------------------------------
def recipient_for(ticket: Ticket) -> str | None:
    if ticket.contact is not None and ticket.contact.email:
        return ticket.contact.email
    return ticket.requester_email


def add_note(
    ctx: Ctx, ticket_id: int, body: str, visibility: str, send_email: bool = False
) -> TicketNote:
    """A note written by staff in the UI."""
    ticket = repo.get_ticket(ctx.db, ctx.scope, ticket_id)
    if ticket is None:
        raise NotFound("Ticket not found")
    if send_email and visibility != "customer":
        raise Conflict("Only customer-visible notes can be emailed")
    email = None
    if send_email:
        to = recipient_for(ticket)
        if not to:
            raise Conflict("This ticket has no contact email to send to")
        email = EmailMessage(
            direction="out",
            ticket_id=ticket.id,
            organization_id=ticket.organization_id,
            to_emails=[to],
            subject=f"[#{ticket.number}] {ticket.subject}"[:998],
            body_text=body,
            send_status="pending",
        )
        ctx.db.add(email)
        ctx.db.flush()
    note = TicketNote(
        ticket_id=ticket.id,
        organization_id=ticket.organization_id,
        author_user_id=ctx.user.id if ctx.user else None,
        visibility=visibility,
        source="ui",
        body=body,
        email_message_id=email.id if email else None,
    )
    ctx.db.add(note)
    if visibility == "customer":
        _mark_first_response(ticket)
    ticket.updated_at = now()
    ctx.db.flush()
    audit.record(
        ctx.db,
        ctx.user,
        "ticket.note_add",
        note,
        after={"ticket_id": ticket.id, "visibility": visibility, "emailed": send_email},
        organization_id=ticket.organization_id,
    )
    return note


# ---- time ----------------------------------------------------------------------------------
def _entry_date(ctx: Ctx, given: date | None) -> date:
    if given:
        return given
    return now().astimezone(calendar(ctx).tz).date()


def add_time(ctx: Ctx, ticket_id: int, data: dict) -> TimeEntry:
    ticket = repo.get_ticket(ctx.db, ctx.scope, ticket_id)
    if ticket is None:
        raise NotFound("Ticket not found")
    if ticket.organization_id is None:
        raise Conflict("Match the ticket to an organization before logging time")
    _active(ctx, WorkType, data["work_type_id"], "work type")
    user_id = data.get("user_id") or ctx.user.id
    if user_id != ctx.user.id:
        if ctx.user.role != "admin":
            raise Forbidden("Only admins can log time for someone else")
        target = repo.get_user(ctx.db, user_id)
        if target is None or not target.is_active:
            raise Conflict("Unknown or inactive user")
    inc = repo.get_settings_row(ctx.db).billing_increment_minutes
    entry = TimeEntry(
        ticket_id=ticket.id,
        organization_id=ticket.organization_id,
        user_id=user_id,
        work_type_id=data["work_type_id"],
        work_date=_entry_date(ctx, data.get("work_date")),
        minutes_actual=data["minutes"],
        billable=data["billable"],
        note=data.get("note"),
        minutes_billable=billable_minutes(data["minutes"], data["billable"], inc),
    )
    ctx.db.add(entry)
    ticket.updated_at = now()
    ctx.db.flush()
    audit.record(
        ctx.db,
        ctx.user,
        "time_entry.create",
        entry,
        after=audit.snapshot(entry),
        organization_id=entry.organization_id,
    )
    return entry


def _own_or_admin(ctx: Ctx, entry: TimeEntry) -> None:
    if entry.user_id != ctx.user.id and ctx.user.role != "admin":
        raise Forbidden("You can only change your own time entries")


def update_time(ctx: Ctx, entry_id: int, data: dict) -> TimeEntry:
    entry = repo.get_time_entry(ctx.db, ctx.scope, entry_id)
    if entry is None:
        raise NotFound("Time entry not found")
    _own_or_admin(ctx, entry)
    if entry.voided_at:
        raise Conflict("Voided time entries cannot be edited")
    if entry.invoice_line_id is not None:
        raise Conflict("This time is on an invoice and is locked")
    before = audit.snapshot(entry)
    if data.get("work_type_id"):
        _active(ctx, WorkType, data["work_type_id"], "work type")
        entry.work_type_id = data["work_type_id"]
    for key, attr in (
        ("minutes", "minutes_actual"),
        ("work_date", "work_date"),
        ("billable", "billable"),
        ("note", "note"),
    ):
        if key in data and data[key] is not None:
            setattr(entry, attr, data[key])
    if "note" in data and data["note"] is None:
        entry.note = None
    inc = repo.get_settings_row(ctx.db).billing_increment_minutes
    entry.minutes_billable = billable_minutes(entry.minutes_actual, entry.billable, inc)
    ctx.db.flush()
    ctx.db.refresh(entry)
    audit.record(
        ctx.db,
        ctx.user,
        "time_entry.update",
        entry,
        before=before,
        after=audit.snapshot(entry),
        organization_id=entry.organization_id,
    )
    return entry


def void_time(ctx: Ctx, entry_id: int) -> TimeEntry:
    entry = repo.get_time_entry(ctx.db, ctx.scope, entry_id)
    if entry is None:
        raise NotFound("Time entry not found")
    _own_or_admin(ctx, entry)
    if entry.voided_at:
        raise Conflict("Already voided")
    if entry.invoice_line_id is not None:
        raise Conflict("This time is on an invoice and is locked")
    before = audit.snapshot(entry)
    entry.voided_at = now()
    ctx.db.flush()
    ctx.db.refresh(entry)
    audit.record(
        ctx.db,
        ctx.user,
        "time_entry.void",
        entry,
        before=before,
        after=audit.snapshot(entry),
        organization_id=entry.organization_id,
    )
    return entry


# ---- inbound-email helpers (used by the mail worker) ---------------------------------------
def reopen_on_customer_activity(ctx: Ctx, ticket: Ticket) -> None:
    """A customer wrote on the ticket: resume the SLA clock / reopen, and mark it touched."""
    if ticket.status in ("waiting_on_customer", "resolved", "closed"):
        _apply_status(ctx, ticket, "open")
    ticket.updated_at = now()


def customer_reply(
    ctx: Ctx, ticket: Ticket, body: str, author_email: str, email: EmailMessage
) -> TicketNote:
    """A customer's emailed reply on an existing ticket: note + reopen/resume if needed."""
    note = TicketNote(
        ticket_id=ticket.id,
        organization_id=ticket.organization_id,
        author_email=author_email,
        visibility="customer",
        source="email",
        body=body,
        email_message_id=email.id,
    )
    ctx.db.add(note)
    before_status = ticket.status
    reopen_on_customer_activity(ctx, ticket)
    ctx.db.flush()
    audit.record(
        ctx.db,
        ctx.user,
        "ticket.email_reply",
        note,
        after={"ticket_id": ticket.id, "from": author_email},
        organization_id=ticket.organization_id,
        detail={"status_before": before_status, "status_after": ticket.status},
    )
    if ticket.assignee_id:
        from app import notifications

        notifications.notify(
            ctx, ticket.assignee_id, ticket, "customer_reply", str(email.id), actor=None
        )
    return note
