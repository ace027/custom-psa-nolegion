"""Parity phase 1D (part 2): customer satisfaction surveys

Revision ID: 0016
Revises: 0015
"""
import sqlalchemy as sa

from alembic import op

revision = "0016"
down_revision = "0015"
APP_ROLE = "psa_app"


def upgrade() -> None:
    op.add_column("settings", sa.Column("csat_enabled", sa.Boolean, nullable=False,
                                        server_default=sa.false()))
    op.create_table(
        "csat_surveys",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        # one survey per ticket: reopening and resolving again never asks twice
        sa.Column("ticket_id", sa.BigInteger, sa.ForeignKey("tickets.id"), nullable=False,
                  unique=True),
        sa.Column("organization_id", sa.BigInteger, sa.ForeignKey("organizations.id"),
                  nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("sent_to", sa.String(320), nullable=False),
        sa.Column("email_message_id", sa.BigInteger, sa.ForeignKey("email_messages.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rating", sa.SmallInteger),
        sa.Column("comment", sa.Text),
        sa.Column("responded_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_csat_rating"),
        sa.CheckConstraint("(rating IS NULL) = (responded_at IS NULL)", name="ck_csat_answered"),
        sa.CheckConstraint("comment IS NULL OR length(comment) <= 2000", name="ck_csat_comment"),
    )
    op.create_index("ix_csat_surveys_org", "csat_surveys", ["organization_id"])
    op.execute("ALTER TABLE csat_surveys ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE csat_surveys FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY org_scope ON csat_surveys USING (app_org_visible(organization_id)) "
               "WITH CHECK (app_org_visible(organization_id))")
    # Surveys are never deleted. Once created, only the answer columns may change.
    op.execute(f"GRANT SELECT, INSERT ON csat_surveys TO {APP_ROLE}")
    op.execute(f"GRANT UPDATE (rating, comment, responded_at) ON csat_surveys TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("csat_surveys")
    op.drop_column("settings", "csat_enabled")
