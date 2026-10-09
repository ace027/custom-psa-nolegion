"""Block-hour / retainer agreements: agreement type 'block' with included minutes, work types
that sit outside blocks, and the part of each time entry a billing run drew from a block

Revision ID: 0023
Revises: 0022
"""
import sqlalchemy as sa

from alembic import op

revision = "0023"
down_revision = "0022"


def upgrade() -> None:
    op.drop_constraint("ck_agreements_type", "agreements", type_="check")
    op.create_check_constraint(
        "ck_agreements_type", "agreements",
        "type IN ('per_user','per_device','flat','block')")
    op.add_column("agreements", sa.Column("block_minutes", sa.Integer, nullable=True))
    op.create_check_constraint(
        "ck_agreements_block", "agreements",
        "((type = 'block') = (block_minutes IS NOT NULL)) "
        "AND (block_minutes IS NULL OR block_minutes > 0)")

    op.add_column("work_types", sa.Column("block_covered", sa.Boolean, nullable=False,
                                          server_default=sa.text("true")))

    op.add_column("time_entries", sa.Column("block_minutes_covered", sa.Integer, nullable=False,
                                            server_default="0"))
    op.create_check_constraint(
        "ck_time_entries_block_covered", "time_entries",
        "block_minutes_covered >= 0 AND block_minutes_covered <= minutes_billable")


def downgrade() -> None:
    # Never delete agreements (they own invoice history): refuse while any block agreement exists.
    bind = op.get_bind()
    n = bind.execute(sa.text("SELECT count(*) FROM agreements WHERE type = 'block'")).scalar_one()
    if n:
        raise RuntimeError(
            f"cannot downgrade 0023: {n} block agreement(s) exist; change or remove them first")

    op.drop_constraint("ck_time_entries_block_covered", "time_entries", type_="check")
    op.drop_column("time_entries", "block_minutes_covered")
    op.drop_column("work_types", "block_covered")
    op.drop_constraint("ck_agreements_block", "agreements", type_="check")
    op.drop_column("agreements", "block_minutes")
    op.drop_constraint("ck_agreements_type", "agreements", type_="check")
    op.create_check_constraint(
        "ck_agreements_type", "agreements",
        "type IN ('per_user','per_device','flat')")
