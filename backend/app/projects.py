"""Projects: phases, tasks (each backed by a ticket), dependencies, approval and budget vs actual.

Money rules live in docs/BILLING.md and plan 08-03; this module only records the billing fields
and reports on them. Every row carries organization_id explicitly (the composite FKs and RLS in
migration 0029 enforce the rest).
"""

from datetime import date

from fastapi import HTTPException
from sqlalchemy import case, func, select

from app import api_keys, audit, billing
from app import repositories as repo
from app import ticket_services as tsvc
from app.deps import Ctx
from app.errors import Conflict, NotFound
from app.models import (
    ApiKey,
    Invoice,
    InvoiceLine,
    Project,
    ProjectPhase,
    ProjectTask,
    ProjectTaskDependency,
    Ticket,
    TimeEntry,
    WorkType,
)
from app.money import hours, line_amounts
from app.permissions import BILLING_WRITE, has_permission

BILLING_FIELDS = ("billing_mode", "fixed_fee_cents", "budget_cents", "taxable")
LOCKED_AFTER_APPROVAL = ("billing_mode", "fixed_fee_cents", "taxable")
TRANSITIONS = {
    "draft": {"cancelled"},  # draft -> active only through approve()
    "active": {"on_hold", "completed", "cancelled"},
    "on_hold": {"active"},
    "completed": set(),
    "cancelled": set(),
}
DONE_STATUSES = ("resolved", "closed")
CLOSED_PROJECT = ("completed", "cancelled")


# ---- permissions / lookups ------------------------------------------------------------------
def can_bill(ctx: Ctx) -> bool:
    if ctx.user is None:
        return False
    if ctx.api_key_id is not None:
        key = ctx.db.get(ApiKey, ctx.api_key_id)
        return key is not None and api_keys.effective_permission(key, BILLING_WRITE)
    return has_permission(ctx.user.role, BILLING_WRITE)


def _require_billing(ctx: Ctx) -> None:
    if not can_bill(ctx):
        raise HTTPException(403, "Not permitted")


def get_project(ctx: Ctx, project_id: int) -> Project:
    stmt = ctx.scope.apply(select(Project).where(Project.id == project_id), Project.organization_id)
    project = ctx.db.execute(stmt).scalar_one_or_none()
    if project is None:
        raise NotFound("Project not found")
    return project


def _open_project(ctx: Ctx, project_id: int) -> Project:
    project = get_project(ctx, project_id)
    if project.status in CLOSED_PROJECT:
        raise Conflict(f"This project is {project.status}")
    return project


def _phase(ctx: Ctx, project: Project, phase_id: int) -> ProjectPhase:
    phase = ctx.db.execute(
        select(ProjectPhase).where(
            ProjectPhase.id == phase_id, ProjectPhase.project_id == project.id
        )
    ).scalar_one_or_none()
    if phase is None:
        raise NotFound("Phase not found")
    return phase


def _task(ctx: Ctx, task_id: int, project_id: int | None = None) -> ProjectTask:
    stmt = select(ProjectTask).where(ProjectTask.id == task_id)
    if project_id is not None:
        stmt = stmt.where(ProjectTask.project_id == project_id)
    stmt = ctx.scope.apply(stmt, ProjectTask.organization_id)
    task = ctx.db.execute(stmt).unique().scalar_one_or_none()
    if task is None:
        raise NotFound("Task not found")
    return task


def _check_dates(start: date | None, due: date | None) -> None:
    if start and due and due < start:
        raise Conflict("The due date cannot be before the start date")


def _next_position(ctx: Ctx, model, project_id: int) -> int:
    top = ctx.db.execute(
        select(func.max(model.position)).where(model.project_id == project_id)
    ).scalar_one()
    return 0 if top is None else top + 1


# ---- projects -------------------------------------------------------------------------------
def create_project(ctx: Ctx, data: dict) -> Project:
    org_id = data["organization_id"]
    if repo.get_organization(ctx.db, ctx.scope, org_id) is None:
        raise NotFound("Organization not found")
    if any(data.get(k) not in (None, False) for k in BILLING_FIELDS):
        _require_billing(ctx)
    tsvc._check_assignee(ctx, data.get("owner_id"))
    _check_dates(data.get("start_date"), data.get("due_date"))
    project = Project(
        organization_id=org_id,
        name=data["name"],
        description=data.get("description"),
        start_date=data.get("start_date"),
        due_date=data.get("due_date"),
        owner_id=data.get("owner_id"),
        billing_mode=data.get("billing_mode"),
        fixed_fee_cents=data.get("fixed_fee_cents"),
        budget_cents=data.get("budget_cents"),
        taxable=bool(data.get("taxable")),
    )
    ctx.db.add(project)
    ctx.db.flush()
    ctx.db.refresh(project)
    audit.record(
        ctx.db,
        ctx.user,
        "project.create",
        project,
        after=audit.snapshot(project),
        organization_id=org_id,
    )
    return project


def update_project(ctx: Ctx, project_id: int, data: dict) -> Project:
    project = get_project(ctx, project_id)
    billing_keys = [k for k in BILLING_FIELDS if k in data]
    if billing_keys:
        _require_billing(ctx)
    before = audit.snapshot(project)
    approved = project.approved_at is not None
    budget_changed = False
    if approved:
        for key in LOCKED_AFTER_APPROVAL:
            if key in data and data[key] != getattr(project, key):
                raise Conflict(f"{key} cannot change after the project is approved")
        if "budget_cents" in data and data["budget_cents"] != project.budget_cents:
            if project.billing_mode != "tm" or data["budget_cents"] is None:
                raise Conflict("Only a T&M project's budget can change after approval")
            budget_changed = True
    if "name" in data and data["name"] is None:
        raise Conflict("name cannot be cleared")
    if "taxable" in data and data["taxable"] is None:
        raise Conflict("taxable cannot be cleared")
    if "owner_id" in data:
        tsvc._check_assignee(ctx, data["owner_id"])
    _check_dates(data.get("start_date", project.start_date), data.get("due_date", project.due_date))
    for key in (
        "name",
        "description",
        "start_date",
        "due_date",
        "owner_id",
        "billing_mode",
        "fixed_fee_cents",
        "budget_cents",
        "taxable",
    ):
        if key in data:
            setattr(project, key, data[key])
    ctx.db.flush()
    ctx.db.refresh(project)
    audit.record(
        ctx.db,
        ctx.user,
        "project.budget_change" if budget_changed else "project.update",
        project,
        before=before,
        after=audit.snapshot(project),
        organization_id=project.organization_id,
        detail={"budget_cents": [before["budget_cents"], project.budget_cents]}
        if budget_changed
        else None,
    )
    return project


def approve(ctx: Ctx, project_id: int) -> Project:
    _require_billing(ctx)
    project = get_project(ctx, project_id)
    if project.status != "draft":
        raise Conflict("Only a draft project can be approved")
    if project.billing_mode is None:
        raise Conflict("Choose a billing mode before approving")
    if project.billing_mode == "fixed_fee" and not project.fixed_fee_cents:
        raise Conflict("A fixed-fee project needs a fee before approval")
    if project.billing_mode == "tm" and not project.budget_cents:
        raise Conflict("A T&M project needs a budget before approval")
    before = audit.snapshot(project)
    project.status = "active"
    project.approved_at = tsvc.now()
    project.approved_by_id = ctx.user.id
    ctx.db.flush()
    ctx.db.refresh(project)
    audit.record(
        ctx.db,
        ctx.user,
        "project.approve",
        project,
        before=before,
        after=audit.snapshot(project),
        organization_id=project.organization_id,
    )
    return project


def set_status(ctx: Ctx, project_id: int, status: str) -> Project:
    project = get_project(ctx, project_id)
    if status == "active" and project.status == "draft":
        raise Conflict("Approve the project to activate it")
    if status not in TRANSITIONS.get(project.status, set()):
        raise Conflict(f"A {project.status} project cannot become {status}")
    before = audit.snapshot(project)
    project.status = status
    ctx.db.flush()
    ctx.db.refresh(project)
    audit.record(
        ctx.db,
        ctx.user,
        "project.status",
        project,
        before={"status": before["status"]},
        after={"status": status},
        organization_id=project.organization_id,
    )
    return project


def list_projects(
    ctx: Ctx, organization_id: int | None = None, status: str | None = None
) -> list[Project]:
    stmt = ctx.scope.apply(select(Project), Project.organization_id)
    if organization_id is not None:
        stmt = stmt.where(Project.organization_id == organization_id)
    if status is not None:
        stmt = stmt.where(Project.status == status)
    return list(ctx.db.execute(stmt.order_by(Project.id.desc())).scalars())


# ---- phases ---------------------------------------------------------------------------------
def add_phase(ctx: Ctx, project_id: int, data: dict) -> ProjectPhase:
    project = _open_project(ctx, project_id)
    position = data.get("position")
    phase = ProjectPhase(
        organization_id=project.organization_id,
        project_id=project.id,
        name=data["name"],
        position=_next_position(ctx, ProjectPhase, project.id) if position is None else position,
        due_date=data.get("due_date"),
    )
    ctx.db.add(phase)
    ctx.db.flush()
    ctx.db.refresh(phase)
    audit.record(
        ctx.db,
        ctx.user,
        "project_phase.create",
        phase,
        after=audit.snapshot(phase),
        organization_id=project.organization_id,
    )
    return phase


def update_phase(ctx: Ctx, project_id: int, phase_id: int, data: dict) -> ProjectPhase:
    project = _open_project(ctx, project_id)
    phase = _phase(ctx, project, phase_id)
    before = audit.snapshot(phase)
    for key in ("name", "position"):
        if key in data:
            if data[key] is None:
                raise Conflict(f"{key} cannot be cleared")
            setattr(phase, key, data[key])
    if "due_date" in data:
        phase.due_date = data["due_date"]
    if "completed" in data and data["completed"] is not None:
        if data["completed"] and phase.completed_at is None:
            phase.completed_at = tsvc.now()
        elif not data["completed"]:
            phase.completed_at = None
    ctx.db.flush()
    ctx.db.refresh(phase)
    audit.record(
        ctx.db,
        ctx.user,
        "project_phase.update",
        phase,
        before=before,
        after=audit.snapshot(phase),
        organization_id=project.organization_id,
    )
    return phase


def delete_phase(ctx: Ctx, project_id: int, phase_id: int) -> None:
    project = _open_project(ctx, project_id)
    phase = _phase(ctx, project, phase_id)
    has_tasks = ctx.db.execute(
        select(func.count()).select_from(ProjectTask).where(ProjectTask.phase_id == phase.id)
    ).scalar_one()
    if has_tasks:
        raise Conflict("Move or remove this phase's tasks first")
    before = audit.snapshot(phase)
    ctx.db.delete(phase)
    ctx.db.flush()
    audit.record(
        ctx.db,
        ctx.user,
        "project_phase.delete",
        phase,
        before=before,
        organization_id=project.organization_id,
    )


# ---- tasks ----------------------------------------------------------------------------------
def add_task(ctx: Ctx, project_id: int, data: dict) -> ProjectTask:
    project = _open_project(ctx, project_id)
    if data.get("phase_id") is not None:
        _phase(ctx, project, data["phase_id"])
    _check_dates(data.get("start_date"), data.get("due_date"))
    ticket = tsvc.create_ticket(
        ctx,
        {
            "organization_id": project.organization_id,
            "subject": data["title"],
            "description": data.get("description"),
            "queue_id": data.get("queue_id"),
            "priority_id": data.get("priority_id"),
            "assignee_id": data.get("assignee_id"),
        },
        source="project",
    )
    ticket.project_id = project.id
    ctx.db.flush()
    position = data.get("position")
    task = ProjectTask(
        organization_id=project.organization_id,
        project_id=project.id,
        phase_id=data.get("phase_id"),
        ticket_id=ticket.id,
        estimate_minutes=data.get("estimate_minutes", 0),
        start_date=data.get("start_date"),
        due_date=data.get("due_date"),
        position=_next_position(ctx, ProjectTask, project.id) if position is None else position,
    )
    ctx.db.add(task)
    ctx.db.flush()
    ctx.db.refresh(task)
    ctx.db.refresh(ticket)
    audit.record(
        ctx.db,
        ctx.user,
        "project_task.create",
        task,
        after=audit.snapshot(task),
        organization_id=project.organization_id,
        detail={"ticket_id": ticket.id},
    )
    return task


def update_task(ctx: Ctx, project_id: int, task_id: int, data: dict) -> ProjectTask:
    project = _open_project(ctx, project_id)
    task = _task(ctx, task_id, project.id)
    before = audit.snapshot(task)
    if data.get("phase_id") is not None:
        _phase(ctx, project, data["phase_id"])
    _check_dates(data.get("start_date", task.start_date), data.get("due_date", task.due_date))
    if "estimate_minutes" in data and data["estimate_minutes"] is None:
        raise Conflict("estimate_minutes cannot be cleared")
    if "position" in data and data["position"] is None:
        raise Conflict("position cannot be cleared")
    ticket_changes = {
        ("subject" if k == "title" else k): data[k]
        for k in (
            "title",
            "description",
            "queue_id",
            "priority_id",
            "assignee_id",
            "status",
            "status_id",
        )
        if k in data
    }
    if ticket_changes:
        tsvc.update_ticket(ctx, task.ticket_id, ticket_changes)
    for key in ("phase_id", "estimate_minutes", "start_date", "due_date", "position"):
        if key in data:
            setattr(task, key, data[key])
    ctx.db.flush()
    ctx.db.refresh(task)
    audit.record(
        ctx.db,
        ctx.user,
        "project_task.update",
        task,
        before=before,
        after=audit.snapshot(task),
        organization_id=project.organization_id,
        detail={"ticket_fields": sorted(ticket_changes)} if ticket_changes else None,
    )
    return task


# ---- dependencies ---------------------------------------------------------------------------
def _reaches(ctx: Ctx, project_id: int, start: int, target: int) -> bool:
    """Depth-first walk of 'depends on' edges from `start`; True when `target` is reachable."""
    edges: dict[int, list[int]] = {}
    rows = ctx.db.execute(
        select(ProjectTaskDependency.task_id, ProjectTaskDependency.depends_on_task_id)
        .join(ProjectTask, ProjectTask.id == ProjectTaskDependency.task_id)
        .where(ProjectTask.project_id == project_id)
    )
    for task_id, dep_id in rows:
        edges.setdefault(task_id, []).append(dep_id)
    seen: set[int] = set()
    stack = [start]
    while stack:
        node = stack.pop()
        if node == target:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(edges.get(node, ()))
    return False


def add_dependency(
    ctx: Ctx, task_id: int, depends_on_task_id: int, project_id: int | None = None
) -> ProjectTask:
    task = _task(ctx, task_id, project_id)
    # Serialize dependency edits per project so two requests cannot each pass the loop check.
    ctx.db.execute(select(Project.id).where(Project.id == task.project_id).with_for_update())
    _open_project(ctx, task.project_id)
    dep = _task(ctx, depends_on_task_id)
    if dep.project_id != task.project_id:
        raise Conflict("A task can only depend on a task in the same project")
    if dep.id == task.id:
        raise Conflict("A task cannot depend on itself")
    exists = ctx.db.execute(
        select(ProjectTaskDependency.id).where(
            ProjectTaskDependency.task_id == task.id,
            ProjectTaskDependency.depends_on_task_id == dep.id,
        )
    ).first()
    if exists:
        raise Conflict("That dependency already exists")
    if _reaches(ctx, task.project_id, dep.id, task.id):
        raise Conflict("That dependency would create a loop")
    edge = ProjectTaskDependency(
        organization_id=task.organization_id, task_id=task.id, depends_on_task_id=dep.id
    )
    ctx.db.add(edge)
    ctx.db.flush()
    audit.record(
        ctx.db,
        ctx.user,
        "project_task_dependency.add",
        edge,
        after={"task_id": task.id, "depends_on_task_id": dep.id},
        organization_id=task.organization_id,
    )
    return task


def remove_dependency(
    ctx: Ctx, task_id: int, depends_on_task_id: int, project_id: int | None = None
) -> ProjectTask:
    task = _task(ctx, task_id, project_id)
    _open_project(ctx, task.project_id)
    edge = ctx.db.execute(
        select(ProjectTaskDependency).where(
            ProjectTaskDependency.task_id == task.id,
            ProjectTaskDependency.depends_on_task_id == depends_on_task_id,
        )
    ).scalar_one_or_none()
    if edge is None:
        raise NotFound("Dependency not found")
    ctx.db.delete(edge)
    ctx.db.flush()
    audit.record(
        ctx.db,
        ctx.user,
        "project_task_dependency.remove",
        edge,
        before={"task_id": task.id, "depends_on_task_id": depends_on_task_id},
        organization_id=task.organization_id,
    )
    return task


# ---- existing tickets -----------------------------------------------------------------------
def attach_ticket(ctx: Ctx, project_id: int, ticket_id: int) -> Ticket:
    """Link an existing ticket so its time counts toward the project (no task is created)."""
    project = _open_project(ctx, project_id)
    ticket = repo.get_ticket(ctx.db, ctx.scope, ticket_id)
    if ticket is None:
        raise NotFound("Ticket not found")
    if ticket.organization_id != project.organization_id:
        raise Conflict("That ticket belongs to a different organization")
    if ticket.project_id is not None:
        raise Conflict("That ticket is already in a project")
    ticket.project_id = project.id
    ctx.db.flush()
    ctx.db.refresh(ticket)
    audit.record(
        ctx.db,
        ctx.user,
        "project.attach_ticket",
        project,
        after={"ticket_id": ticket.id},
        organization_id=project.organization_id,
    )
    return ticket


def detach_ticket(ctx: Ctx, project_id: int, ticket_id: int) -> Ticket:
    project = _open_project(ctx, project_id)
    ticket = repo.get_ticket(ctx.db, ctx.scope, ticket_id)
    if ticket is None:
        raise NotFound("Ticket not found")
    if ticket.project_id != project.id:
        raise Conflict("That ticket is not in this project")
    owned = ctx.db.execute(select(ProjectTask.id).where(ProjectTask.ticket_id == ticket.id)).first()
    if owned:
        raise Conflict("A task's own ticket cannot be detached")
    ticket.project_id = None
    ctx.db.flush()
    ctx.db.refresh(ticket)
    audit.record(
        ctx.db,
        ctx.user,
        "project.detach_ticket",
        project,
        before={"ticket_id": ticket.id},
        organization_id=project.organization_id,
    )
    return ticket


# ---- budget vs actual -----------------------------------------------------------------------
def _minutes_by_ticket(ctx: Ctx, project_id: int) -> dict[int, int]:
    rows = ctx.db.execute(
        select(TimeEntry.ticket_id, func.sum(TimeEntry.minutes_actual))
        .join(Ticket, Ticket.id == TimeEntry.ticket_id)
        .where(Ticket.project_id == project_id, TimeEntry.voided_at.is_(None))
        .group_by(TimeEntry.ticket_id)
    )
    return {ticket_id: int(total) for ticket_id, total in rows}


def budget(ctx: Ctx, project_id: int) -> dict:
    project = get_project(ctx, project_id)
    estimate = ctx.db.execute(
        select(func.coalesce(func.sum(ProjectTask.estimate_minutes), 0)).where(
            ProjectTask.project_id == project.id
        )
    ).scalar_one()
    by_type = ctx.db.execute(
        select(
            TimeEntry.work_type_id,
            func.sum(TimeEntry.minutes_actual),
            func.coalesce(
                func.sum(case((TimeEntry.billable.is_(True), TimeEntry.minutes_billable), else_=0)),
                0,
            ),
        )
        .join(Ticket, Ticket.id == TimeEntry.ticket_id)
        .where(
            Ticket.project_id == project.id,
            TimeEntry.voided_at.is_(None),
            # owner decision 2026-10-30: automation time is not project labour or billing
            TimeEntry.entry_type == "labour",
        )
        .group_by(TimeEntry.work_type_id)
    ).all()
    minutes = 0
    billable_minutes = 0
    cost = 0
    for work_type_id, actual, total in by_type:
        total = int(total)
        minutes += int(actual)
        billable_minutes += total
        wt = ctx.db.get(WorkType, work_type_id)
        rate = billing.hourly_rate(ctx, project.organization_id, wt)
        if rate is not None:
            cost += line_amounts(hours(total), rate, 0)[0]
    billed = ctx.db.execute(
        select(func.coalesce(func.sum(InvoiceLine.amount_cents), 0))
        .join(Invoice, Invoice.id == InvoiceLine.invoice_id)
        .where(
            InvoiceLine.project_id == project.id,
            InvoiceLine.voided.is_(False),
            Invoice.status != "void",
        )
    ).scalar_one()
    billed = int(billed)
    remaining = None
    cap = None
    if project.billing_mode == "tm" and project.budget_cents:
        remaining = max(0, project.budget_cents - billed)
        cap = project.budget_cents
    elif project.billing_mode == "fixed_fee":
        cap = project.fixed_fee_cents
    return {
        "estimate_minutes": int(estimate),
        "actual_minutes": minutes,
        "billable_minutes": billable_minutes,
        "cost_at_rates_cents": cost,
        "billed_cents": billed,
        "remaining_cents": remaining,
        "over_budget": cap is not None and cost > cap,
    }


# ---- read model for the API -----------------------------------------------------------------
def task_rows(ctx: Ctx, project: Project) -> list[dict]:
    tasks = list(
        ctx.db.execute(
            select(ProjectTask)
            .where(ProjectTask.project_id == project.id)
            .order_by(ProjectTask.position, ProjectTask.id)
        )
        .unique()
        .scalars()
    )
    deps: dict[int, list[int]] = {}
    for task_id, dep_id in ctx.db.execute(
        select(ProjectTaskDependency.task_id, ProjectTaskDependency.depends_on_task_id)
        .join(ProjectTask, ProjectTask.id == ProjectTaskDependency.task_id)
        .where(ProjectTask.project_id == project.id)
        .order_by(ProjectTaskDependency.id)
    ):
        deps.setdefault(task_id, []).append(dep_id)
    done = {t.id: t.ticket.status in DONE_STATUSES for t in tasks}
    minutes = _minutes_by_ticket(ctx, project.id)
    out = []
    for t in tasks:
        ticket = t.ticket
        out.append(
            {
                "id": t.id,
                "project_id": t.project_id,
                "ticket_id": t.ticket_id,
                "ticket_number": ticket.number,
                "title": ticket.subject,
                "status": ticket.status,
                "status_name": ticket.status_ref.name,
                "assignee_id": ticket.assignee_id,
                "assignee_name": ticket.assignee.display_name if ticket.assignee else None,
                "phase_id": t.phase_id,
                "estimate_minutes": t.estimate_minutes,
                "actual_minutes": minutes.get(t.ticket_id, 0),
                "start_date": t.start_date,
                "due_date": t.due_date,
                "position": t.position,
                "depends_on": deps.get(t.id, []),
                "blocked": any(not done.get(d, True) for d in deps.get(t.id, [])),
            }
        )
    return out


def phase_rows(ctx: Ctx, project: Project) -> list[dict]:
    counts = dict(
        ctx.db.execute(
            select(ProjectTask.phase_id, func.count())
            .where(ProjectTask.project_id == project.id, ProjectTask.phase_id.is_not(None))
            .group_by(ProjectTask.phase_id)
        ).all()
    )
    phases = ctx.db.execute(
        select(ProjectPhase)
        .where(ProjectPhase.project_id == project.id)
        .order_by(ProjectPhase.position, ProjectPhase.id)
    ).scalars()
    return [
        {
            "id": p.id,
            "project_id": p.project_id,
            "name": p.name,
            "position": p.position,
            "due_date": p.due_date,
            "completed_at": p.completed_at,
            "task_count": counts.get(p.id, 0),
        }
        for p in phases
    ]


def summary(ctx: Ctx, project: Project) -> dict:
    org = repo.get_organization(ctx.db, ctx.scope, project.organization_id)
    row = ctx.db.execute(
        select(func.count(), func.count().filter(Ticket.status.in_(DONE_STATUSES)))
        .select_from(ProjectTask)
        .join(Ticket, Ticket.id == ProjectTask.ticket_id)
        .where(ProjectTask.project_id == project.id)
    ).one()
    return {
        "id": project.id,
        "organization_id": project.organization_id,
        "organization_name": org.name if org else "",
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "start_date": project.start_date,
        "due_date": project.due_date,
        "owner_id": project.owner_id,
        "approved_at": project.approved_at,
        "billing_mode": project.billing_mode,
        "fixed_fee_cents": project.fixed_fee_cents,
        "budget_cents": project.budget_cents,
        "taxable": project.taxable,
        "fixed_fee_billed": project.fixed_fee_invoice_line_id is not None,
        "task_count": row[0],
        "done_count": row[1],
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }


def detail(ctx: Ctx, project: Project) -> dict:
    return {
        **summary(ctx, project),
        "approved_by_id": project.approved_by_id,
        "phases": phase_rows(ctx, project),
        "tasks": task_rows(ctx, project),
        "budget": budget(ctx, project.id),
    }
