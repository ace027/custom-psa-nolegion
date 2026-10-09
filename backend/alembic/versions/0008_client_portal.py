"""Client portal: contacts with portal access, one-time sign-in links, portal sessions

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
APP_ROLE = "psa_app"


def upgrade() -> None:
    op.add_column("contacts", sa.Column("portal_access", sa.Boolean, nullable=False,
                                        server_default=sa.text("false")))
    op.add_column("contacts", sa.Column("portal_org_tickets", sa.Boolean, nullable=False,
                                        server_default=sa.text("false")))
    op.create_check_constraint("ck_contacts_portal_email", "contacts",
                               "NOT portal_access OR email IS NOT NULL")
    # an email address signs in to at most one client: the sign-in link names no organization
    op.execute("CREATE UNIQUE INDEX uq_contacts_portal_email ON contacts (lower(email)) "
               "WHERE portal_access AND archived_at IS NULL")
    op.add_column("settings", sa.Column("portal_enabled", sa.Boolean, nullable=False,
                                        server_default=sa.text("false")))
    op.drop_constraint("ck_tickets_source", "tickets")
    op.create_check_constraint("ck_tickets_source", "tickets", "source IN ('ui','email','portal')")
    op.drop_constraint("ck_notes_source", "ticket_notes")
    op.create_check_constraint("ck_notes_source", "ticket_notes",
                               "source IN ('ui','email','portal')")

    # Neither table has organization_id: like staff `sessions` they are looked up by secret hash.
    op.create_table(
        "portal_login_tokens",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("contact_id", sa.BigInteger, sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("requested_ip", sa.String(64)),
    )
    op.create_index("ix_portal_tokens_contact", "portal_login_tokens", ["contact_id", "created_at"])
    op.create_table(
        "portal_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("contact_id", sa.BigInteger, sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip", sa.String(64)),
        sa.Column("user_agent", sa.String(300)),
    )
    op.create_index("ix_portal_sessions_contact", "portal_sessions", ["contact_id"])
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON portal_login_tokens TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, DELETE ON portal_sessions TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("portal_sessions")
    op.drop_table("portal_login_tokens")
    op.execute("DELETE FROM ticket_notes WHERE source = 'portal'")  # notes are normally immutable
    op.drop_constraint("ck_notes_source", "ticket_notes")
    op.create_check_constraint("ck_notes_source", "ticket_notes", "source IN ('ui','email')")
    op.execute("UPDATE tickets SET source = 'ui' WHERE source = 'portal'")
    op.drop_constraint("ck_tickets_source", "tickets")
    op.create_check_constraint("ck_tickets_source", "tickets", "source IN ('ui','email')")
    op.drop_column("settings", "portal_enabled")
    op.execute("DROP INDEX uq_contacts_portal_email")
    op.drop_constraint("ck_contacts_portal_email", "contacts")
    op.drop_column("contacts", "portal_org_tickets")
    op.drop_column("contacts", "portal_access")
