"""Client statements and payment reminders: stages, statements, review queue, attachments

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"

APP_ROLE = "psa_app"
TS = dict(server_default=sa.text("now()"), nullable=False)
CLIENT_OWNED = ("statements", "billing_notices", "billing_notice_invoices", "outbound_attachments")

FRIENDLY = (
    "Hello {contact_name},\n\nThis is a friendly reminder that the following invoice(s) from "
    "{company} are now past due:\n\n{invoice_list}\n\nTotal past due: {total_due}\n\n"
    "If you have already sent payment, thank you, and please disregard this message. If you "
    "have any questions about these invoices, just reply to this email.\n\nThank you,\n{company}"
)
FOLLOW_UP = (
    "Hello {contact_name},\n\nOur records show the following invoice(s) from {company} are "
    "still unpaid and now {oldest_days_late} days past due:\n\n{invoice_list}\n\n"
    "Total past due: {total_due}\n\nPlease arrange payment at your earliest convenience. If "
    "there is a problem with an invoice, or payment is already on its way, let us know by "
    "replying to this email.\n\nThank you,\n{company}"
)
FIRM = (
    "Hello {contact_name},\n\nThis is a second notice. The following invoice(s) from "
    "{company} remain unpaid, {oldest_days_late} days past due:\n\n{invoice_list}\n\n"
    "Total past due: {total_due}\n\nPlease remit payment promptly or contact us today to "
    "discuss. Continued non-payment may affect the services we can provide.\n\n"
    "Thank you,\n{company}"
)
FINAL = (
    "Hello {contact_name},\n\nThis is a final notice regarding the following invoice(s) from "
    "{company}, now {oldest_days_late} days past due:\n\n{invoice_list}\n\n"
    "Total past due: {total_due}\n\nPlease contact us immediately to arrange payment.\n\n"
    "Thank you,\n{company}"
)
STATEMENT_BODY = (
    "Hello {contact_name},\n\nAttached is your account statement from {company} as of "
    "{as_of}.\n\nBalance due: {total_due}\nOf which past due: {overdue_total}\n"
    "Credit on account: {credit}\n\nIf anything looks wrong, just reply to this email.\n\n"
    "Thank you,\n{company}"
)

STAGES = [
    (1, "Friendly reminder", 1, "Friendly reminder: past-due invoice(s) from {company}", FRIENDLY),
    (2, "Follow-up", 15, "Follow-up: unpaid invoice(s) from {company}", FOLLOW_UP),
    (3, "Second notice", 30, "Second notice: past-due invoice(s) from {company}", FIRM),
    (4, "Final notice", 60, "Final notice: seriously past-due invoice(s) from {company}", FINAL),
]


def upgrade() -> None:
    op.add_column("organizations", sa.Column("do_not_remind", sa.Boolean, nullable=False,
                                             server_default=sa.text("false")))
    for col, default in (("statement_subject", "Account statement from {company} as of {as_of}"),
                         ("statement_body", STATEMENT_BODY)):
        op.add_column("settings", sa.Column(col, sa.Text, nullable=False, server_default=default))
    op.add_column("settings", sa.Column("auto_prepare_reminders", sa.Boolean, nullable=False,
                                        server_default=sa.text("true")))
    op.add_column("settings", sa.Column("auto_prepare_statements", sa.Boolean, nullable=False,
                                        server_default=sa.text("true")))
    op.add_column("settings", sa.Column("reminder_min_gap_days", sa.Integer, nullable=False,
                                        server_default="7"))
    op.add_column("settings", sa.Column("reminders_prepared_on", sa.Date))
    op.add_column("settings", sa.Column("statements_prepared_month", sa.Date))
    op.create_check_constraint("ck_settings_gap", "settings",
                               "reminder_min_gap_days BETWEEN 0 AND 90")

    op.create_table(
        "reminder_stages",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("days_past_due", sa.Integer, nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("updated_at", sa.DateTime(timezone=True), **TS),
        sa.CheckConstraint("days_past_due BETWEEN 0 AND 365", name="ck_stages_days"),
    )
    op.create_index("uq_reminder_stages_days", "reminder_stages", ["days_past_due"], unique=True)
    for row in STAGES:
        op.execute(sa.text("INSERT INTO reminder_stages (position, name, days_past_due, subject, "
                           "body) VALUES (:p, :n, :d, :s, :b)").bindparams(
            p=row[0], n=row[1], d=row[2], s=row[3], b=row[4]))

    op.create_table(
        "statements",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("organization_id", sa.BigInteger, sa.ForeignKey("organizations.id"),
                  nullable=False),
        sa.Column("as_of", sa.Date, nullable=False),
        sa.Column("snapshot", JSONB, nullable=False),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
    )
    op.create_index("ix_statements_org", "statements", ["organization_id", "as_of"])

    op.create_table(
        "billing_notices",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("organization_id", sa.BigInteger, sa.ForeignKey("organizations.id"),
                  nullable=False),
        sa.Column("statement_id", sa.BigInteger, sa.ForeignKey("statements.id")),
        sa.Column("stage_id", sa.BigInteger, sa.ForeignKey("reminder_stages.id")),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("manual", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("batch_month", sa.Date),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("body_text", sa.Text, nullable=False),
        sa.Column("to_emails", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("blocked_reason", sa.Text),
        sa.Column("email_message_id", sa.BigInteger, sa.ForeignKey("email_messages.id")),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.Column("decided_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("dismiss_reason", sa.Text),
        sa.CheckConstraint("kind IN ('reminder','statement')", name="ck_notices_kind"),
        sa.CheckConstraint("status IN ('pending','sent','dismissed','expired')",
                           name="ck_notices_status"),
        sa.CheckConstraint("kind <> 'statement' OR statement_id IS NOT NULL",
                           name="ck_notices_statement"),
        sa.CheckConstraint("status <> 'sent' OR email_message_id IS NOT NULL",
                           name="ck_notices_sent_has_email"),
    )
    op.create_index("ix_notices_status", "billing_notices", ["status"])
    op.create_index("ix_notices_org", "billing_notices", ["organization_id"])
    # the monthly batch is idempotent: one automatic statement per client per month
    op.execute("CREATE UNIQUE INDEX uq_notices_statement_batch ON billing_notices "
               "(organization_id, batch_month) WHERE kind = 'statement' AND batch_month IS NOT NULL")

    op.create_table(
        "billing_notice_invoices",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("notice_id", sa.BigInteger, sa.ForeignKey("billing_notices.id"),
                  nullable=False),
        sa.Column("invoice_id", sa.BigInteger, sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("organization_id", sa.BigInteger, nullable=False),
        sa.Column("stage_id", sa.BigInteger, sa.ForeignKey("reminder_stages.id")),
        sa.Column("balance_cents", sa.BigInteger, nullable=False),
        sa.Column("days_past_due", sa.Integer, nullable=False),
    )
    op.create_index("ix_notice_invoices_notice", "billing_notice_invoices", ["notice_id"])
    # each reminder stage is issued at most once per invoice (this is what makes preparing
    # reminders idempotent and stops the same reminder ever being generated twice)
    op.execute("CREATE UNIQUE INDEX uq_notice_invoice_stage ON billing_notice_invoices "
               "(invoice_id, stage_id) WHERE stage_id IS NOT NULL")

    op.create_table(
        "outbound_attachments",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("email_message_id", sa.BigInteger, sa.ForeignKey("email_messages.id"),
                  nullable=False),
        sa.Column("organization_id", sa.BigInteger),
        sa.Column("filename", sa.String(300), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("data", sa.LargeBinary, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
    )
    op.create_index("ix_outbound_att_email", "outbound_attachments", ["email_message_id"])

    # ---- guards: what we told a client is a record, not a draft ---------------------------
    op.execute(
        """
        CREATE FUNCTION statements_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'a statement is a frozen record and cannot be changed or deleted';
        END $$
        """
    )
    op.execute("CREATE TRIGGER statements_guard BEFORE UPDATE OR DELETE ON statements "
               "FOR EACH ROW EXECUTE FUNCTION statements_guard()")
    op.execute(
        """
        CREATE FUNCTION billing_notices_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'billing notices cannot be deleted';
          END IF;
          IF OLD.status <> 'pending' THEN
            RAISE EXCEPTION 'a notice that was sent, dismissed or expired cannot be changed';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute("CREATE TRIGGER billing_notices_guard BEFORE UPDATE OR DELETE ON billing_notices "
               "FOR EACH ROW EXECUTE FUNCTION billing_notices_guard()")
    op.execute(
        """
        CREATE FUNCTION notice_invoices_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE parent text;
        BEGIN
          SELECT status INTO parent FROM billing_notices
            WHERE id = CASE WHEN TG_OP = 'INSERT' THEN NEW.notice_id ELSE OLD.notice_id END;
          IF parent IS DISTINCT FROM 'pending' THEN
            RAISE EXCEPTION 'the invoices on a sent or closed notice cannot be changed';
          END IF;
          RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END $$
        """
    )
    op.execute("CREATE TRIGGER notice_invoices_guard BEFORE INSERT OR UPDATE OR DELETE ON "
               "billing_notice_invoices FOR EACH ROW EXECUTE FUNCTION notice_invoices_guard()")
    op.execute(
        """
        CREATE FUNCTION outbound_attachments_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'outbound attachments are immutable';
        END $$
        """
    )
    op.execute("CREATE TRIGGER outbound_attachments_guard BEFORE UPDATE OR DELETE ON "
               "outbound_attachments FOR EACH ROW EXECUTE FUNCTION outbound_attachments_guard()")

    for table in CLIENT_OWNED:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY org_scope ON {table} USING (app_org_visible(organization_id)) "
                   f"WITH CHECK (app_org_visible(organization_id))")
    op.execute(f"GRANT SELECT, INSERT ON statements, outbound_attachments TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON billing_notices TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON billing_notice_invoices TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, UPDATE ON reminder_stages TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    for table in ("outbound_attachments", "billing_notice_invoices", "billing_notices",
                  "statements"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_guard ON {table}")
    op.execute("DROP TRIGGER IF EXISTS notice_invoices_guard ON billing_notice_invoices")
    for fn in ("outbound_attachments_guard", "notice_invoices_guard", "billing_notices_guard",
               "statements_guard"):
        op.execute(f"DROP FUNCTION IF EXISTS {fn}()")
    for table in ("outbound_attachments", "billing_notice_invoices", "billing_notices",
                  "statements", "reminder_stages"):
        op.drop_table(table)
    op.drop_constraint("ck_settings_gap", "settings")
    for col in ("statements_prepared_month", "reminders_prepared_on", "reminder_min_gap_days",
                "auto_prepare_statements", "auto_prepare_reminders", "statement_body",
                "statement_subject"):
        op.drop_column("settings", col)
    op.drop_column("organizations", "do_not_remind")
