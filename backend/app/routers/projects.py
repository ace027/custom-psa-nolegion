from fastapi import APIRouter, Response

from app import permissions as P
from app import projects as svc
from app import repositories as repo
from app import ticket_services as tsvc
from app.deps import Ctx, require
from app.project_schemas import (
    BudgetOut,
    PhaseIn,
    PhaseOut,
    PhasePatch,
    ProjectIn,
    ProjectOut,
    ProjectPatch,
    ProjectStatus,
    ProjectStatusIn,
    ProjectSummaryOut,
    TaskIn,
    TaskOut,
    TaskPatch,
)
from app.schemas import ErrorOut, TicketOut
from app.sla import Calendar
from app.ticket_views import ticket_out

router = APIRouter(tags=["projects"])
ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}


def _project_out(ctx: Ctx, project) -> ProjectOut:
    return ProjectOut(**svc.detail(ctx, project))


def _task_out(ctx: Ctx, task) -> TaskOut:
    project = svc.get_project(ctx, task.project_id)
    return TaskOut(**next(t for t in svc.task_rows(ctx, project) if t["id"] == task.id))


def _phase_out(ctx: Ctx, phase) -> PhaseOut:
    project = svc.get_project(ctx, phase.project_id)
    return PhaseOut(**next(p for p in svc.phase_rows(ctx, project) if p["id"] == phase.id))


def _ticket_view(ctx: Ctx, ticket) -> TicketOut:
    s = repo.get_settings_row(ctx.db)
    cal = Calendar.from_settings(s, repo.holiday_exceptions(ctx.db))
    return ticket_out(ticket, cal, s.sla_at_risk_percent, tsvc.now())


@router.get("/projects", response_model=list[ProjectSummaryOut], summary="List projects")
def list_projects(
    organization_id: int | None = None,
    status: ProjectStatus | None = None,
    ctx: Ctx = require(P.TICKET_READ),
):
    return [svc.summary(ctx, p) for p in svc.list_projects(ctx, organization_id, status)]


@router.post(
    "/projects",
    response_model=ProjectOut,
    status_code=201,
    responses=ERR,
    summary="Create a draft project (billing fields need billing:write)",
)
def create_project(body: ProjectIn, ctx: Ctx = require(P.PROJECT_WRITE)):
    return _project_out(ctx, svc.create_project(ctx, body.model_dump()))


@router.get(
    "/projects/{project_id}",
    response_model=ProjectOut,
    responses=ERR,
    summary="Get a project with phases, tasks and budget",
)
def get_project(project_id: int, ctx: Ctx = require(P.TICKET_READ)):
    return _project_out(ctx, svc.get_project(ctx, project_id))


@router.patch(
    "/projects/{project_id}",
    response_model=ProjectOut,
    responses=ERR,
    summary="Update a project (billing fields need billing:write)",
)
def update_project(project_id: int, body: ProjectPatch, ctx: Ctx = require(P.PROJECT_WRITE)):
    project = svc.update_project(ctx, project_id, body.model_dump(exclude_unset=True))
    return _project_out(ctx, project)


@router.post(
    "/projects/{project_id}/approve",
    response_model=ProjectOut,
    responses=ERR,
    summary="Approve a draft project: locks the billing mode and starts it",
)
def approve_project(project_id: int, ctx: Ctx = require(P.BILLING_WRITE)):
    return _project_out(ctx, svc.approve(ctx, project_id))


@router.post(
    "/projects/{project_id}/status",
    response_model=ProjectOut,
    responses=ERR,
    summary="Put a project on hold, resume, complete or cancel it",
)
def set_project_status(project_id: int, body: ProjectStatusIn, ctx: Ctx = require(P.PROJECT_WRITE)):
    return _project_out(ctx, svc.set_status(ctx, project_id, body.status))


@router.get(
    "/projects/{project_id}/budget",
    response_model=BudgetOut,
    responses=ERR,
    summary="Budget vs actual for a project",
)
def project_budget(project_id: int, ctx: Ctx = require(P.TICKET_READ)):
    return svc.budget(ctx, project_id)


# ---- phases ----
@router.post(
    "/projects/{project_id}/phases",
    response_model=PhaseOut,
    status_code=201,
    responses=ERR,
    summary="Add a phase to a project",
)
def add_phase(project_id: int, body: PhaseIn, ctx: Ctx = require(P.PROJECT_WRITE)):
    return _phase_out(ctx, svc.add_phase(ctx, project_id, body.model_dump()))


@router.patch(
    "/projects/{project_id}/phases/{phase_id}",
    response_model=PhaseOut,
    responses=ERR,
    summary="Rename, reorder or complete a phase",
)
def update_phase(
    project_id: int, phase_id: int, body: PhasePatch, ctx: Ctx = require(P.PROJECT_WRITE)
):
    phase = svc.update_phase(ctx, project_id, phase_id, body.model_dump(exclude_unset=True))
    return _phase_out(ctx, phase)


@router.delete(
    "/projects/{project_id}/phases/{phase_id}",
    status_code=204,
    responses=ERR,
    summary="Delete a phase that has no tasks",
)
def delete_phase(project_id: int, phase_id: int, ctx: Ctx = require(P.PROJECT_WRITE)):
    svc.delete_phase(ctx, project_id, phase_id)
    return Response(status_code=204)


# ---- tasks ----
@router.post(
    "/projects/{project_id}/tasks",
    response_model=TaskOut,
    status_code=201,
    responses=ERR,
    summary="Add a task (creates its ticket)",
)
def add_task(project_id: int, body: TaskIn, ctx: Ctx = require(P.PROJECT_WRITE)):
    return _task_out(ctx, svc.add_task(ctx, project_id, body.model_dump()))


@router.patch(
    "/projects/{project_id}/tasks/{task_id}",
    response_model=TaskOut,
    responses=ERR,
    summary="Update a task and its ticket: status, assignee, phase, estimate, dates",
)
def update_task(
    project_id: int, task_id: int, body: TaskPatch, ctx: Ctx = require(P.PROJECT_WRITE)
):
    task = svc.update_task(ctx, project_id, task_id, body.model_dump(exclude_unset=True))
    return _task_out(ctx, task)


@router.post(
    "/projects/{project_id}/tasks/{task_id}/dependencies/{dep_id}",
    response_model=TaskOut,
    status_code=201,
    responses=ERR,
    summary="Make a task depend on another task of the same project",
)
def add_dependency(project_id: int, task_id: int, dep_id: int, ctx: Ctx = require(P.PROJECT_WRITE)):
    return _task_out(ctx, svc.add_dependency(ctx, task_id, dep_id, project_id))


@router.delete(
    "/projects/{project_id}/tasks/{task_id}/dependencies/{dep_id}",
    response_model=TaskOut,
    responses=ERR,
    summary="Remove a task dependency",
)
def remove_dependency(
    project_id: int, task_id: int, dep_id: int, ctx: Ctx = require(P.PROJECT_WRITE)
):
    return _task_out(ctx, svc.remove_dependency(ctx, task_id, dep_id, project_id))


# ---- existing tickets ----
@router.post(
    "/projects/{project_id}/tickets/{ticket_id}",
    response_model=TicketOut,
    responses=ERR,
    summary="Attach an existing ticket so its time counts toward the project",
)
def attach_ticket(project_id: int, ticket_id: int, ctx: Ctx = require(P.PROJECT_WRITE)):
    return _ticket_view(ctx, svc.attach_ticket(ctx, project_id, ticket_id))


@router.delete(
    "/projects/{project_id}/tickets/{ticket_id}",
    response_model=TicketOut,
    responses=ERR,
    summary="Detach a ticket from a project (not a task's own ticket)",
)
def detach_ticket(project_id: int, ticket_id: int, ctx: Ctx = require(P.PROJECT_WRITE)):
    return _ticket_view(ctx, svc.detach_ticket(ctx, project_id, ticket_id))
