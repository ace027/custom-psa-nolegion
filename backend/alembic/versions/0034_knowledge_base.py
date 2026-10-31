"""Knowledge base: kb_articles with full-text search

Revision ID: 0034
Revises: 0033

Articles are the MSP's own content, shared across clients, so the table has no organization_id and
no RLS (like report_schedules). No DELETE grant: articles are archived, never deleted. `search` is
a STORED generated tsvector (title weight A, body weight B) behind a GIN index.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0034"
down_revision = "0033"
APP_ROLE = "psa_app"
NOW = sa.text("now()")


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_table("kb_articles")
