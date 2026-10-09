"""Parity phase 2B: timesheet submit / approve / return

Revision ID: 0018
Revises: 0017
"""
import sqlalchemy as sa

from alembic import op

revision = "0018"
down_revision = "0017"
APP_ROLE = "psa_app"


def upgrade() -> None:
    # One row per person per week, created when the week is first submitted. No row = the week is
    # still open. 'returned' means an admin sent it back: it is editable again and keeps the
    # reason. MSP-level data (no client), so no organization_id and no RLS.
    op.create_table(
        "timesheets",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("week_start", sa.Date, nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("approved_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("returned_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("returned_at", sa.DateTime(timezone=True)),
        sa.Column("return_reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.UniqueConstraint("user_id", "week_start", name="uq_timesheets_user_week"),
        sa.CheckConstraint("status IN ('submitted','approved','returned')",
                           name="ck_timesheets_status"),
        sa.CheckConstraint("extract(isodow FROM week_start) = 1", name="ck_timesheets_monday"),
    )
    op.create_index("ix_timesheets_status", "timesheets", ["status", "week_start"])
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON timesheets TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("timesheets")
