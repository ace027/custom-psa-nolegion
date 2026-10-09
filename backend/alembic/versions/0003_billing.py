"""Billing: rates, products, agreements, charges, invoices, billing runs, immutability triggers

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"

APP_ROLE = "psa_app"
TS = dict(server_default=sa.text("now()"), nullable=False)
CLIENT_OWNED = ("org_work_type_rates", "agreements", "agreement_quantity_log", "product_charges",
                "invoices", "invoice_lines")


def _ts():
    return [sa.Column("created_at", sa.DateTime(timezone=True), **TS),
            sa.Column("updated_at", sa.DateTime(timezone=True), **TS)]


def upgrade() -> None:
    # ---- billing fields on existing tables ---------------------------------------------
    op.add_column("organizations", sa.Column("payment_terms_days", sa.Integer, nullable=False,
                                             server_default="30"))
    op.add_column("organizations", sa.Column("tax_rate_bp", sa.Integer, nullable=False,
                                             server_default="0"))  # 825 = 8.25%
    op.create_check_constraint("ck_org_terms", "organizations",
                               "payment_terms_days BETWEEN 0 AND 365")
    op.create_check_constraint("ck_org_tax", "organizations", "tax_rate_bp BETWEEN 0 AND 10000")
    for col in ("company_name", "company_address", "invoice_footer"):
        op.add_column("settings", sa.Column(col, sa.Text))
    op.add_column("work_types", sa.Column("rate_cents", sa.BigInteger))  # NULL = not billable yet
    op.add_column("work_types", sa.Column("taxable", sa.Boolean, nullable=False,
                                          server_default=sa.text("false")))
    op.create_check_constraint("ck_work_types_rate", "work_types",
                               "rate_cents IS NULL OR rate_cents >= 0")

    op.create_table(
        "org_work_type_rates",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("organization_id", sa.BigInteger, sa.ForeignKey("organizations.id"),
                  nullable=False),
        sa.Column("work_type_id", sa.BigInteger, sa.ForeignKey("work_types.id"), nullable=False),
        sa.Column("rate_cents", sa.BigInteger, nullable=False),
        *_ts(),
        sa.UniqueConstraint("organization_id", "work_type_id", name="uq_org_work_type_rate"),
        sa.CheckConstraint("rate_cents >= 0", name="ck_org_rate_nonneg"),
    )

    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("sku", sa.String(64)),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("unit_price_cents", sa.BigInteger, nullable=False),
        sa.Column("cost_cents", sa.BigInteger),
        sa.Column("taxable", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        *_ts(),
        sa.CheckConstraint("unit_price_cents >= 0 AND (cost_cents IS NULL OR cost_cents >= 0)",
                           name="ck_products_money"),
    )
    op.execute("CREATE UNIQUE INDEX uq_products_sku_active ON products (lower(sku)) "
               "WHERE sku IS NOT NULL AND archived_at IS NULL")

    op.create_table(
        "agreements",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("organization_id", sa.BigInteger, sa.ForeignKey("organizations.id"),
                  nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type", sa.String(10), nullable=False),
        sa.Column("unit_price_cents", sa.BigInteger, nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("taxable", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date),
        sa.Column("notes", sa.Text),
        *_ts(),
        sa.CheckConstraint("type IN ('per_user','per_device','flat')", name="ck_agreements_type"),
        sa.CheckConstraint("unit_price_cents >= 0 AND quantity >= 0", name="ck_agreements_money"),
        sa.CheckConstraint("type <> 'flat' OR quantity = 1", name="ck_agreements_flat_qty"),
        sa.CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_agreements_dates"),
    )
    op.create_index("ix_agreements_organization_id", "agreements", ["organization_id"])

    op.create_table(
        "agreement_quantity_log",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("agreement_id", sa.BigInteger, sa.ForeignKey("agreements.id"), nullable=False),
        sa.Column("organization_id", sa.BigInteger, nullable=False),
        sa.Column("old_quantity", sa.Integer),
        sa.Column("new_quantity", sa.Integer, nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("changed_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("changed_at", sa.DateTime(timezone=True), **TS),
    )
    op.create_index("ix_agreement_qty_log_agreement", "agreement_quantity_log", ["agreement_id"])

    op.create_table(
        "billing_runs",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="draft"),
        # run-level notes, e.g. organizations skipped; per-invoice warnings live on the invoices
        sa.Column("warnings", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.Column("reviewed_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("finalized_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("finalized_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('draft','reviewed','finalized','cancelled')",
                           name="ck_runs_status"),
        sa.CheckConstraint("period_end >= period_start", name="ck_runs_period"),
    )
    # One live run per month: this is what makes re-running a period impossible (no double billing)
    op.execute("CREATE UNIQUE INDEX uq_billing_runs_period ON billing_runs (period_start) "
               "WHERE status <> 'cancelled'")

    op.create_table(
        "invoices",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("number", sa.String(20), unique=True),
        sa.Column("organization_id", sa.BigInteger, sa.ForeignKey("organizations.id"),
                  nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="draft"),
        sa.Column("billing_run_id", sa.BigInteger, sa.ForeignKey("billing_runs.id")),
        sa.Column("period_start", sa.Date),
        sa.Column("period_end", sa.Date),
        sa.Column("invoice_date", sa.Date),
        sa.Column("due_date", sa.Date),
        sa.Column("terms_days", sa.Integer),
        sa.Column("subtotal_cents", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("tax_cents", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("total_cents", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("memo", sa.Text),
        sa.Column("warnings", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        # snapshots frozen at finalize so later edits to the org/company never rewrite history
        sa.Column("bill_to_name", sa.String(200)),
        sa.Column("bill_to_address", sa.Text),
        sa.Column("seller_name", sa.Text),
        sa.Column("seller_address", sa.Text),
        sa.Column("footer", sa.Text),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("finalized_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("finalized_at", sa.DateTime(timezone=True)),
        sa.Column("voided_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        sa.Column("void_reason", sa.Text),
        *_ts(),
        sa.CheckConstraint("status IN ('draft','final','void')", name="ck_invoices_status"),
        sa.CheckConstraint("status = 'draft' OR number IS NOT NULL OR voided_at IS NOT NULL",
                           name="ck_invoices_number_when_final"),
        sa.CheckConstraint("status <> 'final' OR (invoice_date IS NOT NULL AND "
                           "due_date IS NOT NULL AND total_cents >= 0)",
                           name="ck_invoices_final_complete"),
        sa.CheckConstraint("total_cents = subtotal_cents + tax_cents", name="ck_invoices_total"),
    )
    op.create_index("ix_invoices_organization_id", "invoices", ["organization_id"])
    op.create_index("ix_invoices_status", "invoices", ["status"])
    op.create_index("ix_invoices_run", "invoices", ["billing_run_id"])

    op.create_table(
        "invoice_lines",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("invoice_id", sa.BigInteger, sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("organization_id", sa.BigInteger, nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("quantity", sa.Numeric(12, 4), nullable=False),
        sa.Column("unit_price_cents", sa.BigInteger, nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("tax_rate_bp", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tax_cents", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("agreement_id", sa.BigInteger, sa.ForeignKey("agreements.id")),
        sa.Column("period_start", sa.Date),
        sa.Column("voided", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.CheckConstraint("kind IN ('time','product','agreement','manual')",
                           name="ck_invoice_lines_kind"),
        sa.CheckConstraint("tax_rate_bp BETWEEN 0 AND 10000", name="ck_invoice_lines_tax"),
    )
    op.create_index("ix_invoice_lines_invoice_id", "invoice_lines", ["invoice_id"])
    # An agreement period can be on at most one LIVE (non-voided) invoice line
    op.execute("CREATE UNIQUE INDEX uq_invoice_lines_agreement_period ON invoice_lines "
               "(agreement_id, period_start) WHERE agreement_id IS NOT NULL AND NOT voided")

    op.create_table(
        "product_charges",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("organization_id", sa.BigInteger, sa.ForeignKey("organizations.id"),
                  nullable=False),
        sa.Column("product_id", sa.BigInteger, sa.ForeignKey("products.id")),
        sa.Column("ticket_id", sa.BigInteger, sa.ForeignKey("tickets.id")),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("quantity", sa.Numeric(12, 4), nullable=False),
        sa.Column("unit_price_cents", sa.BigInteger, nullable=False),  # snapshot of the price
        sa.Column("taxable", sa.Boolean, nullable=False),              # snapshot
        sa.Column("charged_on", sa.Date, nullable=False),
        sa.Column("invoice_line_id", sa.BigInteger, sa.ForeignKey("invoice_lines.id")),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.CheckConstraint("quantity > 0 AND unit_price_cents >= 0", name="ck_charges_money"),
    )
    op.create_index("ix_product_charges_org", "product_charges", ["organization_id"])

    op.add_column("time_entries", sa.Column("invoice_line_id", sa.BigInteger,
                                            sa.ForeignKey("invoice_lines.id")))
    op.create_index("ix_time_entries_invoice_line", "time_entries", ["invoice_line_id"])

    op.create_table(
        "invoice_counters",
        sa.Column("year", sa.Integer, primary_key=True),
        sa.Column("last_number", sa.Integer, nullable=False, server_default="0"),
    )

    # ---- Immutability, enforced IN THE DATABASE (not just in Python) -----------------------
    op.execute(
        """
        CREATE FUNCTION invoices_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'invoices cannot be deleted; void them instead';
          END IF;
          IF OLD.status = 'void' THEN
            RAISE EXCEPTION 'a voided invoice is immutable';
          END IF;
          IF OLD.status = 'final' THEN
            IF NEW.status <> 'void' THEN
              RAISE EXCEPTION 'a finalized invoice is immutable (void it and reissue)';
            END IF;
            IF (to_jsonb(NEW) - 'status' - 'voided_at' - 'voided_by' - 'void_reason' - 'updated_at')
               IS DISTINCT FROM
               (to_jsonb(OLD) - 'status' - 'voided_at' - 'voided_by' - 'void_reason' - 'updated_at') THEN
              RAISE EXCEPTION 'only the void fields may change on a finalized invoice';
            END IF;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute("CREATE TRIGGER invoices_guard BEFORE UPDATE OR DELETE ON invoices "
               "FOR EACH ROW EXECUTE FUNCTION invoices_guard()")

    op.execute(
        """
        CREATE FUNCTION invoice_lines_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE parent_status text;
        BEGIN
          SELECT status INTO parent_status FROM invoices
            WHERE id = CASE WHEN TG_OP = 'INSERT' THEN NEW.invoice_id ELSE OLD.invoice_id END;
          IF parent_status IS NULL THEN
            RAISE EXCEPTION 'invoice not found (or not visible) for this line';
          END IF;
          IF TG_OP IN ('INSERT', 'DELETE') THEN
            IF parent_status <> 'draft' THEN
              RAISE EXCEPTION 'lines can only be added or removed on a draft invoice';
            END IF;
            RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
          END IF;
          IF parent_status = 'draft' THEN
            RETURN NEW;
          END IF;
          IF parent_status = 'void' AND NEW.voided AND NOT OLD.voided
             AND (to_jsonb(NEW) - 'voided') IS NOT DISTINCT FROM (to_jsonb(OLD) - 'voided') THEN
            RETURN NEW;  -- releasing the agreement period when an invoice is voided
          END IF;
          RAISE EXCEPTION 'lines of a finalized or voided invoice are immutable';
        END $$
        """
    )
    op.execute("CREATE TRIGGER invoice_lines_guard BEFORE INSERT OR UPDATE OR DELETE ON "
               "invoice_lines FOR EACH ROW EXECUTE FUNCTION invoice_lines_guard()")

    # ---- RLS on client-owned tables ---------------------------------------------------------
    for table in CLIENT_OWNED:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY org_scope ON {table} USING (app_org_visible(organization_id)) "
                   f"WITH CHECK (app_org_visible(organization_id))")

    # ---- Grants (least privilege) -----------------------------------------------------------
    for table in ("org_work_type_rates", "products", "agreements", "product_charges", "invoices",
                  "invoice_lines", "billing_runs", "invoice_counters"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {APP_ROLE}")
    op.execute(f"GRANT DELETE ON org_work_type_rates, invoice_lines TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON agreement_quantity_log TO {APP_ROLE}")  # append-only
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TRIGGER invoice_lines_guard ON invoice_lines")
    op.execute("DROP TRIGGER invoices_guard ON invoices")
    op.execute("DROP FUNCTION invoice_lines_guard()")
    op.execute("DROP FUNCTION invoices_guard()")
    op.drop_index("ix_time_entries_invoice_line", "time_entries")
    op.drop_column("time_entries", "invoice_line_id")
    for table in ("invoice_counters", "product_charges", "invoice_lines", "invoices",
                  "billing_runs", "agreement_quantity_log", "agreements", "products",
                  "org_work_type_rates"):
        op.drop_table(table)
    op.drop_constraint("ck_work_types_rate", "work_types")
    op.drop_column("work_types", "taxable")
    op.drop_column("work_types", "rate_cents")
    for col in ("invoice_footer", "company_address", "company_name"):
        op.drop_column("settings", col)
    op.drop_constraint("ck_org_tax", "organizations")
    op.drop_constraint("ck_org_terms", "organizations")
    op.drop_column("organizations", "tax_rate_bp")
    op.drop_column("organizations", "payment_terms_days")
