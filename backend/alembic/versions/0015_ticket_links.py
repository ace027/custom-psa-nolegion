"""Parity phase 1D (part 1): links between tickets

Revision ID: 0015
Revises: 0014
"""
import sqlalchemy as sa

from alembic import op

revision = "0015"
down_revision = "0014"
APP_ROLE = "psa_app"


def upgrade() -> None:
    op.create_table(
        "ticket_links",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("organization_id", sa.BigInteger, sa.ForeignKey("organizations.id"),
                  nullable=False),
        sa.Column("source_ticket_id", sa.BigInteger, sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("target_ticket_id", sa.BigInteger, sa.ForeignKey("tickets.id"), nullable=False),
        # related: symmetric. duplicate_of: source is the duplicate, target the original.
        # parent_of: source is the parent, target the child.
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.CheckConstraint("kind IN ('related','duplicate_of','parent_of')",
                           name="ck_ticket_links_kind"),
        sa.CheckConstraint("source_ticket_id <> target_ticket_id", name="ck_ticket_links_self"),
    )
    op.create_index("ix_ticket_links_org", "ticket_links", ["organization_id"])
    op.create_index("ix_ticket_links_source", "ticket_links", ["source_ticket_id"])
    op.create_index("ix_ticket_links_target", "ticket_links", ["target_ticket_id"])
    # one link per pair of tickets, whichever way round; a ticket is a duplicate of at most one
    # original and has at most one parent
    op.execute("CREATE UNIQUE INDEX uq_ticket_links_pair ON ticket_links "
               "(LEAST(source_ticket_id, target_ticket_id), "
               "GREATEST(source_ticket_id, target_ticket_id))")
    op.execute("CREATE UNIQUE INDEX uq_ticket_links_one_original ON ticket_links "
               "(source_ticket_id) WHERE kind = 'duplicate_of'")
    op.execute("CREATE UNIQUE INDEX uq_ticket_links_one_parent ON ticket_links "
               "(target_ticket_id) WHERE kind = 'parent_of'")
    op.execute("ALTER TABLE ticket_links ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ticket_links FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY org_scope ON ticket_links USING (app_org_visible(organization_id)) "
               "WITH CHECK (app_org_visible(organization_id))")
    # links may be removed again (audited); they carry no money or history of their own
    op.execute(f"GRANT SELECT, INSERT, DELETE ON ticket_links TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("ticket_links")
