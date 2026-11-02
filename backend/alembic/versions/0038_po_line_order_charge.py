"""Bill client purchase orders when they are ordered

Revision ID: 0038
Revises: 0037

Owner decision (runbook P10-02): a purchase order linked to a client is billed when it is ordered,
not when the goods are delivered. Ordering creates one ProductCharge per billable line; the line
keeps a link to it so delivery does not charge again and cancelling the order can void it.

- purchase_order_lines.product_charge_id: nullable, unique FK to product_charges. NULL on stock
  orders, non-billable lines, drafts and every line ordered before this migration (those keep
  billing at delivery).

Grants: purchase_order_lines has table-wide SELECT, INSERT, UPDATE for the app role (0031), which
covers the new column.
"""

import sqlalchemy as sa

from alembic import op

revision = "0038"
down_revision = "0037"


def upgrade() -> None:
    op.add_column(
        "purchase_order_lines",
        sa.Column(
            "product_charge_id",
            sa.BigInteger,
            sa.ForeignKey("product_charges.id"),
            unique=True,
        ),
    )


def downgrade() -> None:
    # Charges created at order time are kept; only the link to their line is lost.
    op.drop_column("purchase_order_lines", "product_charge_id")
