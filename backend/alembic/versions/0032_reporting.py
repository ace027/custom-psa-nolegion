"""Reporting: user cost rate, report schedules and their runs

Revision ID: 0032
Revises: 0031

users.cost_rate_cents is the hourly internal cost of a person's time (admin-only through the API).
report_schedules and report_schedule_runs are staff-internal (no RLS, no DELETE: schedules are
deactivated, runs are history). One run per schedule and period keeps the worker idempotent.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0032"
down_revision = "0031"
APP_ROLE = "psa_app"
NOW = sa.text("now()")
TABLES = ("report_schedules", "report_schedule_runs")


def _stamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    ]


def upgrade() -> None:
    op.add_column("users", sa.Column("cost_rate_cents", sa.BigInteger))
    op.create_check_constraint(
        "ck_users_cost_rate", "users", "cost_rate_cents IS NULL OR cost_rate_cents >= 0"
    )

    op.create_table(
        "report_schedules",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("report", sa.String(15), nullable=False),
        sa.Column("frequency", sa.String(10), nullable=False),
        sa.Column("weekday", sa.SmallInteger),
        sa.Column("day_of_month", sa.SmallInteger),
        sa.Column("recipient_user_ids", postgresql.ARRAY(sa.BigInteger), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("users.id")),
        *_stamps(),
        sa.CheckConstraint(
            "report IN ('sla','utilisation','aging','profitability')",
            name="ck_report_schedules_report",
        ),
        sa.CheckConstraint(
            "frequency IN ('weekly','monthly')", name="ck_report_schedules_frequency"
        ),
        sa.CheckConstraint(
            "weekday IS NULL OR weekday BETWEEN 0 AND 6", name="ck_report_schedules_weekday"
        ),
        sa.CheckConstraint(
            "day_of_month IS NULL OR day_of_month BETWEEN 1 AND 28",
            name="ck_report_schedules_day",
        ),
        sa.CheckConstraint(
            "(frequency = 'weekly' AND weekday IS NOT NULL AND day_of_month IS NULL) OR "
            "(frequency = 'monthly' AND day_of_month IS NOT NULL AND weekday IS NULL)",
            name="ck_report_schedules_timing",
        ),
        sa.CheckConstraint(
            "cardinality(recipient_user_ids) BETWEEN 1 AND 20",
            name="ck_report_schedules_recipients",
        ),
    )

    op.create_table(
        "report_schedule_runs",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column(
            "schedule_id", sa.BigInteger, sa.ForeignKey("report_schedules.id"), nullable=False
        ),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column(
            "recipients",
            postgresql.ARRAY(sa.Text),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("email_message_id", sa.BigInteger, sa.ForeignKey("email_messages.id")),
        sa.Column("detail", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.CheckConstraint(
            "status IN ('sent','skipped','failed')", name="ck_report_schedule_runs_status"
        ),
        sa.UniqueConstraint("schedule_id", "period_start", name="uq_report_schedule_runs_period"),
    )

    for table in TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("report_schedule_runs")
    op.drop_table("report_schedules")
    op.drop_constraint("ck_users_cost_rate", "users", type_="check")
    op.drop_column("users", "cost_rate_cents")
