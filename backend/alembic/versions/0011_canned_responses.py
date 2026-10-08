"""Parity phase 1A: canned responses

Revision ID: 0011
Revises: 0010
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
APP_ROLE = "psa_app"
TS = dict(server_default=sa.text("now()"), nullable=False)


def upgrade() -> None:
    # MSP-level reusable reply text (not client data): no organization_id, no RLS, like queues.
    op.create_table(
        "canned_responses",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.Column("updated_at", sa.DateTime(timezone=True), **TS),
        sa.CheckConstraint("length(trim(body)) > 0", name="ck_canned_body"),
    )
    op.execute("CREATE UNIQUE INDEX uq_canned_responses_name_active "
               "ON canned_responses (lower(name)) WHERE archived_at IS NULL")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON canned_responses TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("canned_responses")
