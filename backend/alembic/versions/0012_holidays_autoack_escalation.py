"""Parity phase 1B: holiday calendar, auto-acknowledgement, escalation on SLA breach

Revision ID: 0012
Revises: 0011
"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
APP_ROLE = "psa_app"

ACK_SUBJECT = "[#{ticket_number}] We received your request"
ACK_BODY = (
    "Hello {contact_name},\n\n"
    "Thanks for contacting {company}. We have opened ticket #{ticket_number} and a technician "
    "will respond as soon as possible.\n\n"
    "Reply to this email to add more information to the ticket.\n\n{company}"
)


def _lit(text: str) -> sa.TextClause:
    return sa.text("'" + text.replace("'", "''") + "'")


def upgrade() -> None:
    # MSP-level calendar data, not client data: no RLS.
    op.create_table(
        "holidays",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("on_date", sa.Date, nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("open_minute", sa.Integer),
        sa.Column("close_minute", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_holidays_name"),
        # closed all day (both null) or shortened hours (both set, a real window)
        sa.CheckConstraint(
            "(open_minute IS NULL AND close_minute IS NULL) OR "
            "(open_minute >= 0 AND close_minute <= 1440 AND open_minute < close_minute)",
            name="ck_holidays_hours",
        ),
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON holidays TO {APP_ROLE}")

    op.add_column("settings", sa.Column("auto_ack_enabled", sa.Boolean, nullable=False,
                                        server_default=sa.text("false")))
    op.add_column("settings", sa.Column("auto_ack_subject", sa.Text, nullable=False,
                                        server_default=_lit(ACK_SUBJECT)))
    op.add_column("settings", sa.Column("auto_ack_body", sa.Text, nullable=False,
                                        server_default=_lit(ACK_BODY)))
    op.add_column("settings", sa.Column("escalation_email", sa.String(320)))
    op.add_column("settings", sa.Column("escalation_bump_priority", sa.Boolean, nullable=False,
                                        server_default=sa.text("false")))
    op.add_column("email_messages", sa.Column("auto_generated", sa.Boolean, nullable=False,
                                              server_default=sa.text("false")))

    # Delivery records (like staff_notifications): the unique ticket_id is the once-only guard.
    op.create_table(
        "ticket_auto_acks",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("ticket_id", sa.BigInteger, sa.ForeignKey("tickets.id"), nullable=False,
                  unique=True),
        sa.Column("sent_to", sa.String(320), nullable=False),
        sa.Column("email_message_id", sa.BigInteger, sa.ForeignKey("email_messages.id"),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
    )
    op.create_index("ix_ticket_auto_acks_sent_to", "ticket_auto_acks", ["sent_to", "created_at"])
    op.create_table(
        "ticket_escalations",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("ticket_id", sa.BigInteger, sa.ForeignKey("tickets.id"), nullable=False,
                  unique=True),
        sa.Column("email_message_id", sa.BigInteger, sa.ForeignKey("email_messages.id")),
        sa.Column("bumped_from_priority_id", sa.BigInteger, sa.ForeignKey("priorities.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
    )
    op.execute(f"GRANT SELECT, INSERT ON ticket_auto_acks, ticket_escalations TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("ticket_escalations")
    op.drop_table("ticket_auto_acks")
    op.drop_column("email_messages", "auto_generated")
    for col in ("escalation_bump_priority", "escalation_email", "auto_ack_body",
                "auto_ack_subject", "auto_ack_enabled"):
        op.drop_column("settings", col)
    op.drop_table("holidays")
