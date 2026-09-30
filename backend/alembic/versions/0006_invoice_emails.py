"""Email a finalized invoice to the client through the same review queue

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"

BODY = (
    "Hello {contact_name},\n\nPlease find attached invoice {invoice_number} from {company} for "
    "{invoice_total}, due {due_date}.\n\nIf you have any questions, just reply to this email."
    "\n\nThank you,\n{company}"
)


def upgrade() -> None:
    op.add_column("settings", sa.Column("invoice_email_subject", sa.Text, nullable=False,
                                        server_default="Invoice {invoice_number} from {company}"))
    op.add_column("settings", sa.Column("invoice_email_body", sa.Text, nullable=False,
                                        server_default=BODY))
    op.add_column("settings", sa.Column("auto_prepare_invoice_emails", sa.Boolean,
                                        nullable=False, server_default=sa.text("false")))
    op.add_column("billing_notices", sa.Column("invoice_id", sa.BigInteger,
                                               sa.ForeignKey("invoices.id")))
    op.drop_constraint("ck_notices_kind", "billing_notices")
    op.create_check_constraint("ck_notices_kind", "billing_notices",
                               "kind IN ('reminder','statement','invoice')")
    op.create_check_constraint("ck_notices_invoice", "billing_notices",
                               "kind <> 'invoice' OR invoice_id IS NOT NULL")
    # one invoice email waiting for review per invoice, enforced by the database
    op.execute("CREATE UNIQUE INDEX uq_notices_invoice_pending ON billing_notices (invoice_id) "
               "WHERE kind = 'invoice' AND status = 'pending'")


def downgrade() -> None:
    op.execute("DROP INDEX uq_notices_invoice_pending")
    op.drop_constraint("ck_notices_invoice", "billing_notices")
    op.drop_constraint("ck_notices_kind", "billing_notices")
    op.execute("DELETE FROM billing_notice_invoices WHERE notice_id IN "
               "(SELECT id FROM billing_notices WHERE kind = 'invoice')")
    op.execute("ALTER TABLE billing_notices DISABLE TRIGGER billing_notices_guard")
    op.execute("DELETE FROM billing_notices WHERE kind = 'invoice'")
    op.execute("ALTER TABLE billing_notices ENABLE TRIGGER billing_notices_guard")
    op.create_check_constraint("ck_notices_kind", "billing_notices",
                               "kind IN ('reminder','statement')")
    op.drop_column("billing_notices", "invoice_id")
    for col in ("auto_prepare_invoice_emails", "invoice_email_body", "invoice_email_subject"):
        op.drop_column("settings", col)
