"""Parity phase 3C: late fees (per-client opt-in, person-approved, billed as a normal charge)

Revision ID: 0022
Revises: 0021
"""
import sqlalchemy as sa

from alembic import op

revision = "0022"
down_revision = "0021"
APP_ROLE = "psa_app"


def upgrade() -> None:
    # Off by default: no percent and no flat fee configured means nothing is ever proposed, and a
    # client must also be opted in.
    op.add_column("settings", sa.Column("late_fee_percent_bp", sa.Integer, nullable=False,
                                        server_default="0"))
    op.add_column("settings", sa.Column("late_fee_flat_cents", sa.BigInteger, nullable=False,
                                        server_default="0"))
    op.add_column("settings", sa.Column("late_fee_grace_days", sa.Integer, nullable=False,
                                        server_default="15"))
    op.add_column("settings", sa.Column("late_fee_max_per_invoice", sa.Integer, nullable=False,
                                        server_default="1"))
    op.create_check_constraint("ck_settings_late_fee", "settings",
                               "late_fee_percent_bp BETWEEN 0 AND 10000 "
                               "AND late_fee_flat_cents BETWEEN 0 AND 100000000 "
                               "AND late_fee_grace_days BETWEEN 0 AND 365 "
                               "AND late_fee_max_per_invoice BETWEEN 1 AND 12")
    op.add_column("organizations", sa.Column("late_fees_enabled", sa.Boolean, nullable=False,
                                             server_default=sa.text("false")))

    op.create_table(
        "late_fee_applications",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("organization_id", sa.BigInteger, sa.ForeignKey("organizations.id"),
                  nullable=False),
        sa.Column("invoice_id", sa.BigInteger, sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("charge_id", sa.BigInteger, sa.ForeignKey("product_charges.id"), nullable=False,
                  unique=True),
        sa.Column("days_overdue", sa.Integer, nullable=False),
        sa.Column("base_cents", sa.BigInteger, nullable=False),
        sa.Column("percent_bp", sa.Integer, nullable=False),
        sa.Column("flat_cents", sa.BigInteger, nullable=False),
        sa.Column("fee_cents", sa.BigInteger, nullable=False),
        sa.Column("applied_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("applied_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.CheckConstraint("fee_cents > 0 AND base_cents > 0", name="ck_late_fee_amounts"),
    )
    op.create_index("ix_late_fee_applications_invoice", "late_fee_applications", ["invoice_id"])
    op.execute(
        """
        CREATE FUNCTION late_fee_applications_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'late fee records are permanent; void the charge instead';
        END $$
        """
    )
    op.execute("CREATE TRIGGER late_fee_applications_guard BEFORE UPDATE OR DELETE ON "
               "late_fee_applications FOR EACH ROW EXECUTE FUNCTION late_fee_applications_guard()")
    op.execute("ALTER TABLE late_fee_applications ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE late_fee_applications FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY org_scope ON late_fee_applications "
               "USING (app_org_visible(organization_id)) "
               "WITH CHECK (app_org_visible(organization_id))")
    op.execute(f"GRANT SELECT, INSERT ON late_fee_applications TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("late_fee_applications")
    op.execute("DROP FUNCTION IF EXISTS late_fee_applications_guard()")
    op.drop_column("organizations", "late_fees_enabled")
    op.drop_constraint("ck_settings_late_fee", "settings")
    for col in ("late_fee_max_per_invoice", "late_fee_grace_days", "late_fee_flat_cents",
                "late_fee_percent_bp"):
        op.drop_column("settings", col)
