"""Parity phase 1C (part 2): ticket types and custom fields

Revision ID: 0014
Revises: 0013
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0014"
down_revision = "0013"
APP_ROLE = "psa_app"


def _stamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
    ]


def upgrade() -> None:
    # MSP-level configuration (definitions), not client data: no RLS. Values live on tickets,
    # which are already row-level protected.
    op.create_table(
        "ticket_types",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        *_stamps(),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_ticket_types_name"),
    )
    op.create_index("uq_ticket_types_name_active", "ticket_types", [sa.text("lower(name)")],
                    unique=True, postgresql_where=sa.text("archived_at IS NULL"))

    op.create_table(
        "custom_fields",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("ticket_type_id", sa.BigInteger, sa.ForeignKey("ticket_types.id"),
                  nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("field_type", sa.String(10), nullable=False),
        sa.Column("options", JSONB),
        sa.Column("required", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("client_visible", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        *_stamps(),
        sa.CheckConstraint("field_type IN ('text','number','date','dropdown','checkbox')",
                           name="ck_custom_fields_type"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_custom_fields_name"),
        sa.CheckConstraint(
            "(field_type = 'dropdown') = (options IS NOT NULL)", name="ck_custom_fields_options"
        ),
    )
    op.create_index("uq_custom_fields_name_active", "custom_fields",
                    ["ticket_type_id", sa.text("lower(name)")], unique=True,
                    postgresql_where=sa.text("archived_at IS NULL"))
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON ticket_types, custom_fields TO {APP_ROLE}")

    op.add_column("tickets", sa.Column("type_id", sa.BigInteger,
                                       sa.ForeignKey("ticket_types.id")))
    op.add_column("tickets", sa.Column("custom_values", JSONB, nullable=False,
                                       server_default=sa.text("'{}'::jsonb")))
    op.create_index("ix_tickets_type_id", "tickets", ["type_id"])


def downgrade() -> None:
    op.drop_index("ix_tickets_type_id", "tickets")
    op.drop_column("tickets", "custom_values")
    op.drop_column("tickets", "type_id")
    op.drop_table("custom_fields")
    op.drop_table("ticket_types")
