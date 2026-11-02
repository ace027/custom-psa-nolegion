"""Per-user navigation bookmarks

Revision ID: 0040
Revises: 0039

users.nav_bookmarks holds the ordered page ids pinned on the person's rail (phase 16, mockup C).
NULL means "never changed": the front end shows the role defaults. The users table has no RLS and
the app role already has UPDATE on it; the API only ever writes the signed-in user's own row.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0040"
down_revision = "0039"


def upgrade() -> None:
    op.add_column("users", sa.Column("nav_bookmarks", postgresql.ARRAY(sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "nav_bookmarks")
