"""Parity phase 2C: expenses, mileage and receipts

Revision ID: 0019
Revises: 0018
"""
import sqlalchemy as sa

from alembic import op

revision = "0019"
down_revision = "0018"
APP_ROLE = "psa_app"


def _stamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
    ]


def upgrade() -> None:
    # Mileage rate in WHOLE cents per mile. 0 (the default) means "not configured yet": entering
    # mileage is refused until it is set, so a trip is never silently worth $0.
    op.add_column("settings", sa.Column("mileage_rate_cents", sa.Integer, nullable=False,
                                        server_default="0"))
    op.create_check_constraint("ck_settings_mileage_rate", "settings",
                               "mileage_rate_cents BETWEEN 0 AND 10000")

    op.create_table(
        "expense_categories",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        *_stamps(),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_expense_categories_name"),
    )
    op.create_index("uq_expense_categories_name_active", "expense_categories",
                    [sa.text("lower(name)")], unique=True,
                    postgresql_where=sa.text("archived_at IS NULL"))
    op.execute("INSERT INTO expense_categories (name) VALUES ('Travel'), ('Meals'), "
               "('Parts and supplies'), ('Software and subscriptions'), ('Other')")

    op.create_table(
        "expenses",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expense_date", sa.Date, nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("category_id", sa.BigInteger, sa.ForeignKey("expense_categories.id")),
        sa.Column("description", sa.Text, nullable=False),
        # mileage: miles and the per-mile rate copied from Settings when entered
        sa.Column("miles", sa.Numeric(8, 2)),
        sa.Column("mileage_rate_cents", sa.Integer),
        # what it COST (and what the person is reimbursed). The client price adds the markup.
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("reimbursable", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("billable", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("taxable", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("markup_bp", sa.Integer, nullable=False, server_default="0"),
        sa.Column("organization_id", sa.BigInteger, sa.ForeignKey("organizations.id")),
        sa.Column("ticket_id", sa.BigInteger, sa.ForeignKey("tickets.id")),
        sa.Column("invoice_line_id", sa.BigInteger, sa.ForeignKey("invoice_lines.id")),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        *_stamps(),
        sa.CheckConstraint("kind IN ('expense','mileage')", name="ck_expenses_kind"),
        sa.CheckConstraint("amount_cents > 0", name="ck_expenses_amount"),
        sa.CheckConstraint("markup_bp BETWEEN 0 AND 100000", name="ck_expenses_markup"),
        sa.CheckConstraint(
            # COALESCE: a NULL miles must FAIL the check, not slip through as "unknown"
            "COALESCE((kind = 'mileage' AND miles > 0 AND mileage_rate_cents > 0) OR "
            "(kind = 'expense' AND miles IS NULL AND mileage_rate_cents IS NULL "
            "AND category_id IS NOT NULL), false)", name="ck_expenses_kind_fields"),
        sa.CheckConstraint("NOT billable OR organization_id IS NOT NULL",
                           name="ck_expenses_billable_has_client"),
        sa.CheckConstraint("ticket_id IS NULL OR organization_id IS NOT NULL",
                           name="ck_expenses_ticket_has_client"),
        sa.CheckConstraint("invoice_line_id IS NULL OR billable", name="ck_expenses_invoiced"),
    )
    op.create_index("ix_expenses_user_date", "expenses", ["user_id", "expense_date"])
    op.create_index("ix_expenses_unbilled", "expenses", ["organization_id", "expense_date"],
                    postgresql_where=sa.text("billable AND invoice_line_id IS NULL "
                                             "AND voided_at IS NULL"))

    op.create_table(
        "expense_receipts",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("expense_id", sa.BigInteger, sa.ForeignKey("expenses.id"), nullable=False),
        sa.Column("organization_id", sa.BigInteger),
        sa.Column("filename", sa.String(300), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(300), nullable=False),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
    )
    op.create_index("ix_expense_receipts_expense", "expense_receipts", ["expense_id"])

    for table in ("expenses", "expense_receipts"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY org_scope ON {table} USING (app_org_visible(organization_id)) "
                   f"WITH CHECK (app_org_visible(organization_id))")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON expense_categories, expenses TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON expense_receipts TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("expense_receipts")
    op.drop_table("expenses")
    op.drop_table("expense_categories")
    op.drop_constraint("ck_settings_mileage_rate", "settings")
    op.drop_column("settings", "mileage_rate_cents")
