from datetime import date, datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

Role = Literal["admin", "tech", "billing", "read_only"]
OrgStatus = Literal["active", "inactive", "prospect"]


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
    assets_published: bool
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
    portal_access: bool = False
    portal_org_tickets: bool = False
    portal_assets: bool = False


class ContactPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = None
    title: str | None = None
    site_id: int | None = None
    is_primary: bool | None = None
    is_billing_contact: bool | None = None
    portal_access: bool | None = None
    portal_org_tickets: bool | None = None
    portal_assets: bool | None = None


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
    portal_access: bool
    portal_org_tickets: bool
    portal_assets: bool
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
    notify_assigned: bool
    notify_sla: bool
    notify_reply: bool


class NotificationPrefsPatch(BaseModel):
    notify_assigned: bool | None = None
    notify_sla: bool | None = None
    notify_reply: bool | None = None


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
    type_id: int | None = None
    custom_values: dict[str, Any] = Field(default_factory=dict)  # keys are custom field ids


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
    status: TicketStatus | None = None  # a built-in behaviour: uses its first named status
    status_id: int | None = None  # a specific named status (wins over `status`)
    type_id: int | None = None  # null clears the type (stored values are kept, just hidden)
    custom_values: dict[str, Any] | None = None  # merged by field id; null/blank clears one


class BulkChanges(BaseModel):
    """The fields a bulk action may change. Absent = leave alone; assignee_id null = unassign."""

    status: TicketStatus | None = None
    status_id: int | None = None
    assignee_id: int | None = None
    queue_id: int | None = None
    priority_id: int | None = None


class BulkTicketsIn(BaseModel):
    ticket_ids: list[int] = Field(min_length=1, max_length=100)
    changes: BulkChanges


class BulkFailure(BaseModel):
    id: int
    error: str


class BulkTicketsOut(BaseModel):
    updated: int
    failed: list[BulkFailure]


class SearchHit(BaseModel):
    kind: str  # ticket | organization | contact | asset
    id: int
    title: str
    subtitle: str | None
    organization_id: int | None


class SearchOut(BaseModel):
    q: str
    hits: list[SearchHit]


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
    status_id: int
    status_name: str
    type_id: int | None
    type_name: str | None
    custom_values: dict[str, Any]
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
    invoice_line_id: int | None = None
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


class InternalTimeIn(BaseModel):
    category_id: int
    minutes: int = Field(ge=1, le=1440)
    work_date: date | None = None
    note: str | None = Field(default=None, max_length=2000)
    user_id: int | None = None  # admin only; defaults to the caller


class InternalTimePatch(BaseModel):
    category_id: int | None = None
    minutes: int | None = Field(default=None, ge=1, le=1440)
    work_date: date | None = None
    note: str | None = Field(default=None, max_length=2000)


class InternalTimeOut(ORM):
    id: int
    user_id: int
    category_id: int
    work_date: date
    minutes: int
    note: str | None
    voided_at: datetime | None


class TimerStartIn(BaseModel):
    ticket_id: int | None = None  # ticket time: needs work_type_id
    work_type_id: int | None = None
    category_id: int | None = None  # internal time
    billable: bool = True
    note: str | None = Field(default=None, max_length=2000)


class TimerOut(BaseModel):
    ticket_id: int | None
    ticket_number: int | None
    ticket_subject: str | None
    work_type_id: int | None
    category_id: int | None
    category_name: str | None
    billable: bool
    note: str | None
    started_at: datetime
    elapsed_seconds: int


class TimerStopOut(BaseModel):
    kind: Literal["ticket", "internal"]
    id: int
    minutes: int


class TimesheetEntryOut(BaseModel):
    kind: Literal["ticket", "internal"]
    id: int
    work_date: date
    label: str
    detail: str | None
    ticket_id: int | None
    minutes_actual: int
    minutes_billable: int
    billable: bool
    note: str | None
    invoiced: bool


class TimesheetDayOut(BaseModel):
    date: date
    minutes: int
    billable_minutes: int


class TimesheetOut(BaseModel):
    status: Literal["open", "submitted", "approved", "returned"]
    return_reason: str | None
    user_id: int
    user_name: str
    week_start: date
    week_end: date
    total_minutes: int
    billable_minutes: int
    internal_minutes: int
    days: list[TimesheetDayOut]
    entries: list[TimesheetEntryOut]


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


class CannedIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=10000)

    @field_validator("body")
    @classmethod
    def _body_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Body cannot be blank")
        return v


class CannedPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    body: str | None = Field(default=None, min_length=1, max_length=10000)

    @field_validator("body")
    @classmethod
    def _body_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Body cannot be blank")
        return v


class CannedOut(LookupOut):
    body: str


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


class TicketStatusIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    behavior: TicketStatus  # fixed once created: it decides SLA pausing and reopening
    position: int | None = Field(default=None, ge=0, le=10_000)


class TicketStatusPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    position: int | None = Field(default=None, ge=0, le=10_000)


class TicketStatusOut(LookupOut):
    behavior: TicketStatus
    position: int


CustomFieldType = Literal["text", "number", "date", "dropdown", "checkbox"]


class CustomFieldIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    field_type: CustomFieldType  # fixed once created
    options: list[str] | None = None  # dropdown only
    required: bool = False
    client_visible: bool = False  # shown to the client in the portal
    position: int | None = Field(default=None, ge=0, le=10_000)


class CustomFieldPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    options: list[str] | None = None
    required: bool | None = None
    client_visible: bool | None = None
    position: int | None = Field(default=None, ge=0, le=10_000)


class CustomFieldOut(LookupOut):
    ticket_type_id: int
    field_type: CustomFieldType
    options: list[str] | None
    required: bool
    client_visible: bool
    position: int


class TicketFieldOut(BaseModel):
    field_id: int
    name: str
    field_type: CustomFieldType
    options: list[str] | None
    required: bool
    client_visible: bool
    value: Any = None


LinkRelation = Literal["related", "duplicate_of", "has_duplicate", "parent", "child"]


class TicketLinkIn(BaseModel):
    relation: LinkRelation  # what the OTHER ticket is to this one
    other_number: int = Field(ge=1)  # the other ticket's number


class TicketLinkOut(BaseModel):
    id: int
    relation: LinkRelation
    ticket_id: int
    number: int
    subject: str
    status: TicketStatus
    status_name: str
    created_at: datetime


class CloseDuplicateIn(BaseModel):
    original_number: int = Field(ge=1)


class CsatRespondIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class CsatRespondOut(BaseModel):
    ticket_number: int


class CsatOut(BaseModel):
    sent_to: str
    requested_at: datetime
    rating: int | None
    comment: str | None
    responded_at: datetime | None


class CsatSummaryOut(BaseModel):
    days: int
    requested: int
    responses: int
    average: float | None
    distribution: dict[str, int]  # "1".."5" -> count


class HolidayIn(BaseModel):
    on_date: date
    name: str = Field(min_length=1, max_length=100)
    # Both null = closed all day. Both set = shortened hours (minutes from midnight).
    open_minute: int | None = Field(default=None, ge=0, le=1439)
    close_minute: int | None = Field(default=None, ge=1, le=1440)

    @model_validator(mode="after")
    def _hours(self):
        if not self.name.strip():
            raise ValueError("Name cannot be blank")
        if (self.open_minute is None) != (self.close_minute is None):
            raise ValueError("Give both opening and closing minutes, or neither (closed all day)")
        if self.open_minute is not None and self.open_minute >= self.close_minute:
            raise ValueError("Opening must be before closing")
        return self


class HolidayOut(ORM):
    id: int
    on_date: date
    name: str
    open_minute: int | None
    close_minute: int | None


class SettingsOut(ORM):
    auto_ack_enabled: bool
    auto_ack_subject: str
    auto_ack_body: str
    escalation_email: str | None
    escalation_bump_priority: bool
    csat_enabled: bool
    mileage_rate_cents: int
    portal_enabled: bool
    notify_staff: bool
    statement_subject: str
    statement_body: str
    invoice_email_subject: str
    invoice_email_body: str
    auto_prepare_invoice_emails: bool
    auto_prepare_reminders: bool
    auto_prepare_statements: bool
    reminder_min_gap_days: int
    company_name: str | None
    company_address: str | None
    invoice_footer: str | None
    timezone: str
    business_days: list[int]
    business_start_minute: int
    business_end_minute: int
    billing_increment_minutes: int
    sla_at_risk_percent: int


class SettingsPatch(BaseModel):
    auto_ack_enabled: bool | None = None
    auto_ack_subject: str | None = Field(default=None, min_length=1, max_length=500)
    auto_ack_body: str | None = Field(default=None, min_length=1, max_length=10_000)
    # An empty string clears the address (None means "leave unchanged", like every other field).
    escalation_email: str | None = Field(default=None, max_length=320)
    escalation_bump_priority: bool | None = None
    csat_enabled: bool | None = None
    mileage_rate_cents: int | None = Field(default=None, ge=0, le=10_000)
    portal_enabled: bool | None = None
    notify_staff: bool | None = None
    statement_subject: str | None = Field(default=None, min_length=1, max_length=500)
    statement_body: str | None = Field(default=None, min_length=1, max_length=10_000)
    invoice_email_subject: str | None = Field(default=None, min_length=1, max_length=500)
    invoice_email_body: str | None = Field(default=None, min_length=1, max_length=10_000)
    auto_prepare_invoice_emails: bool | None = None
    auto_prepare_reminders: bool | None = None
    auto_prepare_statements: bool | None = None
    reminder_min_gap_days: int | None = Field(default=None, ge=0, le=90)
    company_name: str | None = Field(default=None, max_length=200)
    company_address: str | None = Field(default=None, max_length=1000)
    invoice_footer: str | None = Field(default=None, max_length=2000)
    timezone: str | None = None
    business_days: list[int] | None = None
    business_start_minute: int | None = None
    business_end_minute: int | None = None
    billing_increment_minutes: int | None = Field(default=None, ge=1, le=240)
    sla_at_risk_percent: int | None = Field(default=None, ge=0, le=100)

    @field_validator("escalation_email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return v
        v = v.strip()
        if " " in v or v.count("@") != 1 or "." not in v.split("@")[1] or v.startswith("@"):
            raise ValueError("Enter a valid email address")
        return v


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


# ---------------------------------------------------------------------------------------
# Phase 3: contracts and invoicing (money is integer cents; quantities are Decimal strings)
# ---------------------------------------------------------------------------------------
from decimal import Decimal  # noqa: E402

AgreementType = Literal["per_user", "per_device", "flat"]
InvoiceStatus = Literal["draft", "final", "void"]
RunStatus = Literal["draft", "reviewed", "finalized", "cancelled"]
LineKind = Literal["time", "product", "agreement", "manual", "proration"]
Cents = int


class WorkTypeBillingOut(ORM):
    id: int
    name: str
    rate_cents: int | None
    taxable: bool
    archived_at: datetime | None


class WorkTypeBillingPatch(BaseModel):
    rate_cents: int | None = Field(default=None, ge=0, le=100_000_00)
    taxable: bool | None = None


class OrgRateIn(BaseModel):
    rate_cents: int = Field(ge=0, le=100_000_00)


class OrgRateOut(ORM):
    work_type_id: int
    rate_cents: int


class OrgBillingOut(BaseModel):
    payment_terms_days: int
    tax_rate_bp: int
    do_not_remind: bool
    rates: list[OrgRateOut]


class OrgBillingPatch(BaseModel):
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    tax_rate_bp: int | None = Field(default=None, ge=0, le=10000, description="825 = 8.25%")
    do_not_remind: bool | None = Field(
        default=None, description="true = never prepare or send payment reminders for this client"
    )


class ProductIn(BaseModel):
    sku: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    unit_price_cents: int = Field(ge=0, le=1_000_000_00)
    cost_cents: int | None = Field(default=None, ge=0, le=1_000_000_00)
    taxable: bool = True


class ProductPatch(BaseModel):
    sku: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    unit_price_cents: int | None = Field(default=None, ge=0, le=1_000_000_00)
    cost_cents: int | None = Field(default=None, ge=0, le=1_000_000_00)
    taxable: bool | None = None


class ProductOut(ORM):
    id: int
    sku: str | None
    name: str
    description: str | None
    unit_price_cents: int
    cost_cents: int | None
    taxable: bool
    archived_at: datetime | None


class AgreementIn(BaseModel):
    organization_id: int
    name: str = Field(min_length=1, max_length=200)
    type: AgreementType
    unit_price_cents: int = Field(ge=0, le=1_000_000_00)
    quantity: int = Field(default=1, ge=0, le=100_000)
    taxable: bool = False
    start_date: date
    end_date: date | None = None
    notes: str | None = None


class AgreementPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: AgreementType | None = None
    unit_price_cents: int | None = Field(default=None, ge=0, le=1_000_000_00)
    quantity: int | None = Field(default=None, ge=0, le=100_000)
    taxable: bool | None = None
    start_date: date | None = None
    end_date: date | None = None
    notes: str | None = None
    reason: str | None = Field(default=None, max_length=500, description="Why the quantity changed")


class AgreementOut(ORM):
    id: int
    organization_id: int
    organization_name: str
    name: str
    type: AgreementType
    unit_price_cents: int
    quantity: int
    taxable: bool
    start_date: date
    end_date: date | None
    notes: str | None
    monthly_amount_cents: int  # unit price x quantity, before tax


class QuantityLogOut(ORM):
    id: int
    old_quantity: int | None
    new_quantity: int
    reason: str | None
    changed_by: int | None
    changed_at: datetime


class DeviceCountOut(BaseModel):
    ninjaone_devices: int
    agreement_quantity: int
    differs: bool


class ChargeIn(BaseModel):
    organization_id: int
    product_id: int | None = None
    ticket_id: int | None = None
    description: str | None = Field(default=None, max_length=500)
    quantity: Decimal = Field(default=Decimal(1), gt=0, le=Decimal(100000), decimal_places=4)
    unit_price_cents: int | None = Field(default=None, ge=0, le=1_000_000_00)
    taxable: bool | None = None
    charged_on: date | None = None


class ChargeOut(ORM):
    id: int
    organization_id: int
    product_id: int | None
    ticket_id: int | None
    description: str
    quantity: Decimal
    unit_price_cents: int
    taxable: bool
    charged_on: date
    invoice_line_id: int | None
    voided_at: datetime | None


class LineOut(ORM):
    id: int
    invoice_id: int
    position: int
    kind: LineKind
    description: str
    quantity: Decimal
    unit_price_cents: int
    amount_cents: int
    tax_rate_bp: int
    tax_cents: int
    agreement_id: int | None
    period_start: date | None


class LineIn(BaseModel):
    description: str = Field(min_length=1, max_length=1000)
    quantity: Decimal = Field(
        default=Decimal(1), decimal_places=4, ge=Decimal(-100000), le=Decimal(100000)
    )
    unit_price_cents: int = Field(
        ge=-1_000_000_00, le=1_000_000_00, description="Negative = credit"
    )
    taxable: bool = False


class LinePatch(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=1000)
    quantity: Decimal | None = Field(
        default=None, decimal_places=4, ge=Decimal(-100000), le=Decimal(100000)
    )
    unit_price_cents: int | None = Field(default=None, ge=-1_000_000_00, le=1_000_000_00)
    tax_rate_bp: int | None = Field(default=None, ge=0, le=10000)


class InvoiceOut(BaseModel):
    id: int
    number: str | None
    organization_id: int
    organization_name: str
    status: InvoiceStatus
    billing_run_id: int | None
    period_start: date | None
    period_end: date | None
    invoice_date: date | None
    due_date: date | None
    terms_days: int | None
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    memo: str | None
    warnings: list[str]
    void_reason: str | None
    created_at: datetime
    finalized_at: datetime | None
    voided_at: datetime | None
    # payment state: only meaningful for finalized invoices (None otherwise)
    paid_cents: int | None = None
    written_off_cents: int | None = None
    balance_cents: int | None = None
    payment_status: "PaymentStatus | None" = None
    is_overdue: bool = False
    days_past_due: int = 0


class InvoiceDetailOut(InvoiceOut):
    lines: list[LineOut]
    payments: "list[InvoicePaymentLine]" = Field(default_factory=list)
    write_offs: "list[WriteOffOut]" = Field(default_factory=list)


class InvoiceIn(BaseModel):
    organization_id: int
    memo: str | None = None
    include_unbilled: bool = True  # pull in uninvoiced billable time and product charges


class InvoicePatch(BaseModel):
    memo: str | None = None


class FinalizeIn(BaseModel):
    invoice_date: date | None = Field(default=None, description="Defaults to today")


class VoidIn(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class RunIn(BaseModel):
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM")


class RunOut(BaseModel):
    id: int
    period_start: date
    period_end: date
    status: RunStatus
    created_at: datetime
    reviewed_at: datetime | None
    finalized_at: datetime | None
    invoice_count: int
    total_cents: int
    warnings: list[str]


class RunDetailOut(RunOut):
    invoices: list[InvoiceOut]


# ---------------------------------------------------------------------------------------
# Payment tracking
# ---------------------------------------------------------------------------------------
PaymentMethod = Literal["check", "ach", "card", "cash", "other"]
PaymentStatus = Literal["unpaid", "partial", "paid", "written_off"]


class ApplyIn(BaseModel):
    invoice_id: int
    amount_cents: int = Field(gt=0, le=1_000_000_000_00)


class PaymentIn(BaseModel):
    organization_id: int
    amount_cents: int = Field(gt=0, le=1_000_000_000_00)
    received_on: date | None = Field(default=None, description="Defaults to today")
    method: PaymentMethod
    reference: str | None = Field(
        default=None, max_length=200, description="Check number, ACH id..."
    )
    notes: str | None = None
    applications: list[ApplyIn] = Field(default_factory=list, description="Invoices this pays")


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class ApplicationOut(ORM):
    id: int
    payment_id: int
    invoice_id: int
    amount_cents: int
    created_at: datetime
    voided_at: datetime | None
    void_reason: str | None


class PaymentOut(BaseModel):
    id: int
    organization_id: int
    organization_name: str
    amount_cents: int
    received_on: date
    method: PaymentMethod
    reference: str | None
    notes: str | None
    status: Literal["active", "void"]
    applied_cents: int
    unapplied_cents: int  # credit still available to apply (0 for voided payments)
    void_reason: str | None
    voided_at: datetime | None
    created_at: datetime


class PaymentDetailOut(PaymentOut):
    applications: list[ApplicationOut]


class WriteOffIn(BaseModel):
    amount_cents: int | None = Field(
        default=None, gt=0, description="Defaults to the whole balance"
    )
    reason: str = Field(min_length=3, max_length=1000)


class WriteOffOut(ORM):
    id: int
    invoice_id: int
    amount_cents: int
    reason: str
    created_at: datetime
    voided_at: datetime | None
    void_reason: str | None


class InvoicePaymentLine(BaseModel):
    application_id: int
    payment_id: int
    amount_cents: int
    received_on: date
    method: PaymentMethod
    reference: str | None
    voided_at: datetime | None
    void_reason: str | None


class AgingRow(BaseModel):
    organization_id: int
    organization_name: str
    current_cents: int  # not yet due
    d1_30_cents: int
    d31_60_cents: int
    d61_90_cents: int
    d90_plus_cents: int
    total_open_cents: int
    credit_cents: int  # unapplied payments on account
    open_invoice_count: int
    overdue_invoice_count: int
    oldest_days_past_due: int


class ReceivablesOut(BaseModel):
    as_of: date
    rows: list[AgingRow]
    totals: AgingRow


# resolve the forward references used by the invoice models above
InvoiceOut.model_rebuild()
InvoiceDetailOut.model_rebuild()
RunDetailOut.model_rebuild()


# ---------------------------------------------------------------------------------------
# Statements and payment reminders
# ---------------------------------------------------------------------------------------
NoticeStatus = Literal["pending", "sent", "dismissed", "expired"]


class ReminderStageOut(ORM):
    id: int
    position: int
    name: str
    days_past_due: int
    subject: str
    body: str
    enabled: bool


class ReminderStagePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    days_past_due: int | None = Field(default=None, ge=0, le=365)
    subject: str | None = Field(default=None, min_length=1, max_length=500)
    body: str | None = Field(default=None, min_length=1, max_length=10_000)
    enabled: bool | None = None


class StatementOut(BaseModel):
    id: int
    organization_id: int
    as_of: date
    created_at: datetime
    total_due_cents: int
    overdue_cents: int
    credit_cents: int
    invoice_count: int
    snapshot: dict


class NoticeInvoiceOut(BaseModel):
    invoice_id: int
    number: str | None
    due_date: date | None
    balance_cents: int
    days_past_due: int
    new_stage: bool  # this invoice reaches a reminder stage with this notice


class NoticeOut(BaseModel):
    id: int
    kind: Literal["reminder", "statement", "invoice"]
    organization_id: int
    organization_name: str
    status: NoticeStatus
    manual: bool
    stage_name: str | None
    subject: str
    body_text: str
    to_emails: list[str]
    blocked_reason: str | None
    statement_id: int | None
    stale: bool  # numbers changed since it was prepared: refresh before sending
    total_due_cents: int
    created_at: datetime
    decided_at: datetime | None
    dismiss_reason: str | None
    email_status: str | None  # pending | sent | failed once approved
    invoices: list[NoticeInvoiceOut]


class NoticePatch(BaseModel):
    subject: str | None = Field(default=None, max_length=998)
    body_text: str | None = Field(default=None, max_length=20_000)


class NoticeSendIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)


class SendResult(BaseModel):
    id: int
    ok: bool
    error: str | None = None


class PrepareOut(BaseModel):
    created: int
    notice_ids: list[int]


class ReminderIn(BaseModel):
    invoice_ids: list[int] | None = Field(
        default=None, description="Default: all of the client's overdue invoices"
    )


class EmailStatementIn(BaseModel):
    send: bool = Field(default=False, description="true = approve and queue it immediately")


# ---- reports ----
class RevenueRow(BaseModel):
    invoices: int
    time_cents: int
    product_cents: int
    agreement_cents: int
    manual_cents: int
    subtotal_cents: int
    tax_cents: int
    total_cents: int


class RevenueClient(RevenueRow):
    organization_id: int
    organization_name: str


class RevenueMonth(RevenueRow):
    month: date


class RevenueOut(BaseModel):
    start: date
    end: date
    clients: list[RevenueClient]
    months: list[RevenueMonth]
    totals: RevenueRow


class UnbilledRow(BaseModel):
    organization_id: int
    organization_name: str
    time_entries: int
    billable_minutes: int
    time_value_cents: int
    unpriced_minutes: int
    oldest_work_date: date | None
    charges: int
    charges_cents: int
    expenses: int
    expenses_cents: int
    total_cents: int


class UnbilledTotals(BaseModel):
    time_entries: int
    billable_minutes: int
    time_value_cents: int
    unpriced_minutes: int
    charges: int
    charges_cents: int
    expenses: int
    expenses_cents: int
    total_cents: int


class UnbilledOut(BaseModel):
    through: date
    rows: list[UnbilledRow]
    totals: UnbilledTotals


class RecurringMonth(BaseModel):
    month: date
    contracted_cents: int
    agreements: int
    clients: int
    invoiced_cents: int


class RecurringOut(BaseModel):
    months: list[RecurringMonth]


# ---- client portal ----
class PortalLinkIn(BaseModel):
    email: EmailStr


class PortalVerifyIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class PortalMeOut(BaseModel):
    contact_name: str
    email: str | None
    organization_name: str
    company_name: str | None
    can_see_billing: bool
    can_see_all_tickets: bool
    can_see_devices: bool = False


class PortalNoticeOut(BaseModel):
    detail: str


class PortalInvoiceOut(BaseModel):
    id: int
    number: str
    invoice_date: date
    due_date: date
    total_cents: int
    paid_cents: int
    balance_cents: int
    status: Literal["paid", "partial", "unpaid", "written_off"]
    is_overdue: bool
    days_past_due: int


class PortalLineOut(BaseModel):
    description: str
    quantity: str
    unit_price_cents: int
    amount_cents: int
    tax_cents: int


class PortalInvoiceDetail(PortalInvoiceOut):
    subtotal_cents: int
    tax_cents: int
    lines: list[PortalLineOut]


class PortalTicketOut(BaseModel):
    id: int
    number: int
    subject: str
    status: str
    status_name: str
    created_at: datetime
    updated_at: datetime
    mine: bool


class PortalNoteOut(BaseModel):
    id: int
    author: str
    from_you: bool
    from_support: bool
    body: str
    created_at: datetime


class PortalFieldOut(BaseModel):
    name: str
    value: Any


class PortalTicketDetail(PortalTicketOut):
    description: str | None
    custom_fields: list[PortalFieldOut]
    notes: list[PortalNoteOut]


class PortalTicketIn(BaseModel):
    subject: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=1, max_length=10_000)


class PortalReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=10_000)


class WeekIn(BaseModel):
    week_start: date


class WeekUserIn(BaseModel):
    user_id: int
    week_start: date


class WeekReturnIn(WeekUserIn):
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Say why the week is being returned")
        return v


class TimesheetStatusOut(ORM):
    user_id: int
    week_start: date
    status: Literal["submitted", "approved", "returned"]
    submitted_at: datetime | None
    approved_at: datetime | None
    return_reason: str | None


class TimesheetQueueRow(BaseModel):
    id: int
    user_id: int
    user_name: str
    week_start: date
    status: Literal["submitted", "approved", "returned"]
    submitted_at: datetime | None
    approved_at: datetime | None
    return_reason: str | None
    total_minutes: int


# ---- expenses ----
class ExpenseIn(BaseModel):
    kind: Literal["expense", "mileage"] = "expense"
    expense_date: date | None = None
    category_id: int | None = None  # required for kind=expense
    description: str = Field(min_length=1, max_length=2000)
    amount_cents: int | None = Field(default=None, gt=0, le=100_000_000)  # expense only
    miles: Decimal | None = Field(default=None, gt=0, le=10_000, decimal_places=2)  # mileage only
    reimbursable: bool = False
    billable: bool = False
    taxable: bool = False
    markup_bp: int = Field(default=0, ge=0, le=100_000)
    organization_id: int | None = None
    ticket_id: int | None = None
    user_id: int | None = None  # admin only; defaults to the caller


class ExpensePatch(BaseModel):
    expense_date: date | None = None
    category_id: int | None = None
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    amount_cents: int | None = Field(default=None, gt=0, le=100_000_000)
    miles: Decimal | None = Field(default=None, gt=0, le=10_000, decimal_places=2)
    reimbursable: bool | None = None
    billable: bool | None = None
    taxable: bool | None = None
    markup_bp: int | None = Field(default=None, ge=0, le=100_000)
    organization_id: int | None = None
    ticket_id: int | None = None
    clear_client: bool = False  # explicitly remove the client (and ticket)


class ReceiptOut(ORM):
    id: int
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class ExpenseOut(BaseModel):
    id: int
    user_id: int
    user_name: str
    expense_date: date
    kind: Literal["expense", "mileage"]
    category_id: int | None
    category_name: str | None
    description: str
    miles: Decimal | None
    mileage_rate_cents: int | None
    amount_cents: int
    reimbursable: bool
    billable: bool
    taxable: bool
    markup_bp: int
    client_price_cents: int
    organization_id: int | None
    organization_name: str | None
    ticket_id: int | None
    invoiced: bool
    voided_at: datetime | None
    receipts: list[ReceiptOut]
