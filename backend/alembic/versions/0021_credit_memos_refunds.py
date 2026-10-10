"""Parity phase 3B: credit memos (numbered, immutable) and refunds against payments

Revision ID: 0021
Revises: 0020

An invoice balance is now  total - payments applied - write-offs - credit memo applications.
The 0004 guards are left untouched; the memo-aware rules are ADDED as separate triggers so the
downgrade only has to drop them.
"""
import sqlalchemy as sa

from alembic import op

revision = "0021"
down_revision = "0020"
APP_ROLE = "psa_app"
TS = dict(server_default=sa.text("now()"), nullable=False)
CLIENT_OWNED = ("credit_memos", "credit_memo_lines", "credit_memo_applications", "refunds")


def _fn(name: str, body: str) -> None:
    op.execute(f"CREATE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql AS $$\n{body}\n$$")


def upgrade() -> None:
    op.create_table(
        "credit_memo_counters",
        sa.Column("year", sa.Integer, primary_key=True),
        sa.Column("last_number", sa.Integer, nullable=False),
    )
    op.create_table(
        "credit_memos",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("organization_id", sa.BigInteger, sa.ForeignKey("organizations.id"),
                  nullable=False),
        sa.Column("number", sa.String(20), nullable=False, unique=True),
        sa.Column("memo_date", sa.Date, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("invoice_id", sa.BigInteger, sa.ForeignKey("invoices.id")),
        sa.Column("subtotal_cents", sa.BigInteger, nullable=False),
        sa.Column("tax_cents", sa.BigInteger, nullable=False),
        sa.Column("total_cents", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(6), nullable=False, server_default="active"),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        sa.Column("voided_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("void_reason", sa.Text),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.CheckConstraint("total_cents > 0 AND total_cents = subtotal_cents + tax_cents",
                           name="ck_credit_memos_total"),
        sa.CheckConstraint("length(btrim(reason)) >= 3", name="ck_credit_memos_reason"),
        sa.CheckConstraint("status IN ('active','void')", name="ck_credit_memos_status"),
        sa.CheckConstraint(
            "status = 'active' OR (voided_at IS NOT NULL AND length(btrim(COALESCE(void_reason, ''))) >= 3)",
            name="ck_credit_memos_void"),
    )
    op.create_index("ix_credit_memos_org", "credit_memos", ["organization_id"])

    op.create_table(
        "credit_memo_lines",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("memo_id", sa.BigInteger, sa.ForeignKey("credit_memos.id"), nullable=False),
        sa.Column("organization_id", sa.BigInteger, nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("quantity", sa.Numeric(12, 4), nullable=False),
        sa.Column("unit_price_cents", sa.BigInteger, nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("tax_rate_bp", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tax_cents", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.CheckConstraint("quantity > 0 AND unit_price_cents > 0 AND amount_cents > 0",
                           name="ck_credit_memo_lines_money"),
        sa.CheckConstraint("tax_rate_bp BETWEEN 0 AND 10000 AND tax_cents >= 0",
                           name="ck_credit_memo_lines_tax"),
    )
    op.create_index("ix_credit_memo_lines_memo", "credit_memo_lines", ["memo_id"])

    op.create_table(
        "credit_memo_applications",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("memo_id", sa.BigInteger, sa.ForeignKey("credit_memos.id"), nullable=False),
        sa.Column("invoice_id", sa.BigInteger, sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("organization_id", sa.BigInteger, nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        sa.Column("voided_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("void_reason", sa.Text),
        sa.CheckConstraint("amount_cents > 0", name="ck_memo_applications_amount"),
        sa.CheckConstraint("voided_at IS NULL OR void_reason IS NOT NULL",
                           name="ck_memo_applications_void"),
    )
    op.create_index("ix_memo_applications_memo", "credit_memo_applications", ["memo_id"])
    op.create_index("ix_memo_applications_invoice", "credit_memo_applications", ["invoice_id"])

    op.create_table(
        "refunds",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("payment_id", sa.BigInteger, sa.ForeignKey("payments.id"), nullable=False),
        sa.Column("organization_id", sa.BigInteger, nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("refunded_on", sa.Date, nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("reference", sa.String(200)),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        sa.Column("voided_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("void_reason", sa.Text),
        sa.CheckConstraint("amount_cents > 0", name="ck_refunds_amount"),
        sa.CheckConstraint("method IN ('check','ach','card','cash','other')",
                           name="ck_refunds_method"),
        sa.CheckConstraint("length(btrim(reason)) >= 3", name="ck_refunds_reason"),
        sa.CheckConstraint("voided_at IS NULL OR void_reason IS NOT NULL", name="ck_refunds_void"),
    )
    op.create_index("ix_refunds_payment", "refunds", ["payment_id"])

    # ---- guards -------------------------------------------------------------------------
    _fn("credit_memos_guard", """
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'credit memos cannot be deleted; void them instead';
  END IF;
  IF OLD.status = 'void' THEN
    RAISE EXCEPTION 'a voided credit memo is immutable';
  END IF;
  IF NEW.status <> 'void'
     OR (to_jsonb(NEW) - 'status' - 'voided_at' - 'voided_by' - 'void_reason')
        IS DISTINCT FROM
        (to_jsonb(OLD) - 'status' - 'voided_at' - 'voided_by' - 'void_reason') THEN
    RAISE EXCEPTION 'a credit memo cannot be edited; void it and issue a new one';
  END IF;
  IF EXISTS (SELECT 1 FROM credit_memo_applications
               WHERE memo_id = OLD.id AND voided_at IS NULL) THEN
    RAISE EXCEPTION 'this credit memo is still applied to invoices; remove those first';
  END IF;
  RETURN NEW;
END""")
    op.execute("CREATE TRIGGER credit_memos_guard BEFORE UPDATE OR DELETE ON credit_memos "
               "FOR EACH ROW EXECUTE FUNCTION credit_memos_guard()")

    _fn("credit_memo_lines_guard", """
BEGIN
  RAISE EXCEPTION 'credit memo lines are immutable';
END""")
    op.execute("CREATE TRIGGER credit_memo_lines_guard BEFORE UPDATE OR DELETE ON "
               "credit_memo_lines FOR EACH ROW EXECUTE FUNCTION credit_memo_lines_guard()")

    _fn("credit_memo_applications_guard", """
DECLARE
  inv RECORD;
  memo RECORD;
  used bigint;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'credit memo applications cannot be deleted; void them instead';
  END IF;
  IF TG_OP = 'UPDATE' THEN
    IF OLD.voided_at IS NOT NULL THEN
      RAISE EXCEPTION 'a voided credit memo application is immutable';
    END IF;
    IF NEW.voided_at IS NULL
       OR (to_jsonb(NEW) - 'voided_at' - 'voided_by' - 'void_reason')
          IS DISTINCT FROM
          (to_jsonb(OLD) - 'voided_at' - 'voided_by' - 'void_reason') THEN
      RAISE EXCEPTION 'a credit memo application can only be voided, not edited';
    END IF;
    RETURN NEW;
  END IF;
  IF NEW.voided_at IS NOT NULL THEN
    RAISE EXCEPTION 'applications must be created active';
  END IF;
  SELECT id, status, organization_id INTO inv FROM invoices WHERE id = NEW.invoice_id FOR UPDATE;
  IF inv.id IS NULL THEN RAISE EXCEPTION 'invoice not found (or not visible)'; END IF;
  IF inv.status <> 'final' THEN
    RAISE EXCEPTION 'credit can only be applied to a finalized invoice';
  END IF;
  SELECT id, status, organization_id, total_cents INTO memo
    FROM credit_memos WHERE id = NEW.memo_id FOR UPDATE;
  IF memo.id IS NULL THEN RAISE EXCEPTION 'credit memo not found (or not visible)'; END IF;
  IF memo.status <> 'active' THEN RAISE EXCEPTION 'cannot apply a voided credit memo'; END IF;
  IF inv.organization_id <> memo.organization_id
     OR NEW.organization_id <> inv.organization_id THEN
    RAISE EXCEPTION 'credit memo and invoice belong to different clients';
  END IF;
  SELECT COALESCE(sum(amount_cents), 0) INTO used FROM credit_memo_applications
    WHERE memo_id = NEW.memo_id AND voided_at IS NULL;
  IF used + NEW.amount_cents > memo.total_cents THEN
    RAISE EXCEPTION 'this would apply more than the credit memo amount';
  END IF;
  RETURN NEW;
END""")
    op.execute("CREATE TRIGGER credit_memo_applications_guard BEFORE INSERT OR UPDATE OR DELETE "
               "ON credit_memo_applications FOR EACH ROW "
               "EXECUTE FUNCTION credit_memo_applications_guard()")

    # An invoice can never be settled past its total by payments + write-offs + credit memos
    # together (the 0004 guards only see payments and write-offs).
    _fn("zz_invoice_settlement_cap", """
DECLARE
  inv_total bigint;
  used bigint;
BEGIN
  SELECT total_cents INTO inv_total FROM invoices WHERE id = NEW.invoice_id FOR UPDATE;
  SELECT (SELECT COALESCE(sum(amount_cents), 0) FROM payment_applications
            WHERE invoice_id = NEW.invoice_id AND voided_at IS NULL)
       + (SELECT COALESCE(sum(amount_cents), 0) FROM write_offs
            WHERE invoice_id = NEW.invoice_id AND voided_at IS NULL)
       + (SELECT COALESCE(sum(amount_cents), 0) FROM credit_memo_applications
            WHERE invoice_id = NEW.invoice_id AND voided_at IS NULL)
    INTO used;
  IF used + NEW.amount_cents > inv_total THEN
    RAISE EXCEPTION 'this would settle more than the invoice balance';
  END IF;
  RETURN NEW;
END""")
    for table in ("payment_applications", "write_offs", "credit_memo_applications"):
        op.execute(f"CREATE TRIGGER zz_{table}_settlement_cap BEFORE INSERT ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION zz_invoice_settlement_cap()")

    # Refunded money can no longer be applied: applied + refunded <= payment amount
    _fn("zz_payment_refund_cap", """
DECLARE
  pay RECORD;
  applied bigint;
  refunded bigint;
BEGIN
  SELECT id, status, organization_id, amount_cents INTO pay
    FROM payments WHERE id = NEW.payment_id FOR UPDATE;
  IF pay.id IS NULL THEN RAISE EXCEPTION 'payment not found (or not visible)'; END IF;
  IF TG_TABLE_NAME = 'refunds' THEN
    IF pay.status <> 'active' THEN RAISE EXCEPTION 'a voided payment cannot be refunded'; END IF;
    IF NEW.voided_at IS NOT NULL THEN RAISE EXCEPTION 'refunds must be created active'; END IF;
    IF NEW.organization_id <> pay.organization_id THEN
      RAISE EXCEPTION 'refund and payment belong to different clients';
    END IF;
  END IF;
  SELECT COALESCE(sum(amount_cents), 0) INTO applied FROM payment_applications
    WHERE payment_id = NEW.payment_id AND voided_at IS NULL;
  SELECT COALESCE(sum(amount_cents), 0) INTO refunded FROM refunds
    WHERE payment_id = NEW.payment_id AND voided_at IS NULL;
  IF applied + refunded + NEW.amount_cents > pay.amount_cents THEN
    RAISE EXCEPTION 'this would use more than the unapplied, unrefunded part of the payment';
  END IF;
  RETURN NEW;
END""")
    for table in ("payment_applications", "refunds"):
        op.execute(f"CREATE TRIGGER zz_{table}_refund_cap BEFORE INSERT ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION zz_payment_refund_cap()")

    _fn("refunds_guard", """
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'refunds cannot be deleted; void them instead';
  END IF;
  IF OLD.voided_at IS NOT NULL THEN
    RAISE EXCEPTION 'a voided refund is immutable';
  END IF;
  IF NEW.voided_at IS NULL
     OR (to_jsonb(NEW) - 'voided_at' - 'voided_by' - 'void_reason')
        IS DISTINCT FROM
        (to_jsonb(OLD) - 'voided_at' - 'voided_by' - 'void_reason') THEN
    RAISE EXCEPTION 'a refund can only be voided, not edited';
  END IF;
  RETURN NEW;
END""")
    op.execute("CREATE TRIGGER refunds_guard BEFORE UPDATE OR DELETE ON refunds "
               "FOR EACH ROW EXECUTE FUNCTION refunds_guard()")

    _fn("zz_payments_refund_void_guard", """
BEGIN
  IF NEW.status = 'void' AND OLD.status = 'active' AND EXISTS (
       SELECT 1 FROM refunds WHERE payment_id = OLD.id AND voided_at IS NULL) THEN
    RAISE EXCEPTION 'this payment has refunds; void those first';
  END IF;
  RETURN NEW;
END""")
    op.execute("CREATE TRIGGER zz_payments_refund_void_guard BEFORE UPDATE ON payments "
               "FOR EACH ROW EXECUTE FUNCTION zz_payments_refund_void_guard()")

    _fn("zz_invoices_memo_void_guard", """
BEGIN
  IF NEW.status = 'void' AND OLD.status = 'final' AND EXISTS (
       SELECT 1 FROM credit_memo_applications
         WHERE invoice_id = OLD.id AND voided_at IS NULL) THEN
    RAISE EXCEPTION 'this invoice has credit memos applied; remove those first';
  END IF;
  RETURN NEW;
END""")
    op.execute("CREATE TRIGGER zz_invoices_memo_void_guard BEFORE UPDATE ON invoices "
               "FOR EACH ROW EXECUTE FUNCTION zz_invoices_memo_void_guard()")

    for table in CLIENT_OWNED:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY org_scope ON {table} USING (app_org_visible(organization_id)) "
                   f"WITH CHECK (app_org_visible(organization_id))")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON credit_memos, credit_memo_applications, "
               f"refunds, credit_memo_counters TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON credit_memo_lines TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS zz_invoices_memo_void_guard ON invoices")
    op.execute("DROP TRIGGER IF EXISTS zz_payments_refund_void_guard ON payments")
    op.execute("DROP TRIGGER IF EXISTS zz_payment_applications_refund_cap ON payment_applications")
    op.execute("DROP TRIGGER IF EXISTS zz_payment_applications_settlement_cap "
               "ON payment_applications")
    op.execute("DROP TRIGGER IF EXISTS zz_write_offs_settlement_cap ON write_offs")
    for table in reversed(CLIENT_OWNED):
        op.drop_table(table)
    op.drop_table("credit_memo_counters")
    for fn in ("zz_invoices_memo_void_guard", "zz_payments_refund_void_guard", "refunds_guard",
               "zz_payment_refund_cap", "zz_invoice_settlement_cap",
               "credit_memo_applications_guard", "credit_memo_lines_guard", "credit_memos_guard"):
        op.execute(f"DROP FUNCTION IF EXISTS {fn}()")
