"""Onboarding wizard: the admin's encrypted, short-lived Microsoft consent token

Revision ID: 0043
Revises: 0042

onboarding_tokens has no organization_id: like `sessions` it is looked up by its owner (user_id),
so no RLS policy. Grants: SELECT, INSERT, DELETE only (a token is replaced by delete + insert and
never edited in place).
"""

import sqlalchemy as sa

from alembic import op

revision = "0043"
down_revision = "0042"
APP_ROLE = "psa_app"


def upgrade() -> None:
    op.create_table(
        "onboarding_tokens",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_ciphertext", sa.Text, nullable=False),
        sa.Column("scopes", sa.Text),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", name="uq_onboarding_tokens_user"),
    )
    op.execute(f"GRANT SELECT, INSERT, DELETE ON onboarding_tokens TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("onboarding_tokens")
