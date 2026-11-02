"""Drop the built-in knowledge base: Hudu replaces it

Revision ID: 0037
Revises: 0036

The owner moved knowledge-base content to Hudu; tickets now show Hudu articles instead. Drops
kb_articles (its indexes and grants go with it) and removes the retired kb:read / kb:write strings
from API keys (role permissions live in code, not the database).

Downgrade recreates kb_articles exactly as 0034 created it, empty. The API-key permission strings
are not restored: they no longer grant anything.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0037"
down_revision = "0036"
APP_ROLE = "psa_app"
NOW = sa.text("now()")


def upgrade() -> None:
    op.drop_table("kb_articles")
    op.execute(
        "UPDATE api_keys SET permissions = array_remove(array_remove(permissions, 'kb:read'),"
        " 'kb:write') WHERE permissions && ARRAY['kb:read', 'kb:write']::varchar[]"
    )


def downgrade() -> None:
    # Copied from 0034.upgrade.
    op.create_table(
        "kb_articles",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("visibility", sa.String(10), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="draft"),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("created_by_id", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("updated_by_id", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column(
            "search",
            postgresql.TSVECTOR,
            sa.Computed(
                "setweight(to_tsvector('english', title), 'A') || "
                "setweight(to_tsvector('english', body), 'B')",
                persisted=True,
            ),
        ),
        sa.CheckConstraint("visibility IN ('internal','client')", name="ck_kb_articles_visibility"),
        sa.CheckConstraint(
            "status IN ('draft','published','archived')", name="ck_kb_articles_status"
        ),
    )
    op.create_index("ix_kb_articles_search", "kb_articles", ["search"], postgresql_using="gin")
    op.create_index("ix_kb_articles_status_visibility", "kb_articles", ["status", "visibility"])
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON kb_articles TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
