"""Email notifications to staff: assigned to me, SLA at risk / breached, customer replied

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
APP_ROLE = "psa_app"


def upgrade() -> None:
    for col in ("notify_assigned", "notify_sla", "notify_reply"):
        op.add_column("users", sa.Column(col, sa.Boolean, nullable=False,
                                         server_default=sa.text("true")))
    op.add_column("settings", sa.Column("notify_staff", sa.Boolean, nullable=False,
                                        server_default=sa.text("true")))
    # No organization_id here on purpose: this is a staff-facing delivery record, not client data.
    op.create_table(
        "staff_notifications",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("ticket_id", sa.BigInteger, sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("event", sa.String(20), nullable=False),
        sa.Column("dedupe_key", sa.String(100), nullable=False),
        sa.Column("email_message_id", sa.BigInteger, sa.ForeignKey("email_messages.id"),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.UniqueConstraint("user_id", "ticket_id", "event", "dedupe_key",
                            name="uq_staff_notifications_once"),
        sa.CheckConstraint("event IN ('assigned','sla_at_risk','sla_breached','customer_reply')",
                           name="ck_staff_notifications_event"),
    )
    op.create_index("ix_staff_notifications_ticket", "staff_notifications", ["ticket_id"])
    op.execute(f"GRANT SELECT, INSERT ON staff_notifications TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("staff_notifications")
    op.drop_column("settings", "notify_staff")
    for col in ("notify_reply", "notify_sla", "notify_assigned"):
        op.drop_column("users", col)
