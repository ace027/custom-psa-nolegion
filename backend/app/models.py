from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Alembic migrations are the source of truth for schema, including RLS policies and
    expression/partial indexes, which are deliberately declared only in the migration."""


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    billing_address: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_terms_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="30")
    do_not_remind: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    tax_rate_bp: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class Site(TimestampMixin, Base):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address_line1: Mapped[str | None] = mapped_column(String(200))
    address_line2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Contact(TimestampMixin, Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    title: Mapped[str | None] = mapped_column(String(100))
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_billing_contact: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class User(TimestampMixin, Base):
    """Staff user. Roles are assigned in the PSA, not taken from Entra groups."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    entra_oid: Mapped[str | None] = mapped_column(String(64), unique=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notify_assigned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    notify_sla: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    notify_reply: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class Session(Base):
    """Server-side login session. Only a hash of the cookie token is stored."""

    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))


class AuditLog(Base):
    """Append-only. The app DB role has INSERT and SELECT only."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)  # user|system|anonymous
    actor_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[int | None] = mapped_column(BigInteger)
    organization_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    detail: Mapped[dict | None] = mapped_column(JSONB)
    request_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)


# ---------------------------------------------------------------------------------------
# Phase 2: ticketing
# ---------------------------------------------------------------------------------------

STATUSES = ("new", "open", "waiting_on_customer", "resolved", "closed")
CLOCK_STOPPED = frozenset({"waiting_on_customer", "resolved", "closed"})


class _Lookup(TimestampMixin):
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Queue(_Lookup, Base):
    __tablename__ = "queues"
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class Category(_Lookup, Base):
    __tablename__ = "categories"


class Priority(_Lookup, Base):
    __tablename__ = "priorities"
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    first_response_minutes: Mapped[int | None] = mapped_column(Integer)
    resolution_minutes: Mapped[int | None] = mapped_column(Integer)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class WorkType(_Lookup, Base):
    __tablename__ = "work_types"
    rate_cents: Mapped[int | None] = mapped_column(BigInteger)  # hourly; NULL = cannot be billed
    taxable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class Settings(Base):
    """Single-row table (id = 1)."""

    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    business_days: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False)
    business_start_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    business_end_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    billing_increment_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    sla_at_risk_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    company_name: Mapped[str | None] = mapped_column(Text)
    company_address: Mapped[str | None] = mapped_column(Text)
    invoice_footer: Mapped[str | None] = mapped_column(Text)
    statement_subject: Mapped[str] = mapped_column(Text, nullable=False)
    statement_body: Mapped[str] = mapped_column(Text, nullable=False)
    notify_staff: Mapped[bool] = mapped_column(Boolean, nullable=False)
    invoice_email_subject: Mapped[str] = mapped_column(Text, nullable=False)
    invoice_email_body: Mapped[str] = mapped_column(Text, nullable=False)
    auto_prepare_invoice_emails: Mapped[bool] = mapped_column(Boolean, nullable=False)
    auto_prepare_reminders: Mapped[bool] = mapped_column(Boolean, nullable=False)
    auto_prepare_statements: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reminder_min_gap_days: Mapped[int] = mapped_column(Integer, nullable=False)
    reminders_prepared_on: Mapped[date | None] = mapped_column(Date)
    statements_prepared_month: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class MailboxStatus(Base):
    __tablename__ = "mailbox_status"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    mailbox: Mapped[str | None] = mapped_column(String(320))
    worker_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    messages_ingested: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")


class Ticket(TimestampMixin, Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    number: Mapped[int] = mapped_column(
        BigInteger, server_default=text("nextval('ticket_number_seq')")
    )
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"))
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id"))
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id"))
    queue_id: Mapped[int] = mapped_column(ForeignKey("queues.id"), nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    priority_id: Mapped[int] = mapped_column(ForeignKey("priorities.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="new")
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(10), nullable=False, server_default="ui")
    requester_email: Mapped[str | None] = mapped_column(String(320))
    sla_first_response_due: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_resolution_due: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_paused_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    organization: Mapped[Organization | None] = relationship(lazy="joined")
    contact: Mapped[Contact | None] = relationship(lazy="joined")
    queue: Mapped[Queue] = relationship(lazy="joined")
    category: Mapped[Category | None] = relationship(lazy="joined")
    priority: Mapped[Priority] = relationship(lazy="joined")
    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id], lazy="joined")


class EmailMessage(Base):
    __tablename__ = "email_messages"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    direction: Mapped[str] = mapped_column(String(3), nullable=False)
    graph_message_id: Mapped[str | None] = mapped_column(String(400), unique=True)
    internet_message_id: Mapped[str | None] = mapped_column(String(998))
    in_reply_to: Mapped[str | None] = mapped_column(String(998))
    conversation_id: Mapped[str | None] = mapped_column(String(400))
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    organization_id: Mapped[int | None] = mapped_column(BigInteger)
    from_email: Mapped[str | None] = mapped_column(String(320))
    to_emails: Mapped[list | None] = mapped_column(JSONB)
    subject: Mapped[str | None] = mapped_column(String(998))
    body_text: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingest_status: Mapped[str | None] = mapped_column(String(20))
    ingest_detail: Mapped[str | None] = mapped_column(Text)
    send_status: Mapped[str | None] = mapped_column(String(10))
    send_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    send_error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TicketNote(Base):
    """Immutable once written (the app role has no UPDATE except organization_id on triage)."""

    __tablename__ = "ticket_notes"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    organization_id: Mapped[int | None] = mapped_column(BigInteger)
    author_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    author_email: Mapped[str | None] = mapped_column(String(320))
    visibility: Mapped[str] = mapped_column(String(10), nullable=False)
    source: Mapped[str] = mapped_column(String(10), nullable=False, server_default="ui")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    email_message_id: Mapped[int | None] = mapped_column(ForeignKey("email_messages.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    author: Mapped[User | None] = relationship(lazy="joined")


class TimeEntry(TimestampMixin, Base):
    __tablename__ = "time_entries"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    organization_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    work_type_id: Mapped[int] = mapped_column(ForeignKey("work_types.id"), nullable=False)
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    minutes_actual: Mapped[int] = mapped_column(Integer, nullable=False)
    minutes_billable: Mapped[int] = mapped_column(Integer, nullable=False)
    billable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    note: Mapped[str | None] = mapped_column(Text)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invoice_line_id: Mapped[int | None] = mapped_column(ForeignKey("invoice_lines.id"))


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    email_message_id: Mapped[int] = mapped_column(ForeignKey("email_messages.id"), nullable=False)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    organization_id: Mapped[int | None] = mapped_column(BigInteger)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(200))
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------------------
# Phase 3: contracts and invoicing. Money is ALWAYS integer cents.
# ---------------------------------------------------------------------------------------


class OrgWorkTypeRate(TimestampMixin, Base):
    __tablename__ = "org_work_type_rates"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    work_type_id: Mapped[int] = mapped_column(ForeignKey("work_types.id"), nullable=False)
    rate_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    sku: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cost_cents: Mapped[int | None] = mapped_column(BigInteger)
    taxable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Agreement(TimestampMixin, Base):
    __tablename__ = "agreements"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)  # per_user|per_device|flat
    unit_price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    taxable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    organization: Mapped[Organization] = relationship(lazy="joined")


class AgreementQuantityLog(Base):
    __tablename__ = "agreement_quantity_log"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    agreement_id: Mapped[int] = mapped_column(ForeignKey("agreements.id"), nullable=False)
    organization_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    old_quantity: Mapped[int | None] = mapped_column(Integer)
    new_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BillingRun(Base):
    __tablename__ = "billing_runs"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default="draft")
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalized_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Invoice(TimestampMixin, Base):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    number: Mapped[str | None] = mapped_column(String(20), unique=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="draft")
    billing_run_id: Mapped[int | None] = mapped_column(ForeignKey("billing_runs.id"))
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    invoice_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    terms_days: Mapped[int | None] = mapped_column(Integer)
    subtotal_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    tax_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    total_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    memo: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    bill_to_name: Mapped[str | None] = mapped_column(String(200))
    bill_to_address: Mapped[str | None] = mapped_column(Text)
    seller_name: Mapped[str | None] = mapped_column(Text)
    seller_address: Mapped[str | None] = mapped_column(Text)
    footer: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    finalized_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(Text)
    organization: Mapped[Organization] = relationship(lazy="joined")


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    organization_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_rate_bp: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    tax_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    agreement_id: Mapped[int | None] = mapped_column(ForeignKey("agreements.id"))
    period_start: Mapped[date | None] = mapped_column(Date)
    voided: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProductCharge(Base):
    """A one-off product/hardware/license sale waiting to be invoiced."""

    __tablename__ = "product_charges"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    taxable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    charged_on: Mapped[date] = mapped_column(Date, nullable=False)
    invoice_line_id: Mapped[int | None] = mapped_column(ForeignKey("invoice_lines.id"))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InvoiceCounter(Base):
    __tablename__ = "invoice_counters"
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


# ---------------------------------------------------------------------------------------
# Payment tracking. An invoice's balance is DERIVED:
#   total - active applications - active write-offs   (the frozen invoice is never touched)
# ---------------------------------------------------------------------------------------
PAYMENT_METHODS = ("check", "ach", "card", "cash", "other")


class Payment(Base):
    """Money received from a client. Immutable except for being voided (with a reason)."""

    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    received_on: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(6), nullable=False, server_default="active")
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    void_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    organization: Mapped[Organization] = relationship(lazy="joined")


class PaymentApplication(Base):
    __tablename__ = "payment_applications"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), nullable=False)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    organization_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    void_reason: Mapped[str | None] = mapped_column(Text)


class WriteOff(Base):
    __tablename__ = "write_offs"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    organization_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    void_reason: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------------------------------
# Statements and payment reminders
# ---------------------------------------------------------------------------------------


class ReminderStage(Base):
    __tablename__ = "reminder_stages"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    days_past_due: Mapped[int] = mapped_column(Integer, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Statement(Base):
    """A frozen point-in-time account statement (the PDF is rendered from this snapshot)."""

    __tablename__ = "statements"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BillingNotice(Base):
    """An email to a client waiting for a human decision (or the record of that decision)."""

    __tablename__ = "billing_notices"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # reminder | statement | invoice
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"))
    statement_id: Mapped[int | None] = mapped_column(ForeignKey("statements.id"))
    stage_id: Mapped[int | None] = mapped_column(ForeignKey("reminder_stages.id"))
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="pending")
    manual: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    batch_month: Mapped[date | None] = mapped_column(Date)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    to_emails: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    email_message_id: Mapped[int | None] = mapped_column(ForeignKey("email_messages.id"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismiss_reason: Mapped[str | None] = mapped_column(Text)
    organization: Mapped[Organization] = relationship(lazy="joined")
    stage: Mapped[ReminderStage | None] = relationship(lazy="joined")


class BillingNoticeInvoice(Base):
    __tablename__ = "billing_notice_invoices"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    notice_id: Mapped[int] = mapped_column(ForeignKey("billing_notices.id"), nullable=False)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    organization_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stage_id: Mapped[int | None] = mapped_column(ForeignKey("reminder_stages.id"))
    balance_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    days_past_due: Mapped[int] = mapped_column(Integer, nullable=False)


class OutboundAttachment(Base):
    __tablename__ = "outbound_attachments"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    email_message_id: Mapped[int] = mapped_column(ForeignKey("email_messages.id"), nullable=False)
    organization_id: Mapped[int | None] = mapped_column(BigInteger)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StaffNotification(Base):
    """Record that a staff member was emailed about a ticket event (also the once-only guard)."""

    __tablename__ = "staff_notifications"
    __table_args__ = (UniqueConstraint("user_id", "ticket_id", "event", "dedupe_key"),)
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    event: Mapped[str] = mapped_column(String(20), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(100), nullable=False)
    email_message_id: Mapped[int] = mapped_column(ForeignKey("email_messages.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
