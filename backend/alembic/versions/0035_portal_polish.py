"""Portal polish: Entra tenant ids, contact oids, portal-sourced attachments

Revision ID: 0035
Revises: 0034

- organizations.entra_tenant_id: the client's Entra tenant GUID for portal SSO. Unique (case-
  insensitively) among organizations that set one, so a token's tid maps to at most one client.
- contacts.entra_oid: the Entra object id bound on a contact's first portal SSO sign-in. Unique.
- attachments.source ('email' | 'portal'); email_message_id becomes nullable but is still required
  for email-sourced rows (CHECK); uploaded_by_contact_id records the portal uploader.

Grants: contacts and organizations already have table-wide SELECT, INSERT, UPDATE (0001), which
covers the new columns. attachments stay SELECT, INSERT (+ UPDATE (organization_id)) only, so they
remain immutable. The downgrade refuses while portal-sourced attachments exist, because restoring
NOT NULL on email_message_id would otherwise have to delete client files.
"""

import sqlalchemy as sa

from alembic import op

revision = "0035"
down_revision = "0034"


def upgrade() -> None:
    op.add_column("organizations", sa.Column("entra_tenant_id", sa.String(64)))
    op.execute(
        "CREATE UNIQUE INDEX uq_organizations_entra_tenant_id ON organizations "
        "(lower(entra_tenant_id)) WHERE entra_tenant_id IS NOT NULL"
    )

    op.add_column("contacts", sa.Column("entra_oid", sa.String(64)))
    op.execute(
        "CREATE UNIQUE INDEX uq_contacts_entra_oid ON contacts (entra_oid) "
        "WHERE entra_oid IS NOT NULL"
    )

    op.alter_column("attachments", "email_message_id", existing_type=sa.BigInteger, nullable=True)
    op.add_column(
        "attachments",
        sa.Column("source", sa.String(10), nullable=False, server_default="email"),
    )
    op.add_column(
        "attachments",
        sa.Column("uploaded_by_contact_id", sa.BigInteger, sa.ForeignKey("contacts.id")),
    )
    op.create_check_constraint(
        "ck_attachments_source", "attachments", "source IN ('email','portal')"
    )
    op.create_check_constraint(
        "ck_attachments_email_has_message",
        "attachments",
        "source <> 'email' OR email_message_id IS NOT NULL",
    )


def downgrade() -> None:
    portal_files = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM attachments WHERE source <> 'email'"))
        .scalar_one()
    )
    if portal_files:
        raise RuntimeError(
            f"Refusing to downgrade 0035: {portal_files} portal-sourced attachment(s) exist. "
            "Export or remove them deliberately first."
        )
    op.drop_constraint("ck_attachments_email_has_message", "attachments", type_="check")
    op.drop_constraint("ck_attachments_source", "attachments", type_="check")
    op.drop_column("attachments", "uploaded_by_contact_id")
    op.drop_column("attachments", "source")
    op.alter_column("attachments", "email_message_id", existing_type=sa.BigInteger, nullable=False)

    op.execute("DROP INDEX uq_contacts_entra_oid")
    op.drop_column("contacts", "entra_oid")
    op.execute("DROP INDEX uq_organizations_entra_tenant_id")
    op.drop_column("organizations", "entra_tenant_id")
