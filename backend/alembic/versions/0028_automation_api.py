"""Automation and API: api_keys, webhook_endpoints, webhook_deliveries, automation_rules,
automation_runs, tickets.sla_breached_event_at, ticket source 'rule'

Revision ID: 0028
Revises: 0027

All five tables are staff-internal (like staff_notifications): no organization_id and no RLS.
psa_app gets SELECT, INSERT, UPDATE only; nothing is ever deleted.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0028"
down_revision = "0027"
APP_ROLE = "psa_app"
NOW = sa.text("now()")
TABLES = (
    "api_keys",
    "webhook_endpoints",
    "webhook_deliveries",
    "automation_rules",
    "automation_runs",
)


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("prefix", sa.String(8), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("permissions", pg.ARRAY(sa.String), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_by_id", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("prefix", name="uq_api_keys_prefix"),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )

    op.create_table(
        "webhook_endpoints",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("secret", sa.Text, nullable=False),
        sa.Column("events", pg.ARRAY(sa.String), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("consecutive_failures", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_failure_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_id", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.CheckConstraint("kind IN ('generic','teams')", name="ck_webhook_endpoints_kind"),
        sa.CheckConstraint(
            "consecutive_failures >= 0", name="ck_webhook_endpoints_consecutive_failures"
        ),
    )

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column(
            "endpoint_id", sa.BigInteger, sa.ForeignKey("webhook_endpoints.id"), nullable=False
        ),
        sa.Column("event_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("payload", pg.JSONB, nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("last_status_code", sa.Integer),
        sa.Column("last_error", sa.String(300)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("endpoint_id", "event_id", name="uq_webhook_deliveries_event"),
        sa.CheckConstraint(
            "status IN ('pending','delivered','failed')", name="ck_webhook_deliveries_status"
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_webhook_deliveries_attempts"),
    )
    op.create_index("ix_webhook_deliveries_due", "webhook_deliveries", ["status", "next_attempt_at"])

    op.create_table(
        "automation_rules",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("trigger", sa.String(40), nullable=False),
        sa.Column("conditions", pg.JSONB, nullable=False, server_default="[]"),
        sa.Column("actions", pg.JSONB, nullable=False, server_default="[]"),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("disabled_reason", sa.String(200)),
        sa.Column("fire_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_fired_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_id", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.CheckConstraint("trigger <> ''", name="ck_automation_rules_trigger"),
        sa.CheckConstraint("fire_count >= 0", name="ck_automation_rules_fire_count"),
    )

    op.create_table(
        "automation_runs",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("rule_id", sa.BigInteger, sa.ForeignKey("automation_rules.id"), nullable=False),
        sa.Column("event_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("ticket_id", sa.BigInteger, sa.ForeignKey("tickets.id")),
        sa.Column("matched", sa.Boolean, nullable=False),
        sa.Column("dry_run", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("trace", pg.JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index(
        "uq_automation_runs_event",
        "automation_runs",
        ["rule_id", "event_id"],
        unique=True,
        postgresql_where=sa.text("NOT dry_run"),
    )

    op.add_column("tickets", sa.Column("sla_breached_event_at", sa.DateTime(timezone=True)))
    op.drop_constraint("ck_tickets_source", "tickets", type_="check")
    op.create_check_constraint(
        "ck_tickets_source", "tickets", "source IN ('ui','email','portal','rmm','rule')"
    )

    for table in TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("automation_runs")
    op.drop_table("automation_rules")
    op.drop_table("webhook_deliveries")
    op.drop_table("webhook_endpoints")
    op.drop_table("api_keys")
    op.execute("UPDATE tickets SET source = 'ui' WHERE source = 'rule'")
    op.drop_constraint("ck_tickets_source", "tickets", type_="check")
    op.create_check_constraint(
        "ck_tickets_source", "tickets", "source IN ('ui','email','portal','rmm')"
    )
    op.drop_column("tickets", "sla_breached_event_at")
