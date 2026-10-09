"""Scheduling: per-user timezone, working hours, time off, and client-owned appointments

Revision ID: 0024
Revises: 0023

A user with no user_work_hours rows works the organisation's default business hours.
Appointments carry their ticket's organization_id through a composite FK (ON UPDATE CASCADE),
so moving a ticket to another client moves its appointments with it and RLS stays correct.
"""
import sqlalchemy as sa

from alembic import op

revision = "0024"
down_revision = "0023"
APP_ROLE = "psa_app"
TS = dict(server_default=sa.text("now()"), nullable=False)


def upgrade() -> None:
    op.add_column("users", sa.Column("timezone", sa.String(64), nullable=True))
    # Target for the appointments composite FK (id alone is already unique).
    op.create_unique_constraint("uq_tickets_id_org", "tickets", ["id", "organization_id"])

    op.create_table(
        "user_work_hours",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("weekday", sa.SmallInteger, nullable=False),
        sa.Column("start_minute", sa.Integer, nullable=False),
        sa.Column("end_minute", sa.Integer, nullable=False),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_user_work_hours_weekday"),
        sa.CheckConstraint(
            "0 <= start_minute AND start_minute < end_minute AND end_minute <= 1440",
            name="ck_user_work_hours_range"),
        sa.UniqueConstraint("user_id", "weekday", name="uq_user_work_hours_day"),
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON user_work_hours TO {APP_ROLE}")

    op.create_table(
        "user_time_off",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("requested_by", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decided_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.Column("updated_at", sa.DateTime(timezone=True), **TS),
        sa.CheckConstraint("status IN ('pending','approved','rejected','cancelled')",
                           name="ck_user_time_off_status"),
        sa.CheckConstraint(
            "ends_at > starts_at AND ends_at - starts_at <= interval '366 days'",
            name="ck_user_time_off_range"),
        sa.CheckConstraint(
            "status NOT IN ('approved','rejected') "
            "OR (decided_by IS NOT NULL AND decided_at IS NOT NULL)",
            name="ck_user_time_off_decided"),
    )
    op.create_index("ix_user_time_off_user_start", "user_time_off", ["user_id", "starts_at"])
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON user_time_off TO {APP_ROLE}")

    op.create_table(
        "appointments",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("organization_id", sa.BigInteger, nullable=False),
        sa.Column("ticket_id", sa.BigInteger, nullable=False),
        sa.Column("tech_id", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="scheduled"),
        sa.Column("notes", sa.Text),
        sa.Column("client_visible", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("cancel_reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.Column("updated_at", sa.DateTime(timezone=True), **TS),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"],
                                name="fk_appointments_org"),
        sa.ForeignKeyConstraint(["ticket_id", "organization_id"],
                                ["tickets.id", "tickets.organization_id"],
                                name="fk_appointments_ticket_org", onupdate="CASCADE"),
        sa.CheckConstraint("status IN ('scheduled','cancelled')", name="ck_appointments_status"),
        sa.CheckConstraint(
            "ends_at > starts_at AND ends_at - starts_at <= interval '24 hours'",
            name="ck_appointments_range"),
        sa.CheckConstraint("(status = 'cancelled') = (cancelled_at IS NOT NULL)",
                           name="ck_appointments_cancelled"),
    )
    op.create_index("ix_appointments_tech_start", "appointments", ["tech_id", "starts_at"])
    op.create_index("ix_appointments_ticket", "appointments", ["ticket_id"])
    op.create_index("ix_appointments_organization_id", "appointments", ["organization_id"])
    op.execute("ALTER TABLE appointments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE appointments FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY org_scope ON appointments USING (app_org_visible(organization_id)) "
               "WITH CHECK (app_org_visible(organization_id))")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON appointments TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("appointments")
    op.drop_table("user_time_off")
    op.drop_table("user_work_hours")
    op.drop_constraint("uq_tickets_id_org", "tickets", type_="unique")
    op.drop_column("users", "timezone")
