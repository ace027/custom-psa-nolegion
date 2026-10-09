"""Parity phase 3A: a 'proration' invoice line kind (negative credit for days not covered)

Revision ID: 0020
Revises: 0019
"""
from alembic import op

revision = "0020"
down_revision = "0019"


def upgrade() -> None:
    op.drop_constraint("ck_invoice_lines_kind", "invoice_lines", type_="check")
    op.create_check_constraint(
        "ck_invoice_lines_kind", "invoice_lines",
        "kind IN ('time','product','agreement','manual','proration')")


def downgrade() -> None:
    op.execute("DELETE FROM invoice_lines WHERE kind = 'proration'")
    op.drop_constraint("ck_invoice_lines_kind", "invoice_lines", type_="check")
    op.create_check_constraint(
        "ck_invoice_lines_kind", "invoice_lines",
        "kind IN ('time','product','agreement','manual')")
