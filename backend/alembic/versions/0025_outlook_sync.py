"""Outlook push: the appointment_sync outbox, the busy cache and the outlook_sync_enabled setting

Revision ID: 0025
Revises: 0024

appointment_sync is client-owned (organization_id, forced RLS like appointments). busy_blocks and
calendar_busy_status are staff data keyed by user, with the same grants as user_time_off.
"""
import sqlalchemy as sa

from alembic import op

revision = "0025"
down_revision = "0024"
APP_ROLE = "psa_app"
NOW = sa.text("now()")


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column("outlook_sync_enabled", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
    )

    op.create_table(
        "appointment_sync",
        sa.Column("appointment_id", sa.BigInteger,
                  sa.ForeignKey("appointments.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("organization_id", sa.BigInteger, nullable=False),
        sa.Column("generation", sa.Integer, nullable=False, server_default="1"),
        sa.Column("desired_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("synced_version", sa.Integer, nullable=False, server_default="0"),
        sa.Column("synced_tech_id", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("graph_event_id", sa.String(512)),
        sa.Column("state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=NOW),
        sa.Column("last_error", sa.String(500)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.CheckConstraint("state IN ('pending','synced','failed','skipped')",
                           name="ck_appointment_sync_state"),
    )
    op.create_index("ix_appointment_sync_due", "appointment_sync", ["state", "next_attempt_at"])
    op.execute("ALTER TABLE appointment_sync ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE appointment_sync FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY org_scope ON appointment_sync "
               "USING (app_org_visible(organization_id)) "
               "WITH CHECK (app_org_visible(organization_id))")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON appointment_sync TO {APP_ROLE}")

    op.create_table(
        "busy_blocks",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.CheckConstraint("ends_at > starts_at", name="ck_busy_blocks_range"),
    )
    op.create_index("ix_busy_blocks_user_start", "busy_blocks", ["user_id", "starts_at"])
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON busy_blocks TO {APP_ROLE}")

    op.create_table(
        "calendar_busy_status",
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(500)),
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON calendar_busy_status TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("calendar_busy_status")
    op.drop_table("busy_blocks")
    op.drop_table("appointment_sync")
    op.drop_column("settings", "outlook_sync_enabled")
