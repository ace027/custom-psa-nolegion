"""What a signed-in client contact may see and do. Every query is scoped to the contact's own
organization (Scope + row-level security), and only customer-visible information is returned:
never internal notes, assignees, SLA clocks, time entries, costs or other clients' data."""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit, custom_fields
from app import billing_repo as brepo
from app import payment_repo as prepo
from app import repositories as repo
from app import ticket_services as tsvc
from app.auth import portal_sessions
from app.billing import today
from app.config import get_settings
from app.errors import Conflict, NotFound
from app.models import EmailMessage, Invoice, Ticket, TicketNote, User
from app.payments import payment_state
from app.portal_deps import PortalCtx

MAX_TICKETS_PER_DAY = 20
MAX_REPLIES_PER_DAY = 50


# ---- signing in ------------------------------------------------------------------------
def request_link(db: Session, email: str, ip: str | None) -> dict:
    """Queue a sign-in email if this address belongs to a portal-enabled contact. The caller answers
    identically either way, so the form cannot be used to discover who has access."""
    outcome = {"contact_id": None, "sent": False, "reason": None}
    if not repo.get_settings_row(db).portal_enabled:
        return {**outcome, "reason": "portal_off"}
    contact = portal_sessions.find_contact_by_email(db, email)
    if contact is None:
        return {**outcome, "reason": "unknown_email"}
    outcome["contact_id"] = contact.id
    if not portal_sessions.may_issue_link(db, contact, ip):
        return {**outcome, "reason": "rate_limited"}
    if repo.get_mailbox_status(db).mailbox is None:
        return {**outcome, "reason": "mail_not_configured"}
    token = portal_sessions.issue_link_token(db, contact, ip)
    company = repo.get_settings_row(db).company_name or "your IT provider"
    minutes = get_settings().portal_link_minutes
    url = f"{get_settings().public_url.rstrip('/')}/portal/verify#token={token}"
    db.add(
        EmailMessage(
            direction="out",
            organization_id=contact.organization_id,
            to_emails=[contact.email],
            subject=f"Your sign-in link for {company}",
            body_text=(
                f"Hello {contact.name},\n\nUse this link to sign in to the {company} client portal:"
                f"\n\n{url}\n\nIt works once and expires in {minutes} minutes. If you did not ask "
                "for it, you can ignore this message; nobody can sign in without it."
            ),
            send_status="pending",
        )
    )
    db.flush()
    return {**outcome, "sent": True}


# ---- devices and warranty (designated contacts, published clients only) ----
def devices_visible(ctx: PortalCtx, org) -> bool:
    return bool(org.assets_published and ctx.contact.portal_assets)


def list_devices(ctx: PortalCtx) -> dict:
    from app import assets as asvc

    rows = asvc.list_assets(ctx, ctx.contact.organization_id)
    counts = {s: 0 for s in asvc.STATUSES}
    for r in rows:
        counts[r["warranty_status"]] += 1
    keep = ("name", "kind", "manufacturer", "model", "warranty_end", "warranty_status")
    return dict(
        as_of=asvc.today(ctx),
        total=len(rows),
        counts=counts,
        devices=[{k: r[k] for k in keep} for r in rows],
    )


# ---- who am I --------------------------------------------------------------------------
def me(ctx: PortalCtx) -> dict:
    org = repo.get_organization(ctx.db, ctx.scope, ctx.contact.organization_id)
    return dict(
        contact_name=ctx.contact.name,
        email=ctx.contact.email,
        organization_name=org.name,
        company_name=repo.get_settings_row(ctx.db).company_name,
        can_see_billing=ctx.contact.is_billing_contact,
        can_see_all_tickets=ctx.contact.portal_org_tickets,
        can_see_devices=devices_visible(ctx, org),
    )


# ---- invoices and statement (billing contacts) -----------------------------------------
def _invoice_out(inv: Invoice, applied: int, written_off: int, on) -> dict:
    st = payment_state(inv, applied, written_off, on)
    return dict(
        id=inv.id,
        number=inv.number,
        invoice_date=inv.invoice_date,
        due_date=inv.due_date,
        total_cents=inv.total_cents,
        paid_cents=st["paid_cents"],
        balance_cents=st["balance_cents"],
        status=st["payment_status"],
        is_overdue=st["is_overdue"],
        days_past_due=st["days_past_due"],
    )


def list_invoices(ctx: PortalCtx) -> list[dict]:
    invoices = list(
        ctx.db.execute(
            ctx.scope.apply(
                select(Invoice).where(Invoice.status == "final"), Invoice.organization_id
            ).order_by(Invoice.invoice_date.desc(), Invoice.id.desc())
        )
        .unique()
        .scalars()
    )
    amounts = prepo.amounts_for(ctx.db, [i.id for i in invoices])
    on = today(ctx)
    return [_invoice_out(i, *amounts[i.id], on) for i in invoices]


def get_final_invoice(ctx: PortalCtx, invoice_id: int) -> Invoice:
    inv = brepo.get_invoice(ctx.db, ctx.scope, invoice_id)
    if inv is None or inv.status != "final":  # drafts and voided invoices are internal
        raise NotFound("Invoice not found")
    return inv


def invoice_detail(ctx: PortalCtx, invoice_id: int) -> dict:
    inv = get_final_invoice(ctx, invoice_id)
    applied, written_off = prepo.amounts_for(ctx.db, [inv.id])[inv.id]
    lines = [ln for ln in brepo.invoice_lines(ctx.db, ctx.scope, inv.id) if not ln.voided]
    return {
        **_invoice_out(inv, applied, written_off, today(ctx)),
        "subtotal_cents": inv.subtotal_cents,
        "tax_cents": inv.tax_cents,
        "lines": [
            dict(
                description=ln.description,
                quantity=str(ln.quantity),
                unit_price_cents=ln.unit_price_cents,
                amount_cents=ln.amount_cents,
                tax_cents=ln.tax_cents,
            )
            for ln in lines
        ],
    }


# ---- tickets ---------------------------------------------------------------------------
def _visible(ctx: PortalCtx):
    cond = Ticket.organization_id == ctx.contact.organization_id
    if not ctx.contact.portal_org_tickets:
        cond = cond & (Ticket.contact_id == ctx.contact.id)
    return cond


def _ticket_out(ctx: PortalCtx, t: Ticket) -> dict:
    return dict(
        id=t.id,
        number=t.number,
        subject=t.subject,
        status=t.status,
        status_name=t.status_ref.name,
        created_at=t.created_at,
        updated_at=t.updated_at,
        mine=t.contact_id == ctx.contact.id,
    )


def list_tickets(ctx: PortalCtx) -> list[dict]:
    rows = (
        ctx.db.execute(
            select(Ticket)
            .where(_visible(ctx))
            .order_by(Ticket.updated_at.desc(), Ticket.id.desc())
            .limit(200)
        )
        .unique()
        .scalars()
    )
    return [_ticket_out(ctx, t) for t in rows]


def _get_ticket(ctx: PortalCtx, ticket_id: int) -> Ticket:
    t = (
        ctx.db.execute(select(Ticket).where(Ticket.id == ticket_id, _visible(ctx)))
        .unique()
        .scalar_one_or_none()
    )
    if t is None:  # someone else's ticket looks exactly like a missing one
        raise NotFound("Ticket not found")
    return t


def ticket_detail(ctx: PortalCtx, ticket_id: int) -> dict:
    t = _get_ticket(ctx, ticket_id)
    notes = ctx.db.execute(
        ctx.scope.apply(
            select(TicketNote).where(
                TicketNote.ticket_id == t.id, TicketNote.visibility == "customer"
            ),
            TicketNote.organization_id,
        ).order_by(TicketNote.id)
    ).scalars()
    staff = {}
    out = []
    for n in notes:
        if n.author_user_id is not None:
            if n.author_user_id not in staff:
                u = ctx.db.get(User, n.author_user_id)
                staff[n.author_user_id] = u.display_name if u else "Support"
            author, support, mine = staff[n.author_user_id], True, False
        else:
            mine = (n.author_email or "").lower() == (ctx.contact.email or "").lower()
            author, support = ("You" if mine else "A colleague"), False
        out.append(
            dict(
                id=n.id,
                author=author,
                from_you=mine,
                from_support=support,
                body=n.body,
                created_at=n.created_at,
            )
        )
    visible = [
        dict(name=d["name"], value=d["value"])
        for d in custom_fields.definitions_with_values(ctx, t.type_id, t.custom_values)
        if d["client_visible"] and d["value"] is not None
    ]
    return {
        **_ticket_out(ctx, t),
        "description": t.description,
        "notes": out,
        "custom_fields": visible,
    }


def _count_today(ctx: PortalCtx, model, *conds) -> int:
    since = tsvc.now() - timedelta(days=1)
    return ctx.db.execute(
        select(func.count()).select_from(model).where(model.created_at > since, *conds)
    ).scalar_one()


def create_ticket(ctx: PortalCtx, subject: str, description: str) -> dict:
    if (
        _count_today(ctx, Ticket, Ticket.source == "portal", Ticket.contact_id == ctx.contact.id)
        >= MAX_TICKETS_PER_DAY
    ):
        raise Conflict("You have opened a lot of tickets today; please call us or try tomorrow")
    t = tsvc.create_ticket(
        ctx,
        {
            "organization_id": ctx.contact.organization_id,
            "contact_id": ctx.contact.id,
            "subject": " ".join(subject.split()),
            "description": description,
        },
        source="portal",
        requester_email=ctx.contact.email,
    )
    audit.record(
        ctx.db,
        None,
        "portal.ticket_create",
        t,
        organization_id=t.organization_id,
        detail={"contact_id": ctx.contact.id},
    )
    return _ticket_out(ctx, t)


def reply(ctx: PortalCtx, ticket_id: int, body: str) -> dict:
    t = _get_ticket(ctx, ticket_id)
    if (
        _count_today(
            ctx,
            TicketNote,
            TicketNote.source == "portal",
            TicketNote.author_email == ctx.contact.email,
        )
        >= MAX_REPLIES_PER_DAY
    ):
        raise Conflict("You have sent a lot of messages today; please call us")
    note = TicketNote(
        ticket_id=t.id,
        organization_id=t.organization_id,
        author_email=ctx.contact.email,
        visibility="customer",
        source="portal",
        body=body,
    )
    ctx.db.add(note)
    status_before = t.status
    tsvc.reopen_on_customer_activity(ctx, t)
    ctx.db.flush()
    audit.record(
        ctx.db,
        None,
        "portal.ticket_reply",
        note,
        after={"ticket_id": t.id},
        organization_id=t.organization_id,
        detail={
            "contact_id": ctx.contact.id,
            "status_before": status_before,
            "status_after": t.status,
        },
    )
    if t.assignee_id:
        from app import notifications

        notifications.notify(ctx, t.assignee_id, t, "customer_reply", f"n{note.id}")
    return ticket_detail(ctx, t.id)
