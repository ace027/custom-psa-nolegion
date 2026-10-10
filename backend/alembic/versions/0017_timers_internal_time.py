"""Parity phase 2A: timers and internal (non-ticket) time

Revision ID: 0017
Revises: 0016
"""
import sqlalchemy as sa

from alembic import op

revision = "0017"
down_revision = "0016"
APP_ROLE = "psa_app"


def _stamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
    ]


def upgrade() -> None:
    # Everything here belongs to the MSP, not to a client, so there is no organization_id and no
    # RLS. A timer only remembers WHICH ticket; the ticket is re-checked (scope, client) when the
    # timer is stopped and becomes a normal time entry.
    op.create_table(
        "time_categories",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        *_stamps(),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_time_categories_name"),
    )
    op.create_index("uq_time_categories_name_active", "time_categories", [sa.text("lower(name)")],
                    unique=True, postgresql_where=sa.text("archived_at IS NULL"))
    op.execute("INSERT INTO time_categories (name) VALUES ('Administration'), ('Training'), "
               "('Meeting'), ('Paid time off')")

    op.create_table(
        "internal_time_entries",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("category_id", sa.BigInteger, sa.ForeignKey("time_categories.id"),
                  nullable=False),
        sa.Column("work_date", sa.Date, nullable=False),
        sa.Column("minutes", sa.Integer, nullable=False),
        sa.Column("note", sa.Text),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        *_stamps(),
        sa.CheckConstraint("minutes > 0 AND minutes <= 1440", name="ck_internal_time_minutes"),
    )
    op.create_index("ix_internal_time_user_date", "internal_time_entries",
                    ["user_id", "work_date"])

    op.create_table(
        "timers",
        # one running timer per person: the primary key enforces it
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("ticket_id", sa.BigInteger, sa.ForeignKey("tickets.id")),
        sa.Column("work_type_id", sa.BigInteger, sa.ForeignKey("work_types.id")),
        sa.Column("category_id", sa.BigInteger, sa.ForeignKey("time_categories.id")),
        sa.Column("billable", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("note", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.CheckConstraint(
            "(ticket_id IS NOT NULL AND work_type_id IS NOT NULL AND category_id IS NULL) OR "
            "(ticket_id IS NULL AND work_type_id IS NULL AND category_id IS NOT NULL)",
            name="ck_timers_target",
        ),
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON time_categories, internal_time_entries "
               f"TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, DELETE ON timers TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("timers")
    op.drop_table("internal_time_entries")
    op.drop_table("time_categories")
