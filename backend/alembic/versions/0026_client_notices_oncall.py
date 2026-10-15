"""Client appointment notices and on-call rotations

Revision ID: 0026
Revises: 0025

appointment_notices is a per-appointment email queue (one pending row at a time). The oncall_*
tables hold weekly rotations, their ordered members and temporary overrides. appointment_notices
is client-scoped by organization_id with forced RLS like appointment_sync. The oncall_* tables are
staff-internal like user_time_off: no organization_id, no RLS, guarded by schedule permissions.
"""
import sqlalchemy as sa

from alembic import op

revision = "0026"
down_revision = "0025"
APP_ROLE = "psa_app"
NOW = sa.text("now()")

GRANTS = {
    "appointment_notices": "SELECT, INSERT, UPDATE",
    "oncall_rotations": "SELECT, INSERT, UPDATE",
    "oncall_members": "SELECT, INSERT, UPDATE, DELETE",
    "oncall_overrides": "SELECT, INSERT, UPDATE, DELETE",
}


def _org_col() -> sa.Column:
    return sa.Column(
        "organization_id", sa.BigInteger, sa.ForeignKey("organizations.id"), nullable=False
    )


def _rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY org_scope ON {table} "
        "USING (app_org_visible(organization_id)) "
        "WITH CHECK (app_org_visible(organization_id))"
    )


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column("notify_client", sa.Boolean, nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "settings",
        sa.Column(
            "appointment_emails_enabled", sa.Boolean, nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.create_table(
        "appointment_notices",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        _org_col(),
        sa.Column("appointment_id", sa.BigInteger,
                  sa.ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("kind", sa.Text),
        sa.Column("send_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("email_message_id", sa.BigInteger,
                  sa.ForeignKey("email_messages.id", ondelete="SET NULL")),
        sa.Column("reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("state IN ('pending','sent','skipped')",
                           name="ck_appointment_notices_state"),
        sa.CheckConstraint("kind IS NULL OR kind IN ('booked','moved','cancelled')",
                           name="ck_appointment_notices_kind"),
    )
    op.create_index(
        "uq_appointment_notices_pending", "appointment_notices", ["appointment_id"],
        unique=True, postgresql_where=sa.text("state = 'pending'"),
    )
    op.create_index("ix_appointment_notices_due", "appointment_notices", ["state", "send_after"])

    op.create_table(
        "oncall_rotations",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("handoff_weekday", sa.SmallInteger, nullable=False),
        sa.Column("handoff_time", sa.Time, nullable=False),
        sa.Column("anchor_date", sa.Date, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.CheckConstraint("handoff_weekday BETWEEN 0 AND 6",
                           name="ck_oncall_rotations_weekday"),
        sa.CheckConstraint("extract(isodow from anchor_date)::int - 1 = handoff_weekday",
                           name="ck_oncall_rotations_anchor"),
    )

    op.create_table(
        "oncall_members",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("rotation_id", sa.BigInteger,
                  sa.ForeignKey("oncall_rotations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.UniqueConstraint("rotation_id", "position", name="uq_oncall_members_position"),
        sa.UniqueConstraint("rotation_id", "user_id", name="uq_oncall_members_user"),
    )

    op.create_table(
        "oncall_overrides",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("rotation_id", sa.BigInteger,
                  sa.ForeignKey("oncall_rotations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.CheckConstraint("ends_at > starts_at", name="ck_oncall_overrides_range"),
    )
    op.create_index("ix_oncall_overrides_rotation", "oncall_overrides",
                    ["rotation_id", "starts_at"])

    _rls("appointment_notices")
    for table, privs in GRANTS.items():
        op.execute(f"GRANT {privs} ON {table} TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("oncall_overrides")
    op.drop_table("oncall_members")
    op.drop_table("oncall_rotations")
    op.drop_table("appointment_notices")
    op.drop_column("settings", "appointment_emails_enabled")
    op.drop_column("appointments", "notify_client")
