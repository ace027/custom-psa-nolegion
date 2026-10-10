"""Editable configuration (admin) plus read access for everyone who can see tickets."""

from fastapi import APIRouter
from sqlalchemy import func, select

from app import config_services as svc
from app import permissions as P
from app import repositories as repo
from app.deps import Ctx, require
from app.models import (
    CannedResponse,
    Category,
    EmailMessage,
    ExpenseCategory,
    Priority,
    Queue,
    Ticket,
    TicketType,
    TimeCategory,
    WorkType,
)
from app.schemas import (
    CannedIn,
    CannedOut,
    CannedPatch,
    ErrorOut,
    LookupOut,
    MailStatusOut,
    NameIn,
    NamePatch,
    PriorityIn,
    PriorityOut,
    PriorityPatch,
    QueueIn,
    QueueOut,
    QueuePatch,
    SettingsOut,
    SettingsPatch,
)

router = APIRouter(tags=["configuration"])
ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}

# path segment, model, label (used in audit action names), create/patch/out schemas
LOOKUPS = [
    ("queues", Queue, "queue", QueueIn, QueuePatch, QueueOut),
    ("categories", Category, "category", NameIn, NamePatch, LookupOut),
    ("priorities", Priority, "priority", PriorityIn, PriorityPatch, PriorityOut),
    ("work-types", WorkType, "work_type", NameIn, NamePatch, LookupOut),
    ("time-categories", TimeCategory, "time_category", NameIn, NamePatch, LookupOut),
    ("expense-categories", ExpenseCategory, "expense_category", NameIn, NamePatch, LookupOut),
    ("ticket-types", TicketType, "ticket_type", NameIn, NamePatch, LookupOut),
    ("canned-responses", CannedResponse, "canned_response", CannedIn, CannedPatch, CannedOut),
]


def _register(path, model, label, schema_in, schema_patch, schema_out):
    pretty = label.replace("_", " ")

    def list_(include_archived: bool = False, ctx: Ctx = require(P.TICKET_READ)):
        return repo.list_lookup(ctx.db, model, include_archived)

    def create(body: schema_in, ctx: Ctx = require(P.CONFIG_MANAGE)):  # type: ignore[valid-type]
        return svc.create_lookup(ctx, model, label, body.model_dump())

    def update(
        item_id: int,
        body: schema_patch,  # type: ignore[valid-type]
        ctx: Ctx = require(P.CONFIG_MANAGE),
    ):
        return svc.update_lookup(ctx, model, label, item_id, body.model_dump(exclude_unset=True))

    def archive(item_id: int, ctx: Ctx = require(P.CONFIG_MANAGE)):
        return svc.set_lookup_archived(ctx, model, label, item_id, True)

    def unarchive(item_id: int, ctx: Ctx = require(P.CONFIG_MANAGE)):
        return svc.set_lookup_archived(ctx, model, label, item_id, False)

    for fn, suffix in (
        (list_, "list"),
        (create, "create"),
        (update, "update"),
        (archive, "archive"),
        (unarchive, "unarchive"),
    ):
        fn.__name__ = f"{suffix}_{label}"
    router.add_api_route(
        f"/{path}",
        list_,
        methods=["GET"],
        response_model=list[schema_out],
        summary=f"List {pretty}s",
    )
    router.add_api_route(
        f"/{path}",
        create,
        methods=["POST"],
        response_model=schema_out,
        status_code=201,
        responses=ERR,
        summary=f"Create a {pretty} (admin)",
    )
    router.add_api_route(
        f"/{path}/{{item_id}}",
        update,
        methods=["PATCH"],
        response_model=schema_out,
        responses=ERR,
        summary=f"Update a {pretty} (admin)",
    )
    router.add_api_route(
        f"/{path}/{{item_id}}/archive",
        archive,
        methods=["POST"],
        response_model=schema_out,
        responses=ERR,
        summary=f"Archive a {pretty} (admin)",
    )
    router.add_api_route(
        f"/{path}/{{item_id}}/unarchive",
        unarchive,
        methods=["POST"],
        response_model=schema_out,
        responses=ERR,
        summary=f"Restore an archived {pretty} (admin)",
    )


for spec in LOOKUPS:
    _register(*spec)


@router.get(
    "/settings",
    response_model=SettingsOut,
    summary="Business hours, billing increment and SLA settings",
)
def get_settings_(ctx: Ctx = require(P.TICKET_READ)):
    return repo.get_settings_row(ctx.db)


@router.patch(
    "/settings",
    response_model=SettingsOut,
    responses=ERR,
    summary="Change business hours, billing increment or SLA settings (admin)",
)
def patch_settings(body: SettingsPatch, ctx: Ctx = require(P.CONFIG_MANAGE)):
    return svc.update_settings(ctx, body.model_dump(exclude_unset=True))


@router.get(
    "/mail/status",
    response_model=MailStatusOut,
    summary="Mailbox connector health: last poll, errors, outbound queue (admin)",
)
def mail_status(ctx: Ctx = require(P.CONFIG_MANAGE)):
    st = repo.get_mailbox_status(ctx.db)

    def count(stmt) -> int:
        return ctx.db.execute(stmt).scalar_one()

    out = EmailMessage
    return MailStatusOut(
        configured=st.mailbox is not None,
        mailbox=st.mailbox,
        worker_seen_at=st.worker_seen_at,
        last_poll_at=st.last_poll_at,
        last_success_at=st.last_success_at,
        last_error=st.last_error,
        last_error_at=st.last_error_at,
        messages_ingested=st.messages_ingested,
        outbound_pending=count(
            select(func.count()).where(out.direction == "out", out.send_status == "pending")
        ),
        outbound_failed=count(
            select(func.count()).where(out.direction == "out", out.send_status == "failed")
        ),
        tickets_needing_triage=count(
            select(func.count())
            .select_from(Ticket)
            .where(Ticket.organization_id.is_(None), Ticket.status.in_(repo.OPEN_STATUSES))
        ),
    )
