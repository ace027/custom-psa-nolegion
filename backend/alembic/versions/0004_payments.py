"""Payment tracking: payments, applications to invoices, write-offs, and DB-level guards

Revision ID: 0004
Revises: 0003

Balance of an invoice is DERIVED (never stored on the frozen invoice):
    balance = invoice.total - active applications - active write-offs
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"

APP_ROLE = "psa_app"
TS = dict(server_default=sa.text("now()"), nullable=False)
TABLES = ("payments", "payment_applications", "write_offs")

# original 0003 definition, restored on downgrade
INVOICES_GUARD_V3 = """
CREATE OR REPLACE FUNCTION invoices_guard() RETURNS trigger LANGUAGE plpgsql AS $$
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

INVOICES_GUARD_V4 = INVOICES_GUARD_V3.replace(
    "    IF (to_jsonb(NEW) - 'status'",
    """    IF EXISTS (SELECT 1 FROM payment_applications
                 WHERE invoice_id = OLD.id AND voided_at IS NULL)
       OR EXISTS (SELECT 1 FROM write_offs WHERE invoice_id = OLD.id AND voided_at IS NULL) THEN
      RAISE EXCEPTION 'this invoice has payments or write-offs applied; void those first';
    END IF;
    IF (to_jsonb(NEW) - 'status'""",
)


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("organization_id", sa.BigInteger, sa.ForeignKey("organizations.id"),
                  nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("received_on", sa.Date, nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("reference", sa.String(200)),
        sa.Column("notes", sa.Text),
        sa.Column("status", sa.String(6), nullable=False, server_default="active"),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        sa.Column("voided_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("void_reason", sa.Text),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.CheckConstraint("amount_cents > 0", name="ck_payments_amount"),
        sa.CheckConstraint("method IN ('check','ach','card','cash','other')",
                           name="ck_payments_method"),
        sa.CheckConstraint("status IN ('active','void')", name="ck_payments_status"),
        sa.CheckConstraint("status = 'active' OR (voided_at IS NOT NULL AND void_reason IS NOT NULL)",
                           name="ck_payments_void"),
    )
    op.create_index("ix_payments_organization_id", "payments", ["organization_id"])

    op.create_table(
        "payment_applications",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("payment_id", sa.BigInteger, sa.ForeignKey("payments.id"), nullable=False),
        sa.Column("invoice_id", sa.BigInteger, sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("organization_id", sa.BigInteger, nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        sa.Column("voided_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("void_reason", sa.Text),
        sa.CheckConstraint("amount_cents > 0", name="ck_applications_amount"),
        sa.CheckConstraint("voided_at IS NULL OR void_reason IS NOT NULL", name="ck_applications_void"),
    )
    op.create_index("ix_applications_payment", "payment_applications", ["payment_id"])
    op.create_index("ix_applications_invoice", "payment_applications", ["invoice_id"])

    op.create_table(
        "write_offs",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("invoice_id", sa.BigInteger, sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("organization_id", sa.BigInteger, nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        sa.Column("voided_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("void_reason", sa.Text),
        sa.CheckConstraint("amount_cents > 0", name="ck_write_offs_amount"),
        sa.CheckConstraint("length(btrim(reason)) >= 3", name="ck_write_offs_reason"),
        sa.CheckConstraint("voided_at IS NULL OR void_reason IS NOT NULL", name="ck_write_offs_void"),
    )
    op.create_index("ix_write_offs_invoice", "write_offs", ["invoice_id"])

    # ---- guards: the database is the source of truth for the money invariants -------------
    op.execute(
        """
        CREATE FUNCTION payments_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'payments cannot be deleted; void them instead';
          END IF;
          IF OLD.status = 'void' THEN
            RAISE EXCEPTION 'a voided payment is immutable';
          END IF;
          IF NEW.status <> 'void'
             OR (to_jsonb(NEW) - 'status' - 'voided_at' - 'voided_by' - 'void_reason')
                IS DISTINCT FROM
                (to_jsonb(OLD) - 'status' - 'voided_at' - 'voided_by' - 'void_reason') THEN
            RAISE EXCEPTION 'a payment cannot be edited; void it and record it again';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute("CREATE TRIGGER payments_guard BEFORE UPDATE OR DELETE ON payments "
               "FOR EACH ROW EXECUTE FUNCTION payments_guard()")

    op.execute(
        """
        CREATE FUNCTION payment_applications_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
          inv RECORD;
          pay RECORD;
          on_invoice bigint;
          from_payment bigint;
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'payment applications cannot be deleted; void them instead';
          END IF;
          IF TG_OP = 'UPDATE' THEN
            IF OLD.voided_at IS NOT NULL THEN
              RAISE EXCEPTION 'a voided payment application is immutable';
            END IF;
            IF NEW.voided_at IS NULL
               OR (to_jsonb(NEW) - 'voided_at' - 'voided_by' - 'void_reason')
                  IS DISTINCT FROM
                  (to_jsonb(OLD) - 'voided_at' - 'voided_by' - 'void_reason') THEN
              RAISE EXCEPTION 'a payment application can only be voided, not edited';
            END IF;
            RETURN NEW;
          END IF;
          -- INSERT: serialize on the invoice and the payment, then re-check the arithmetic
          IF NEW.voided_at IS NOT NULL THEN
            RAISE EXCEPTION 'applications must be created active';
          END IF;
          SELECT id, status, organization_id, total_cents INTO inv
            FROM invoices WHERE id = NEW.invoice_id FOR UPDATE;
          IF inv.id IS NULL THEN RAISE EXCEPTION 'invoice not found (or not visible)'; END IF;
          IF inv.status <> 'final' THEN
            RAISE EXCEPTION 'payments can only be applied to a finalized invoice';
          END IF;
          SELECT id, status, organization_id, amount_cents INTO pay
            FROM payments WHERE id = NEW.payment_id FOR UPDATE;
          IF pay.id IS NULL THEN RAISE EXCEPTION 'payment not found (or not visible)'; END IF;
          IF pay.status <> 'active' THEN RAISE EXCEPTION 'cannot apply a voided payment'; END IF;
          IF inv.organization_id <> pay.organization_id
             OR NEW.organization_id <> inv.organization_id THEN
            RAISE EXCEPTION 'payment and invoice belong to different clients';
          END IF;
          SELECT COALESCE(sum(amount_cents), 0) INTO on_invoice FROM payment_applications
            WHERE invoice_id = NEW.invoice_id AND voided_at IS NULL;
          on_invoice := on_invoice + COALESCE((SELECT sum(amount_cents) FROM write_offs
            WHERE invoice_id = NEW.invoice_id AND voided_at IS NULL), 0);
          IF on_invoice + NEW.amount_cents > inv.total_cents THEN
            RAISE EXCEPTION 'this would apply more than the invoice balance';
          END IF;
          SELECT COALESCE(sum(amount_cents), 0) INTO from_payment FROM payment_applications
            WHERE payment_id = NEW.payment_id AND voided_at IS NULL;
          IF from_payment + NEW.amount_cents > pay.amount_cents THEN
            RAISE EXCEPTION 'this would apply more than the payment amount';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute("CREATE TRIGGER payment_applications_guard BEFORE INSERT OR UPDATE OR DELETE ON "
               "payment_applications FOR EACH ROW EXECUTE FUNCTION payment_applications_guard()")

    op.execute(
        """
        CREATE FUNCTION write_offs_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
          inv RECORD;
          on_invoice bigint;
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'write-offs cannot be deleted; void them instead';
          END IF;
          IF TG_OP = 'UPDATE' THEN
            IF OLD.voided_at IS NOT NULL THEN
              RAISE EXCEPTION 'a voided write-off is immutable';
            END IF;
            IF NEW.voided_at IS NULL
               OR (to_jsonb(NEW) - 'voided_at' - 'voided_by' - 'void_reason')
                  IS DISTINCT FROM
                  (to_jsonb(OLD) - 'voided_at' - 'voided_by' - 'void_reason') THEN
              RAISE EXCEPTION 'a write-off can only be voided, not edited';
            END IF;
            RETURN NEW;
          END IF;
          IF NEW.voided_at IS NOT NULL THEN
            RAISE EXCEPTION 'write-offs must be created active';
          END IF;
          SELECT id, status, organization_id, total_cents INTO inv
            FROM invoices WHERE id = NEW.invoice_id FOR UPDATE;
          IF inv.id IS NULL THEN RAISE EXCEPTION 'invoice not found (or not visible)'; END IF;
          IF inv.status <> 'final' THEN
            RAISE EXCEPTION 'only a finalized invoice can be written off';
          END IF;
          IF NEW.organization_id <> inv.organization_id THEN
            RAISE EXCEPTION 'write-off and invoice belong to different clients';
          END IF;
          SELECT COALESCE(sum(amount_cents), 0) INTO on_invoice FROM payment_applications
            WHERE invoice_id = NEW.invoice_id AND voided_at IS NULL;
          on_invoice := on_invoice + COALESCE((SELECT sum(amount_cents) FROM write_offs
            WHERE invoice_id = NEW.invoice_id AND voided_at IS NULL), 0);
          IF on_invoice + NEW.amount_cents > inv.total_cents THEN
            RAISE EXCEPTION 'this would write off more than the invoice balance';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute("CREATE TRIGGER write_offs_guard BEFORE INSERT OR UPDATE OR DELETE ON write_offs "
               "FOR EACH ROW EXECUTE FUNCTION write_offs_guard()")

    # an invoice with live payments/write-offs cannot be voided out from under them
    op.execute(INVOICES_GUARD_V4)

    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY org_scope ON {table} USING (app_org_visible(organization_id)) "
                   f"WITH CHECK (app_org_visible(organization_id))")
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {APP_ROLE}")  # never DELETE
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.execute(INVOICES_GUARD_V3)
    for table in reversed(TABLES):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_guard ON {table}")
    for fn in ("write_offs_guard", "payment_applications_guard", "payments_guard"):
        op.execute(f"DROP FUNCTION IF EXISTS {fn}()")
    for table in reversed(TABLES):
        op.drop_table(table)
