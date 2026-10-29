import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
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
    late_fees_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    assets_published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )


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
    portal_access: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    portal_org_tickets: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    portal_assets: Mapped[bool] = mapped_column(
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
    timezone: Mapped[str | None] = mapped_column(String(64))  # None = the Settings timezone


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


class TicketStatus(_Lookup, Base):
    """A named status. `behavior` is one of the five built-in states and decides SLA pause,
    reopen and "open" filters; it cannot be changed after creation."""

    __tablename__ = "ticket_statuses"
    behavior: Mapped[str] = mapped_column(String(30), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class TicketType(_Lookup, Base):
    __tablename__ = "ticket_types"


class CustomField(_Lookup, Base):
    """A field a ticket of one type carries. `field_type` cannot change after creation (stored
    values would stop making sense); values live on the ticket, keyed by this field's id."""

    __tablename__ = "custom_fields"
    ticket_type_id: Mapped[int] = mapped_column(ForeignKey("ticket_types.id"), nullable=False)
    field_type: Mapped[str] = mapped_column(String(10), nullable=False)
    options: Mapped[list | None] = mapped_column(JSONB(none_as_null=True))
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    client_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class CannedResponse(_Lookup, Base):
    """Reusable reply text. Placeholders ({{contact_name}}, {{ticket_number}}...) are filled in by
    the UI when a tech inserts it; the stored text is never client data."""

    __tablename__ = "canned_responses"
    body: Mapped[str] = mapped_column(Text, nullable=False)


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
    # false = time of this type is never drawn from a block agreement ("Not covered by blocks")
    block_covered: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


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
    portal_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    renewal_reminder_days: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, server_default=text("'{90,30}'::integer[]")
    )
    renewal_email: Mapped[str | None] = mapped_column(String(320))
    invoice_email_subject: Mapped[str] = mapped_column(Text, nullable=False)
    invoice_email_body: Mapped[str] = mapped_column(Text, nullable=False)
    auto_prepare_invoice_emails: Mapped[bool] = mapped_column(Boolean, nullable=False)
    auto_prepare_reminders: Mapped[bool] = mapped_column(Boolean, nullable=False)
    auto_prepare_statements: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reminder_min_gap_days: Mapped[int] = mapped_column(Integer, nullable=False)
    late_fee_percent_bp: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    late_fee_flat_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    late_fee_grace_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="15")
    late_fee_max_per_invoice: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    outlook_sync_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    appointment_emails_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    reminders_prepared_on: Mapped[date | None] = mapped_column(Date)
    statements_prepared_month: Mapped[date | None] = mapped_column(Date)
    auto_ack_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    auto_ack_subject: Mapped[str] = mapped_column(Text, nullable=False)
    auto_ack_body: Mapped[str] = mapped_column(Text, nullable=False)
    escalation_email: Mapped[str | None] = mapped_column(String(320))
    escalation_bump_priority: Mapped[bool] = mapped_column(Boolean, nullable=False)
    csat_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    mileage_rate_cents: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    default_markup_bp: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Holiday(Base):
    """A day the business is closed (both hours null) or open shorter hours (minutes from midnight).
    Only matters on normal business days."""

    __tablename__ = "holidays"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    on_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    open_minute: Mapped[int | None] = mapped_column(Integer)
    close_minute: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---- scheduling ----
APPOINTMENT_STATUSES = ("scheduled", "cancelled")
TIME_OFF_STATUSES = ("pending", "approved", "rejected", "cancelled")


class UserWorkHours(Base):
    """One working window per weekday (0 = Monday), minutes from local midnight in the user's
    timezone. A user with no rows works the default business hours from Settings."""

    __tablename__ = "user_work_hours"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_user_work_hours_weekday"),
        CheckConstraint(
            "0 <= start_minute AND start_minute < end_minute AND end_minute <= 1440",
            name="ck_user_work_hours_range",
        ),
        UniqueConstraint("user_id", "weekday", name="uq_user_work_hours_day"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    weekday: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    end_minute: Mapped[int] = mapped_column(Integer, nullable=False)


class UserTimeOff(TimestampMixin, Base):
    """A time-off request. Never deleted: cancelled or rejected instead."""

    __tablename__ = "user_time_off"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected','cancelled')",
            name="ck_user_time_off_status",
        ),
        CheckConstraint(
            "ends_at > starts_at AND ends_at - starts_at <= interval '366 days'",
            name="ck_user_time_off_range",
        ),
        CheckConstraint(
            "status NOT IN ('approved','rejected') "
            "OR (decided_by IS NOT NULL AND decided_at IS NOT NULL)",
            name="ck_user_time_off_decided",
        ),
        Index("ix_user_time_off_user_start", "user_id", "starts_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)


class Appointment(TimestampMixin, Base):
    """A tech booked against a ticket. Client-owned (RLS); organization_id follows the ticket via
    the composite FK. Never deleted: cancelled instead."""

    __tablename__ = "appointments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["ticket_id", "organization_id"],
            ["tickets.id", "tickets.organization_id"],
            name="fk_appointments_ticket_org",
            onupdate="CASCADE",
        ),
        CheckConstraint("status IN ('scheduled','cancelled')", name="ck_appointments_status"),
        CheckConstraint(
            "ends_at > starts_at AND ends_at - starts_at <= interval '24 hours'",
            name="ck_appointments_range",
        ),
        CheckConstraint(
            "(status = 'cancelled') = (cancelled_at IS NOT NULL)",
            name="ck_appointments_cancelled",
        ),
        Index("ix_appointments_tech_start", "tech_id", "starts_at"),
        Index("ix_appointments_ticket", "ticket_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", name="fk_appointments_org"), nullable=False, index=True
    )
    ticket_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tech_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="scheduled")
    notes: Mapped[str | None] = mapped_column(Text)
    client_visible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    notify_client: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    cancel_reason: Mapped[str | None] = mapped_column(Text)


class AppointmentNotice(Base):
    """Queued client email about an appointment. One pending row per appointment. Client-owned
    (RLS)."""

    __tablename__ = "appointment_notices"
    __table_args__ = (
        CheckConstraint(
            "state IN ('pending','sent','skipped')", name="ck_appointment_notices_state"
        ),
        CheckConstraint(
            "kind IS NULL OR kind IN ('booked','moved','cancelled')",
            name="ck_appointment_notices_kind",
        ),
        Index("ix_appointment_notices_due", "state", "send_after"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    appointment_id: Mapped[int] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False
    )
    state: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str | None] = mapped_column(Text)
    send_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    email_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("email_messages.id", ondelete="SET NULL")
    )
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OncallRotation(Base):
    """Weekly on-call rotation (handoff_weekday 0 = Monday). Staff-internal like UserTimeOff: no
    organization_id and no RLS; schedule:read/write guard it."""

    __tablename__ = "oncall_rotations"
    __table_args__ = (
        CheckConstraint("handoff_weekday BETWEEN 0 AND 6", name="ck_oncall_rotations_weekday"),
        CheckConstraint(
            "extract(isodow from anchor_date)::int - 1 = handoff_weekday",
            name="ck_oncall_rotations_anchor",
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    handoff_weekday: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    handoff_time: Mapped[time] = mapped_column(Time, nullable=False)
    anchor_date: Mapped[date] = mapped_column(Date, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OncallMember(Base):
    __tablename__ = "oncall_members"
    __table_args__ = (
        UniqueConstraint("rotation_id", "position", name="uq_oncall_members_position"),
        UniqueConstraint("rotation_id", "user_id", name="uq_oncall_members_user"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    rotation_id: Mapped[int] = mapped_column(
        ForeignKey("oncall_rotations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class OncallOverride(Base):
    __tablename__ = "oncall_overrides"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_oncall_overrides_range"),
        Index("ix_oncall_overrides_rotation", "rotation_id", "starts_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    rotation_id: Mapped[int] = mapped_column(
        ForeignKey("oncall_rotations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AppointmentSync(Base):
    """Outbox row per appointment for the Outlook push. Client-owned (RLS)."""

    __tablename__ = "appointment_sync"
    __table_args__ = (
        CheckConstraint(
            "state IN ('pending','synced','failed','skipped')", name="ck_appointment_sync_state"
        ),
        Index("ix_appointment_sync_due", "state", "next_attempt_at"),
    )
    appointment_id: Mapped[int] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), primary_key=True
    )
    organization_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    desired_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    synced_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    synced_tech_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    graph_event_id: Mapped[str | None] = mapped_column(String(512))
    state: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_error: Mapped[str | None] = mapped_column(String(500))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class BusyBlock(Base):
    """Cached Outlook busy time for a staff user (no client data, no RLS)."""

    __tablename__ = "busy_blocks"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_busy_blocks_range"),
        Index("ix_busy_blocks_user_start", "user_id", "starts_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class CalendarBusyStatus(Base):
    __tablename__ = "calendar_busy_status"
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))


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
    # composite target for appointments' (ticket_id, organization_id) FK
    __table_args__ = (UniqueConstraint("id", "organization_id", name="uq_tickets_id_org"),)

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
    status_id: Mapped[int] = mapped_column(
        ForeignKey("ticket_statuses.id"),
        nullable=False,
        server_default=text("default_status_id('new')"),
    )
    type_id: Mapped[int | None] = mapped_column(ForeignKey("ticket_types.id"))
    custom_values: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(10), nullable=False, server_default="ui")
    requester_email: Mapped[str | None] = mapped_column(String(320))
    sla_first_response_due: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_resolution_due: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_breached_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_paused_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # composite FK (asset_id, organization_id) lives in migration 0027
    asset_id: Mapped[int | None] = mapped_column(BigInteger)
    # composite FK (project_id, organization_id) lives in migration 0029
    project_id: Mapped[int | None] = mapped_column(BigInteger)

    organization: Mapped[Organization | None] = relationship(lazy="joined")
    contact: Mapped[Contact | None] = relationship(lazy="joined")
    project: Mapped["Project | None"] = relationship(
        "Project",
        primaryjoin="Project.id == Ticket.project_id",
        foreign_keys="[Ticket.project_id]",
        lazy="select",
        viewonly=True,
    )
    asset: Mapped["Asset | None"] = relationship(
        "Asset",
        primaryjoin="Asset.id == Ticket.asset_id",
        foreign_keys="[Ticket.asset_id]",
        lazy="selectin",
        viewonly=True,
    )
    queue: Mapped[Queue] = relationship(lazy="joined")
    category: Mapped[Category | None] = relationship(lazy="joined")
    priority: Mapped[Priority] = relationship(lazy="joined")
    status_ref: Mapped[TicketStatus] = relationship(lazy="joined")
    type: Mapped[TicketType | None] = relationship(lazy="joined")
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
    auto_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
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
    # Part of minutes_billable drawn from a block agreement by a billing run (0 = none)
    block_minutes_covered: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class TimeCategory(_Lookup, Base):
    """What internal (non-client) time was spent on: Administration, Training, Paid time off..."""

    __tablename__ = "time_categories"


class InternalTimeEntry(TimestampMixin, Base):
    """Time that belongs to no client or ticket. Never billable; voided, never deleted."""

    __tablename__ = "internal_time_entries"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("time_categories.id"), nullable=False)
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    category: Mapped[TimeCategory] = relationship(lazy="joined")


class Timer(Base):
    """A person's running timer: on a ticket (with a work type) or on an internal category."""

    __tablename__ = "timers"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    work_type_id: Mapped[int | None] = mapped_column(ForeignKey("work_types.id"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("time_categories.id"))
    billable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    note: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Timesheet(TimestampMixin, Base):
    """A person's week, once submitted. No row = the week is still open for edits."""

    __tablename__ = "timesheets"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)  # submitted|approved|returned
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    returned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    return_reason: Mapped[str | None] = mapped_column(Text)


class ExpenseCategory(_Lookup, Base):
    __tablename__ = "expense_categories"


class Expense(TimestampMixin, Base):
    """Money a person spent (or a trip they drove). Reimbursable to them and/or billable to a
    client. Amounts are integer cents; `amount_cents` is the COST, the client price adds markup."""

    __tablename__ = "expenses"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # expense | mileage
    category_id: Mapped[int | None] = mapped_column(ForeignKey("expense_categories.id"))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    miles: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    mileage_rate_cents: Mapped[int | None] = mapped_column(Integer)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reimbursable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    billable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    taxable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    markup_bp: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"))
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    invoice_line_id: Mapped[int | None] = mapped_column(ForeignKey("invoice_lines.id"))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    category: Mapped["ExpenseCategory | None"] = relationship()  # not joined: rows get FOR UPDATE


class ExpenseReceipt(Base):
    __tablename__ = "expense_receipts"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    expense_id: Mapped[int] = mapped_column(ForeignKey("expenses.id"), nullable=False)
    organization_id: Mapped[int | None] = mapped_column(BigInteger)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(300), nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


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
    category: Mapped[str | None] = mapped_column(String(10))  # hardware|software|license|other


class Agreement(TimestampMixin, Base):
    __tablename__ = "agreements"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)  # per_user|per_device|flat|block
    unit_price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    taxable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    # Included minutes per month; set only (and always) for type 'block'
    block_minutes: Mapped[int | None] = mapped_column(Integer)
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
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))
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


class LateFeeApplication(Base):
    """A person-approved late fee: links the overdue invoice to the charge that bills it."""

    __tablename__ = "late_fee_applications"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    charge_id: Mapped[int] = mapped_column(
        ForeignKey("product_charges.id"), nullable=False, unique=True
    )
    days_overdue: Mapped[int] = mapped_column(Integer, nullable=False)
    base_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    percent_bp: Mapped[int] = mapped_column(Integer, nullable=False)
    flat_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fee_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    applied_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CreditMemo(Base):
    """A numbered, immutable credit to a client. Voidable (with a reason), never edited."""

    __tablename__ = "credit_memos"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    number: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    memo_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"))  # what it corrects
    subtotal_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(6), nullable=False, server_default="active")
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    void_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    organization: Mapped[Organization] = relationship(lazy="joined")


class CreditMemoLine(Base):
    __tablename__ = "credit_memo_lines"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    memo_id: Mapped[int] = mapped_column(ForeignKey("credit_memos.id"), nullable=False)
    organization_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_rate_bp: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    tax_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CreditMemoApplication(Base):
    __tablename__ = "credit_memo_applications"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    memo_id: Mapped[int] = mapped_column(ForeignKey("credit_memos.id"), nullable=False)
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


class Refund(Base):
    """Money paid back to a client against a payment (recorded by hand; nothing is sent)."""

    __tablename__ = "refunds"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), nullable=False)
    organization_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    refunded_on: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(200))
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


class ApiKey(Base):
    """A staff-owned API key. Only the SHA-256 of the secret is stored; `prefix` finds the row."""

    __tablename__ = "api_keys"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    prefix: Mapped[str] = mapped_column(String(8), nullable=False, unique=True)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    permissions: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    user: Mapped["User"] = relationship(foreign_keys=[user_id], lazy="joined")


class WebhookEndpoint(Base):
    """An outbound webhook target (generic JSON or Microsoft Teams). `secret` is encrypted."""

    __tablename__ = "webhook_endpoints"
    __table_args__ = (
        CheckConstraint("kind IN ('generic','teams')", name="ck_webhook_endpoints_kind"),
        CheckConstraint(
            "consecutive_failures >= 0", name="ck_webhook_endpoints_consecutive_failures"
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    secret: Mapped[str] = mapped_column(Text, nullable=False)
    events: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WebhookDelivery(Base):
    """One event queued for one endpoint; unique per (endpoint, event), so no duplicates."""

    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        UniqueConstraint("endpoint_id", "event_id", name="uq_webhook_deliveries_event"),
        CheckConstraint(
            "status IN ('pending','delivered','failed')", name="ck_webhook_deliveries_status"
        ),
        CheckConstraint("attempts >= 0", name="ck_webhook_deliveries_attempts"),
        Index("ix_webhook_deliveries_due", "status", "next_attempt_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    endpoint_id: Mapped[int] = mapped_column(ForeignKey("webhook_endpoints.id"), nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(String(300))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    endpoint: Mapped["WebhookEndpoint"] = relationship()


class AutomationRule(Base):
    """A staff-defined trigger / conditions / actions rule."""

    __tablename__ = "automation_rules"
    __table_args__ = (
        CheckConstraint("trigger <> ''", name="ck_automation_rules_trigger"),
        CheckConstraint("fire_count >= 0", name="ck_automation_rules_fire_count"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    trigger: Mapped[str] = mapped_column(String(40), nullable=False)
    conditions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    actions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disabled_reason: Mapped[str | None] = mapped_column(String(200))
    fire_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AutomationRun(Base):
    """One evaluation of a rule against an event; real runs are unique per (rule, event)."""

    __tablename__ = "automation_runs"
    __table_args__ = (
        Index(
            "uq_automation_runs_event",
            "rule_id",
            "event_id",
            unique=True,
            postgresql_where=text("NOT dry_run"),
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("automation_rules.id"), nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    matched: Mapped[bool] = mapped_column(Boolean, nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    trace: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    rule: Mapped["AutomationRule"] = relationship()


class TicketLink(Base):
    """A relationship between two tickets of the same client (see docs/TICKETS_PLAN.md)."""

    __tablename__ = "ticket_links"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    target_ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CsatSurvey(Base):
    """A satisfaction survey sent when a ticket is first resolved. Only the token's hash is
    stored; it answers once and expires."""

    __tablename__ = "csat_surveys"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False, unique=True)
    organization_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    sent_to: Mapped[str] = mapped_column(String(320), nullable=False)
    email_message_id: Mapped[int | None] = mapped_column(ForeignKey("email_messages.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rating: Mapped[int | None] = mapped_column(SmallInteger)
    comment: Mapped[str | None] = mapped_column(Text)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TicketAutoAck(Base):
    """The automatic "we got your request" email sent for a ticket (once per ticket)."""

    __tablename__ = "ticket_auto_acks"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False, unique=True)
    sent_to: Mapped[str] = mapped_column(String(320), nullable=False)
    email_message_id: Mapped[int] = mapped_column(ForeignKey("email_messages.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TicketEscalation(Base):
    """A ticket was escalated after breaching its SLA (once per ticket)."""

    __tablename__ = "ticket_escalations"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False, unique=True)
    email_message_id: Mapped[int | None] = mapped_column(ForeignKey("email_messages.id"))
    bumped_from_priority_id: Mapped[int | None] = mapped_column(ForeignKey("priorities.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PortalLoginToken(Base):
    """A one-time sign-in link. Only the hash is stored; it works once and expires quickly."""

    __tablename__ = "portal_login_tokens"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_ip: Mapped[str | None] = mapped_column(String(64))


class PortalSession(Base):
    __tablename__ = "portal_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))


# ---- new-client quoting (docs/QUOTING.md) -------------------------------------------------
class QuoteSettings(Base):
    """Single-row rate card and uplift percentages (id = 1). Basis points: 2500 = 25%."""

    __tablename__ = "quote_settings"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    per_user_rate_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    workstation_rate_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    server_rate_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    network_rate_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    other_rate_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    hardware_uplift_bp: Mapped[int] = mapped_column(Integer, nullable=False)
    server_uplift_bp: Mapped[int] = mapped_column(Integer, nullable=False)
    legacy_app_uplift_bp: Mapped[int] = mapped_column(Integer, nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_days: Mapped[int] = mapped_column(Integer, nullable=False)
    agreement_taxable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    intro_text: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SiteSurvey(TimestampMixin, Base):
    __tablename__ = "site_surveys"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default="scheduled")
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tech_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    user_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    site_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    notes: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    organization: Mapped[Organization] = relationship(lazy="joined")
    devices: Mapped[list["SurveyDevice"]] = relationship(
        order_by="SurveyDevice.id", lazy="selectin", cascade="all, delete-orphan"
    )
    apps: Mapped[list["SurveyApp"]] = relationship(
        order_by="SurveyApp.id", lazy="selectin", cascade="all, delete-orphan"
    )


class SurveyDevice(Base):
    __tablename__ = "survey_devices"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    survey_id: Mapped[int] = mapped_column(ForeignKey("site_surveys.id"), nullable=False)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    device_class: Mapped[str] = mapped_column(String(12), nullable=False)
    label: Mapped[str | None] = mapped_column(String(200))
    make_model: Mapped[str | None] = mapped_column(String(200))
    serial: Mapped[str | None] = mapped_column(String(100))
    warranty_end: Mapped[date | None] = mapped_column(Date)
    warranty_status: Mapped[str] = mapped_column(String(16), nullable=False)
    priced: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    notes: Mapped[str | None] = mapped_column(Text)


class SurveyApp(Base):
    __tablename__ = "survey_apps"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    survey_id: Mapped[int] = mapped_column(ForeignKey("site_surveys.id"), nullable=False)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    vendor: Mapped[str | None] = mapped_column(String(200))
    legacy: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    notes: Mapped[str | None] = mapped_column(Text)


class Quote(TimestampMixin, Base):
    __tablename__ = "quotes"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    survey_id: Mapped[int] = mapped_column(ForeignKey("site_surveys.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False, server_default="new")
    agreement_id: Mapped[int | None] = mapped_column(ForeignKey("agreements.id"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    replaces_quote_id: Mapped[int | None] = mapped_column(ForeignKey("quotes.id"))
    status: Mapped[str] = mapped_column(String(14), nullable=False, server_default="draft")
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    base_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uplift_bp: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    final_price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    adjustment_reason: Mapped[str | None] = mapped_column(Text)
    adjusted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date)
    effective_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    decision_note: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_to: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    resulting_agreement_id: Mapped[int | None] = mapped_column(ForeignKey("agreements.id"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    organization: Mapped[Organization] = relationship(lazy="joined")


class Integration(TimestampMixin, Base):
    """A connected vendor (MSP-level). `credentials` is ciphertext; see app/crypto.py."""

    __tablename__ = "integrations"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str] = mapped_column(String(300), nullable=False)
    credentials: Mapped[str | None] = mapped_column(Text)
    credentials_set_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="unknown")
    last_error: Mapped[str | None] = mapped_column(Text)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    alerts_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    alerts_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    alerts_last_error: Mapped[str | None] = mapped_column(Text)


class IntegrationClientMap(Base):
    __tablename__ = "integration_client_maps"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    integration_id: Mapped[int] = mapped_column(ForeignKey("integrations.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    external_name: Mapped[str] = mapped_column(String(300), nullable=False)
    psa_organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"))
    ignored: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SyncRun(Base):
    __tablename__ = "sync_runs"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    integration_id: Mapped[int] = mapped_column(ForeignKey("integrations.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="running")
    added: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    changed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    retired: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    clients_synced: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    clients_failed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)


class Asset(TimestampMixin, Base):
    __tablename__ = "assets"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(String(200))
    model: Mapped[str | None] = mapped_column(String(200))
    serial: Mapped[str | None] = mapped_column(String(100))
    serial_norm: Mapped[str | None] = mapped_column(String(100))
    warranty_start: Mapped[date | None] = mapped_column(Date)  # synced value, before overrides
    warranty_end: Mapped[date | None] = mapped_column(Date)
    conflict: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    organization: Mapped[Organization] = relationship(lazy="joined")
    sources: Mapped[list["AssetSource"]] = relationship(
        order_by="AssetSource.id", lazy="selectin", cascade="all, delete-orphan"
    )
    overrides: Mapped[list["AssetOverride"]] = relationship(
        order_by="AssetOverride.id", lazy="selectin", cascade="all, delete-orphan"
    )


class AssetSource(Base):
    __tablename__ = "asset_sources"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    integration_id: Mapped[int] = mapped_column(ForeignKey("integrations.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    data_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AssetOverride(TimestampMixin, Base):
    __tablename__ = "asset_overrides"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    field: Mapped[str] = mapped_column(String(20), nullable=False)
    value_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class RmmAlert(Base):
    """One open alert per (integration, condition); the migration owns constraints and indexes."""

    __tablename__ = "rmm_alerts"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    integration_id: Mapped[int] = mapped_column(ForeignKey("integrations.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    condition_key: Mapped[str] = mapped_column(Text, nullable=False)
    device_external_id: Mapped[str] = mapped_column(Text, nullable=False)
    asset_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ticket_id: Mapped[int | None] = mapped_column(BigInteger)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    occurrences: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    # Consecutive successful polls this open condition was absent from; cleared at two.
    missed_polls: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    asset: Mapped[Asset] = relationship(
        primaryjoin="Asset.id == RmmAlert.asset_id",
        foreign_keys="[RmmAlert.asset_id]",
        lazy="selectin",
        viewonly=True,
    )
    ticket: Mapped["Ticket | None"] = relationship(
        primaryjoin="Ticket.id == RmmAlert.ticket_id",
        foreign_keys="[RmmAlert.ticket_id]",
        lazy="selectin",
        viewonly=True,
    )


class Project(TimestampMixin, Base):
    """Client-scoped project; the migration owns constraints, RLS and grants."""

    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("id", "organization_id", name="uq_projects_id_org"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    billing_mode: Mapped[str | None] = mapped_column(String(20))
    fixed_fee_cents: Mapped[int | None] = mapped_column(BigInteger)
    budget_cents: Mapped[int | None] = mapped_column(BigInteger)
    taxable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    start_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    fixed_fee_invoice_line_id: Mapped[int | None] = mapped_column(ForeignKey("invoice_lines.id"))
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class ProjectPhase(Base):
    __tablename__ = "project_phases"
    __table_args__ = (UniqueConstraint("id", "organization_id", name="uq_project_phases_id_org"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    # composite FK (project_id, organization_id) lives in migration 0029
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    due_date: Mapped[date | None] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectTask(Base):
    """Each task owns exactly one ticket; composite FKs keep everything in one org."""

    __tablename__ = "project_tasks"
    __table_args__ = (UniqueConstraint("id", "organization_id", name="uq_project_tasks_id_org"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    phase_id: Mapped[int | None] = mapped_column(BigInteger)
    ticket_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    estimate_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    start_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    ticket: Mapped[Ticket] = relationship(
        primaryjoin="Ticket.id == ProjectTask.ticket_id",
        foreign_keys="[ProjectTask.ticket_id]",
        lazy="joined",
        viewonly=True,
    )
    phase: Mapped[ProjectPhase | None] = relationship(
        primaryjoin="ProjectPhase.id == ProjectTask.phase_id",
        foreign_keys="[ProjectTask.phase_id]",
        lazy="select",
        viewonly=True,
    )
    project: Mapped[Project] = relationship(
        primaryjoin="Project.id == ProjectTask.project_id",
        foreign_keys="[ProjectTask.project_id]",
        lazy="select",
        viewonly=True,
    )


class ProjectTaskDependency(Base):
    __tablename__ = "project_task_dependencies"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    depends_on_task_id: Mapped[int] = mapped_column(BigInteger, nullable=False)


class Lead(TimestampMixin, Base):
    """Staff-internal sales lead (no organization_id, no RLS)."""

    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    company: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    source: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="new")
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    converted_organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"))
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OpportunityStage(Base):
    """Pipeline stage config (staff-internal); seeded by migration 0030."""

    __tablename__ = "opportunity_stages"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    probability_bp: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # open|won|lost
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class Opportunity(TimestampMixin, Base):
    """Client-scoped; the migration owns constraints, composite FKs, RLS and grants."""

    __tablename__ = "opportunities"
    __table_args__ = (UniqueConstraint("id", "organization_id", name="uq_opportunities_id_org"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False, server_default="new")
    stage_id: Mapped[int] = mapped_column(ForeignKey("opportunity_stages.id"), nullable=False)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    monthly_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    term_months: Mapped[int] = mapped_column(Integer, nullable=False, server_default="12")
    expected_close_date: Mapped[date | None] = mapped_column(Date)
    # composite FKs (quote_id|agreement_id, organization_id) live in migration 0030
    quote_id: Mapped[int | None] = mapped_column(BigInteger)
    agreement_id: Mapped[int | None] = mapped_column(BigInteger)
    lost_reason: Mapped[str | None] = mapped_column(String(300))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


class RenewalReminder(Base):
    __tablename__ = "renewal_reminders"
    __table_args__ = (
        UniqueConstraint("agreement_id", "lead_days", name="uq_renewal_reminders_once"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    agreement_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    lead_days: Mapped[int] = mapped_column(Integer, nullable=False)
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="open")
    opportunity_id: Mapped[int | None] = mapped_column(BigInteger)
    email_message_id: Mapped[int | None] = mapped_column(ForeignKey("email_messages.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---- procurement (migration 0031; staff-internal, no RLS) ----
class Vendor(TimestampMixin, Base):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    account_number: Mapped[str | None] = mapped_column(String(64))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(40))
    website: Mapped[str | None] = mapped_column(String(300))
    notes: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PurchaseOrder(TimestampMixin, Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    number: Mapped[str | None] = mapped_column(String(20), unique=True)  # 'PO-<id>', set by service
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), nullable=False)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"))
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="draft")
    ordered_on: Mapped[date | None] = mapped_column(Date)
    expected_on: Mapped[date | None] = mapped_column(Date)
    vendor_reference: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    vendor: Mapped[Vendor] = relationship(lazy="joined")
    lines: Mapped[list["PurchaseOrderLine"]] = relationship(
        order_by="PurchaseOrderLine.position, PurchaseOrderLine.id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PurchaseOrderLine(TimestampMixin, Base):
    __tablename__ = "purchase_order_lines"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    received_quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    serialised: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    billable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    taxable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    markup_bp: Mapped[int | None] = mapped_column(Integer)


class InventoryItem(TimestampMixin, Base):
    """Stock received against a PO line. Serial uniqueness (lower(serial_number)) lives in the
    migration."""

    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    purchase_order_line_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase_order_lines.id")
    )
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(120))
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="in_stock")
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"))
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"))
    delivered_on: Mapped[date | None] = mapped_column(Date)
    markup_bp: Mapped[int | None] = mapped_column(Integer)  # frozen at delivery
    product_charge_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_charges.id"), unique=True
    )
    received_on: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class MarkupRule(TimestampMixin, Base):
    """Exactly one of product_id / category is set (CHECK in the migration)."""

    __tablename__ = "markup_rules"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), unique=True)
    category: Mapped[str | None] = mapped_column(String(10), unique=True)
    markup_bp: Mapped[int] = mapped_column(Integer, nullable=False)
