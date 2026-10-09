"""Ticketing: queues, categories, priorities, work types, settings, tickets, notes, time,
email messages, attachments, mailbox status

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision = "0002"
down_revision = "0001"

APP_ROLE = "psa_app"
TS = dict(server_default=sa.text("now()"), nullable=False)
STATUSES = "('new','open','waiting_on_customer','resolved','closed')"


def _lookup(name: str, extra: list[sa.Column] | None = None) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        *(extra or []),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.Column("updated_at", sa.DateTime(timezone=True), **TS),
    )
    op.execute(f"CREATE UNIQUE INDEX uq_{name}_name_active ON {name} (lower(name)) "
               "WHERE archived_at IS NULL")


def upgrade() -> None:
    # ---- configuration (editable rows) ---------------------------------------------------
    _lookup("queues", [sa.Column("is_default", sa.Boolean, nullable=False,
                                 server_default=sa.text("false"))])
    op.execute("CREATE UNIQUE INDEX uq_queues_one_default ON queues (is_default) "
               "WHERE is_default AND archived_at IS NULL")
    _lookup("categories")
    _lookup("priorities", [
        sa.Column("rank", sa.Integer, nullable=False),  # 1 = most urgent
        sa.Column("first_response_minutes", sa.Integer),  # business minutes; NULL = no target
        sa.Column("resolution_minutes", sa.Integer),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default=sa.text("false")),
    ])
    op.execute("CREATE UNIQUE INDEX uq_priorities_one_default ON priorities (is_default) "
               "WHERE is_default AND archived_at IS NULL")
    _lookup("work_types")

    op.create_table(
        "settings",
        sa.Column("id", sa.SmallInteger, primary_key=True),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="America/Chicago"),
        sa.Column("business_days", ARRAY(sa.Integer), nullable=False,
                  server_default=sa.text("'{0,1,2,3,4}'")),  # 0 = Monday
        sa.Column("business_start_minute", sa.Integer, nullable=False, server_default="480"),
        sa.Column("business_end_minute", sa.Integer, nullable=False, server_default="1020"),
        sa.Column("billing_increment_minutes", sa.Integer, nullable=False, server_default="15"),
        sa.Column("sla_at_risk_percent", sa.Integer, nullable=False, server_default="25"),
        sa.Column("updated_at", sa.DateTime(timezone=True), **TS),
        sa.CheckConstraint("id = 1", name="ck_settings_singleton"),
        sa.CheckConstraint("business_start_minute >= 0 AND business_end_minute <= 1440 "
                           "AND business_start_minute < business_end_minute",
                           name="ck_settings_hours"),
        sa.CheckConstraint("billing_increment_minutes > 0", name="ck_settings_increment"),
        sa.CheckConstraint("sla_at_risk_percent BETWEEN 0 AND 100", name="ck_settings_risk"),
    )
    op.execute("INSERT INTO settings (id) VALUES (1)")

    op.create_table(
        "mailbox_status",
        sa.Column("id", sa.SmallInteger, primary_key=True),
        # The WORKER reports its own state here: the API container deliberately does not hold the
        # Graph secret, so it cannot know whether mail is configured.
        sa.Column("mailbox", sa.String(320)),  # NULL = worker running but mail not configured
        sa.Column("worker_seen_at", sa.DateTime(timezone=True)),
        sa.Column("last_poll_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text),
        sa.Column("last_error_at", sa.DateTime(timezone=True)),
        sa.Column("messages_ingested", sa.BigInteger, nullable=False, server_default="0"),
        sa.CheckConstraint("id = 1", name="ck_mailbox_status_singleton"),
    )
    op.execute("INSERT INTO mailbox_status (id) VALUES (1)")

    # Sensible starting rows; all editable in the UI.
    op.execute("INSERT INTO queues (name, is_default) VALUES ('Support', true), ('Security', false)")
    op.execute("INSERT INTO categories (name) VALUES ('General'), ('Microsoft 365'), "
               "('Network'), ('Hardware'), ('Security'), ('Onboarding / Offboarding')")
    op.execute(
        "INSERT INTO priorities (name, rank, first_response_minutes, resolution_minutes, is_default) "
        "VALUES ('Urgent', 1, 30, 240, false), ('High', 2, 60, 480, false), "
        "('Normal', 3, 240, 1440, true), ('Low', 4, 480, 4320, false)"
    )
    op.execute("INSERT INTO work_types (name) VALUES ('Remote'), ('Onsite'), ('After hours')")

    # ---- tickets ------------------------------------------------------------------------
    op.execute("CREATE SEQUENCE ticket_number_seq START 10001")
    op.create_table(
        "tickets",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("number", sa.BigInteger, nullable=False, unique=True,
                  server_default=sa.text("nextval('ticket_number_seq')")),
        # NULL organization = email from an unknown sender awaiting triage
        sa.Column("organization_id", sa.BigInteger, sa.ForeignKey("organizations.id")),
        sa.Column("contact_id", sa.BigInteger, sa.ForeignKey("contacts.id")),
        sa.Column("site_id", sa.BigInteger, sa.ForeignKey("sites.id")),
        sa.Column("queue_id", sa.BigInteger, sa.ForeignKey("queues.id"), nullable=False),
        sa.Column("category_id", sa.BigInteger, sa.ForeignKey("categories.id")),
        sa.Column("priority_id", sa.BigInteger, sa.ForeignKey("priorities.id"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="new"),
        sa.Column("assignee_id", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("subject", sa.String(300), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("source", sa.String(10), nullable=False, server_default="ui"),
        sa.Column("requester_email", sa.String(320)),
        sa.Column("sla_first_response_due", sa.DateTime(timezone=True)),
        sa.Column("sla_resolution_due", sa.DateTime(timezone=True)),
        sa.Column("first_responded_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("sla_paused_at", sa.DateTime(timezone=True)),
        sa.Column("sla_paused_minutes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_by_user_id", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.Column("updated_at", sa.DateTime(timezone=True), **TS),
        sa.CheckConstraint(f"status IN {STATUSES}", name="ck_tickets_status"),
        sa.CheckConstraint("source IN ('ui','email')", name="ck_tickets_source"),
        sa.CheckConstraint("organization_id IS NOT NULL OR source = 'email'",
                           name="ck_tickets_org_required_unless_email"),
    )
    for col in ("organization_id", "status", "assignee_id", "queue_id"):
        op.create_index(f"ix_tickets_{col}", "tickets", [col])

    op.create_table(
        "email_messages",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("direction", sa.String(3), nullable=False),
        sa.Column("graph_message_id", sa.String(400), unique=True),
        sa.Column("internet_message_id", sa.String(998)),
        sa.Column("in_reply_to", sa.String(998)),
        sa.Column("conversation_id", sa.String(400)),
        sa.Column("ticket_id", sa.BigInteger, sa.ForeignKey("tickets.id")),
        sa.Column("organization_id", sa.BigInteger),
        sa.Column("from_email", sa.String(320)),
        sa.Column("to_emails", JSONB),
        sa.Column("subject", sa.String(998)),
        sa.Column("body_text", sa.Text),
        sa.Column("received_at", sa.DateTime(timezone=True)),
        sa.Column("ingest_status", sa.String(20)),   # in: ticket_created|appended|ignored
        sa.Column("ingest_detail", sa.Text),
        sa.Column("send_status", sa.String(10)),     # out: pending|sent|failed
        sa.Column("send_attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("send_error", sa.Text),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.CheckConstraint("direction IN ('in','out')", name="ck_email_direction"),
    )
    op.create_index("ix_email_messages_ticket_id", "email_messages", ["ticket_id"])
    op.create_index("ix_email_messages_internet_message_id", "email_messages",
                    ["internet_message_id"])
    op.execute("CREATE INDEX ix_email_messages_outbox ON email_messages (send_status) "
               "WHERE direction = 'out' AND send_status = 'pending'")

    op.create_table(
        "ticket_notes",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("ticket_id", sa.BigInteger, sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("organization_id", sa.BigInteger),
        sa.Column("author_user_id", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("author_email", sa.String(320)),
        sa.Column("visibility", sa.String(10), nullable=False),
        sa.Column("source", sa.String(10), nullable=False, server_default="ui"),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("email_message_id", sa.BigInteger, sa.ForeignKey("email_messages.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.CheckConstraint("visibility IN ('internal','customer')", name="ck_notes_visibility"),
        sa.CheckConstraint("source IN ('ui','email')", name="ck_notes_source"),
    )
    op.create_index("ix_ticket_notes_ticket_id", "ticket_notes", ["ticket_id"])

    op.create_table(
        "time_entries",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("ticket_id", sa.BigInteger, sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("organization_id", sa.BigInteger, nullable=False),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("work_type_id", sa.BigInteger, sa.ForeignKey("work_types.id"), nullable=False),
        sa.Column("work_date", sa.Date, nullable=False),
        sa.Column("minutes_actual", sa.Integer, nullable=False),
        sa.Column("minutes_billable", sa.Integer, nullable=False),
        sa.Column("billable", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("note", sa.Text),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.Column("updated_at", sa.DateTime(timezone=True), **TS),
        sa.CheckConstraint("minutes_actual > 0 AND minutes_actual <= 1440",
                           name="ck_time_minutes_actual"),
        sa.CheckConstraint("minutes_billable >= 0", name="ck_time_minutes_billable"),
    )
    op.create_index("ix_time_entries_ticket_id", "time_entries", ["ticket_id"])
    op.create_index("ix_time_entries_organization_id", "time_entries", ["organization_id"])
    op.create_index("ix_time_entries_user_date", "time_entries", ["user_id", "work_date"])

    op.create_table(
        "attachments",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("email_message_id", sa.BigInteger, sa.ForeignKey("email_messages.id"),
                  nullable=False),
        sa.Column("ticket_id", sa.BigInteger, sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("organization_id", sa.BigInteger),
        sa.Column("filename", sa.String(300), nullable=False),
        sa.Column("content_type", sa.String(200)),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
    )
    op.create_index("ix_attachments_ticket_id", "attachments", ["ticket_id"])

    # ---- RLS on client-owned tables (organization_id may be NULL = unmatched) -------------
    for table in ("tickets", "ticket_notes", "time_entries", "email_messages", "attachments"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY org_scope ON {table} USING (app_org_visible(organization_id)) "
                   f"WITH CHECK (app_org_visible(organization_id))")

    # ---- Grants ---------------------------------------------------------------------------
    for table in ("queues", "categories", "priorities", "work_types", "settings", "tickets",
                  "time_entries", "email_messages", "mailbox_status"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON ticket_notes, attachments TO {APP_ROLE}")  # immutable
    # triage moves an unmatched ticket's children to its organization: that column only
    op.execute(f"GRANT UPDATE (organization_id) ON ticket_notes, attachments TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    for table in ("attachments", "time_entries", "ticket_notes", "email_messages", "tickets",
                  "mailbox_status", "settings", "work_types", "priorities", "categories",
                  "queues"):
        op.drop_table(table)
    op.execute("DROP SEQUENCE ticket_number_seq")
