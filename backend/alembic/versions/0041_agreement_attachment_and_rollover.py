"""Agreement attachment on tickets and time, plus all-inclusive and rollover agreement settings

Revision ID: 0041
Revises: 0040

Columns only, no backfill (phase 17, plan 17-01):
- tickets.agreement_id and time_entries.agreement_id: nullable FKs to agreements, indexed.
  NULL = no agreement, which keeps today's billing behaviour exactly.
- agreements.all_inclusive (only true on type 'flat'), agreements.rollover ('expire' | 'roll')
  and agreements.rollover_cap_minutes (NULL = no cap, else > 0). Defaults match today.

Grants: no change. 0002 granted SELECT, INSERT, UPDATE table-wide on tickets and time_entries,
and 0003 did the same on agreements, so the app role can already read and write the new columns.
RLS policies are row-level and cover the new columns as they are.
"""

import sqlalchemy as sa

from alembic import op

revision = "0041"
down_revision = "0040"


def upgrade() -> None:
    for table in ("tickets", "time_entries"):
        op.add_column(
            table,
            sa.Column("agreement_id", sa.BigInteger, sa.ForeignKey("agreements.id"), nullable=True),
        )
        op.create_index(f"ix_{table}_agreement_id", table, ["agreement_id"])

    op.add_column(
        "agreements",
        sa.Column("all_inclusive", sa.Boolean, nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "agreements",
        sa.Column("rollover", sa.String(10), nullable=False, server_default="expire"),
    )
    op.add_column("agreements", sa.Column("rollover_cap_minutes", sa.Integer, nullable=True))
    op.create_check_constraint(
        "ck_agreements_rollover", "agreements", "rollover IN ('expire','roll')"
    )
    op.create_check_constraint(
        "ck_agreements_rollover_cap", "agreements", "rollover_cap_minutes > 0"
    )
    op.create_check_constraint(
        "ck_agreements_all_inclusive_flat", "agreements", "NOT all_inclusive OR type = 'flat'"
    )


def downgrade() -> None:
    op.drop_constraint("ck_agreements_all_inclusive_flat", "agreements", type_="check")
    op.drop_constraint("ck_agreements_rollover_cap", "agreements", type_="check")
    op.drop_constraint("ck_agreements_rollover", "agreements", type_="check")
    op.drop_column("agreements", "rollover_cap_minutes")
    op.drop_column("agreements", "rollover")
    op.drop_column("agreements", "all_inclusive")
    for table in ("time_entries", "tickets"):
        op.drop_index(f"ix_{table}_agreement_id", table)
        op.drop_column(table, "agreement_id")
