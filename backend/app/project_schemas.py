"""Request and response shapes for projects, phases, tasks, dependencies and budget."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas import TicketStatus

ProjectStatus = Literal["draft", "active", "on_hold", "completed", "cancelled"]
BillingMode = Literal["fixed_fee", "tm"]
CENTS = 10_000_000_000  # upper bound on any money field


class ProjectIn(BaseModel):
    organization_id: int
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=100_000)
    start_date: date | None = None
    due_date: date | None = None
    owner_id: int | None = None
    # billing fields: need billing:write
    billing_mode: BillingMode | None = None
    fixed_fee_cents: int | None = Field(default=None, gt=0, le=CENTS)
    budget_cents: int | None = Field(default=None, gt=0, le=CENTS)
    taxable: bool | None = None


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=100_000)
    start_date: date | None = None
    due_date: date | None = None
    owner_id: int | None = None
    billing_mode: BillingMode | None = None
    fixed_fee_cents: int | None = Field(default=None, gt=0, le=CENTS)
    budget_cents: int | None = Field(default=None, gt=0, le=CENTS)
    taxable: bool | None = None


class ProjectStatusIn(BaseModel):
    status: ProjectStatus


class PhaseIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    position: int | None = Field(default=None, ge=0, le=100_000)
    due_date: date | None = None


class PhasePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    position: int | None = Field(default=None, ge=0, le=100_000)
    due_date: date | None = None
    completed: bool | None = None


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=100_000)
    phase_id: int | None = None
    queue_id: int | None = None
    priority_id: int | None = None
    assignee_id: int | None = None
    estimate_minutes: int = Field(default=0, ge=0, le=1_000_000)
    start_date: date | None = None
    due_date: date | None = None
    position: int | None = Field(default=None, ge=0, le=100_000)


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=100_000)
    phase_id: int | None = None  # null moves the task out of its phase
    queue_id: int | None = None
    priority_id: int | None = None
    assignee_id: int | None = None
    status: TicketStatus | None = None
    status_id: int | None = None
    estimate_minutes: int | None = Field(default=None, ge=0, le=1_000_000)
    start_date: date | None = None
    due_date: date | None = None
    position: int | None = Field(default=None, ge=0, le=100_000)


class PhaseOut(BaseModel):
    id: int
    project_id: int
    name: str
    position: int
    due_date: date | None
    completed_at: datetime | None
    task_count: int


class TaskOut(BaseModel):
    id: int
    project_id: int
    ticket_id: int
    ticket_number: int
    title: str
    status: TicketStatus
    status_name: str
    assignee_id: int | None
    assignee_name: str | None
    phase_id: int | None
    estimate_minutes: int
    actual_minutes: int
    start_date: date | None
    due_date: date | None
    position: int
    depends_on: list[int]
    blocked: bool


class BudgetOut(BaseModel):
    estimate_minutes: int
    actual_minutes: int
    billable_minutes: int
    cost_at_rates_cents: int
    billed_cents: int
    remaining_cents: int | None  # T&M: max(0, budget - billed); fixed fee: null
    over_budget: bool


class ProjectSummaryOut(BaseModel):
    id: int
    organization_id: int
    organization_name: str
    name: str
    description: str | None
    status: ProjectStatus
    start_date: date | None
    due_date: date | None
    owner_id: int | None
    approved_at: datetime | None
    billing_mode: BillingMode | None
    fixed_fee_cents: int | None
    budget_cents: int | None
    taxable: bool
    fixed_fee_billed: bool
    task_count: int
    done_count: int
    created_at: datetime
    updated_at: datetime


class ProjectOut(ProjectSummaryOut):
    approved_by_id: int | None
    phases: list[PhaseOut]
    tasks: list[TaskOut]
    budget: BudgetOut
