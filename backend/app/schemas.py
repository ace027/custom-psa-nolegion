from datetime import date, datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Role = Literal["admin", "tech", "billing", "read_only"]
OrgStatus = Literal["active", "inactive"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorOut(BaseModel):
    detail: str


# ---- organizations ----
class OrganizationIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    status: OrgStatus = "active"
    billing_address: str | None = None
    notes: str | None = None


class OrganizationPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    status: OrgStatus | None = None
    billing_address: str | None = None
    notes: str | None = None


class OrganizationOut(ORM):
    id: int
    name: str
    status: str
    billing_address: str | None
    notes: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ---- sites ----
class SiteIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    notes: str | None = None


class SitePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    notes: str | None = None


class SiteOut(ORM):
    id: int
    organization_id: int
    name: str
    address_line1: str | None
    address_line2: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    notes: str | None
    archived_at: datetime | None


# ---- contacts ----
class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = None
    title: str | None = None
    site_id: int | None = None
    is_primary: bool = False
    is_billing_contact: bool = False


class ContactPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = None
    title: str | None = None
    site_id: int | None = None
    is_primary: bool | None = None
    is_billing_contact: bool | None = None


class ContactOut(ORM):
    id: int
    organization_id: int
    site_id: int | None
    name: str
    email: str | None
    phone: str | None
    title: str | None
    is_primary: bool
    is_billing_contact: bool
    archived_at: datetime | None


# ---- users ----
class UserIn(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=200)
    role: Role


class UserPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    role: Role | None = None
    is_active: bool | None = None


class UserOut(ORM):
    id: int
    email: str
    display_name: str
    role: str
    is_active: bool
    last_login_at: datetime | None


class MeOut(UserOut):
    permissions: list[str]


class DevLoginIn(BaseModel):
    email: EmailStr


# ---- audit ----
class AuditOut(ORM):
    id: int
    occurred_at: datetime
    actor_type: str
    actor_id: int | None
    action: str
    entity_type: str | None
    entity_id: int | None
    organization_id: int | None
    before: dict | None
    after: dict | None
    detail: dict | None
    request_id: str | None
    ip: str | None


# ---------------------------------------------------------------------------------------
# Phase 2: ticketing
# ---------------------------------------------------------------------------------------
TicketStatus = Literal["new", "open", "waiting_on_customer", "resolved", "closed"]
Visibility = Literal["internal", "customer"]
SlaState = Literal["none", "ok", "at_risk", "breached", "paused", "done"]


class TicketIn(BaseModel):
    organization_id: int
    contact_id: int | None = None
    site_id: int | None = None
    queue_id: int | None = None  # default queue when omitted
    category_id: int | None = None
    priority_id: int | None = None  # default priority when omitted
    assignee_id: int | None = None
    subject: str = Field(min_length=1, max_length=300)
    description: str | None = None


class TicketPatch(BaseModel):
    subject: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    organization_id: int | None = None  # only to triage a ticket that has none
    contact_id: int | None = None
    site_id: int | None = None
    queue_id: int | None = None
    category_id: int | None = None
    priority_id: int | None = None
    assignee_id: int | None = None
    status: TicketStatus | None = None


class TicketOut(BaseModel):
    id: int
    number: int
    organization_id: int | None
    organization_name: str | None
    contact_id: int | None
    contact_name: str | None
    site_id: int | None
    queue_id: int
    queue_name: str
    category_id: int | None
    category_name: str | None
    priority_id: int
    priority_name: str
    priority_rank: int
    status: TicketStatus
    assignee_id: int | None
    assignee_name: str | None
    subject: str
    description: str | None
    source: str
    requester_email: str | None
    needs_triage: bool
    sla_state: SlaState
    sla_first_response_due: datetime | None
    sla_resolution_due: datetime | None
    first_responded_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=100_000)
    visibility: Visibility = "internal"
    send_email: bool = False  # only with visibility=customer


class NoteOut(BaseModel):
    id: int
    ticket_id: int
    author_user_id: int | None
    author_name: str | None
    author_email: str | None
    visibility: Visibility
    source: str
    body: str
    created_at: datetime
    email_status: str | None  # pending|sent|failed (outbound) or received (inbound)


class TimeIn(BaseModel):
    work_type_id: int
    minutes: int = Field(ge=1, le=1440)
    work_date: date | None = None  # defaults to today in the business timezone
    billable: bool = True
    note: str | None = None
    user_id: int | None = None  # admin only; defaults to the caller


class TimePatch(BaseModel):
    work_type_id: int | None = None
    minutes: int | None = Field(default=None, ge=1, le=1440)
    work_date: date | None = None
    billable: bool | None = None
    note: str | None = None


class TimeOut(ORM):
    id: int
    ticket_id: int
    organization_id: int
    user_id: int
    work_type_id: int
    work_date: date
    minutes_actual: int
    minutes_billable: int
    billable: bool
    note: str | None
    voided_at: datetime | None


class AttachmentOut(ORM):
    id: int
    ticket_id: int
    filename: str
    content_type: str | None
    size_bytes: int
    created_at: datetime


class LookupOut(ORM):
    id: int
    name: str
    archived_at: datetime | None


class QueueIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    is_default: bool = False


class QueuePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_default: bool | None = None


class QueueOut(LookupOut):
    is_default: bool


class NameIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class PriorityIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    rank: int = Field(ge=1, le=99)
    first_response_minutes: int | None = Field(default=None, ge=1)
    resolution_minutes: int | None = Field(default=None, ge=1)
    is_default: bool = False


class PriorityPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    rank: int | None = Field(default=None, ge=1, le=99)
    first_response_minutes: int | None = Field(default=None, ge=1)
    resolution_minutes: int | None = Field(default=None, ge=1)
    is_default: bool | None = None


class PriorityOut(LookupOut):
    rank: int
    first_response_minutes: int | None
    resolution_minutes: int | None
    is_default: bool


class SettingsOut(ORM):
    timezone: str
    business_days: list[int]
    business_start_minute: int
    business_end_minute: int
    billing_increment_minutes: int
    sla_at_risk_percent: int


class SettingsPatch(BaseModel):
    timezone: str | None = None
    business_days: list[int] | None = None
    business_start_minute: int | None = None
    business_end_minute: int | None = None
    billing_increment_minutes: int | None = Field(default=None, ge=1, le=240)
    sla_at_risk_percent: int | None = Field(default=None, ge=0, le=100)


class DashboardOut(BaseModel):
    my_open: list[TicketOut]
    unassigned: list[TicketOut]
    sla_at_risk: list[TicketOut]
    counts: dict[str, int]


class MailStatusOut(BaseModel):
    configured: bool
    mailbox: str | None
    worker_seen_at: datetime | None
    last_poll_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    last_error_at: datetime | None
    messages_ingested: int
    outbound_pending: int
    outbound_failed: int
    tickets_needing_triage: int


class NamePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
