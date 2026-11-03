"""Accounting sender mailbox and last outbound send error

Revision ID: 0042
Revises: 0041

Columns only (phase 18, plan 18-01):
- settings.accounting_mailbox: address billing notices are sent from (NULL = the support mailbox).
- mailbox_status.last_send_error / last_send_error_at: the last outbound failure, kept as history.

Grants: no change. Existing table-wide SELECT, INSERT, UPDATE grants cover the new columns.
"""

import sqlalchemy as sa

from alembic import op

revision = "0042"
down_revision = "0041"


def upgrade() -> None:
    op.add_column("settings", sa.Column("accounting_mailbox", sa.String(320), nullable=True))
    op.add_column("mailbox_status", sa.Column("last_send_error", sa.Text, nullable=True))
    op.add_column(
        "mailbox_status", sa.Column("last_send_error_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("mailbox_status", "last_send_error_at")
    op.drop_column("mailbox_status", "last_send_error")
    op.drop_column("settings", "accounting_mailbox")
