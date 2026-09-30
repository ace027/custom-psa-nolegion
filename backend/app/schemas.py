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
    company_name: str | None = Field(default=None, max_length=200)
    company_address: str | None = Field(default=None, max_length=1000)
    invoice_footer: str | None = Field(default=None, max_length=2000)
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


# ---------------------------------------------------------------------------------------
# Phase 3: contracts and invoicing (money is integer cents; quantities are Decimal strings)
# ---------------------------------------------------------------------------------------
from decimal import Decimal  # noqa: E402

AgreementType = Literal["per_user", "per_device", "flat"]
InvoiceStatus = Literal["draft", "final", "void"]
RunStatus = Literal["draft", "reviewed", "finalized", "cancelled"]
LineKind = Literal["time", "product", "agreement", "manual"]
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
    rates: list[OrgRateOut]


class OrgBillingPatch(BaseModel):
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    tax_rate_bp: int | None = Field(default=None, ge=0, le=10000, description="825 = 8.25%")


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
