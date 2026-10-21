"""CRM: leads, opportunity_stages, opportunities, renewal_reminders, renewal settings

Revision ID: 0030
Revises: 0029

leads and opportunity_stages are staff-internal (no organization_id, no RLS). opportunities and
renewal_reminders are client-scoped (organization_id, forced RLS org_scope); their links to quotes
and agreements are composite FKs on (id, organization_id) so a row can never point at another
client's record. CRM amounts are forecast estimates and never bill.
"""

import sqlalchemy as sa

from alembic import op

revision = "0030"
down_revision = "0029"
APP_ROLE = "psa_app"
NOW = sa.text("now()")
SCOPED = ("opportunities", "renewal_reminders")
STAGES = (
    (1, "Qualify", 1000, "open"),
    (2, "Site survey", 2500, "open"),
    (3, "Proposal", 5000, "open"),
    (4, "Negotiation", 7500, "open"),
    (5, "Won", 10000, "won"),
    (6, "Lost", 0, "lost"),
)


def _org_col() -> sa.Column:
    return sa.Column(
        "organization_id", sa.BigInteger, sa.ForeignKey("organizations.id"), nullable=False
    )


def upgrade() -> None:
    op.create_unique_constraint("uq_quotes_id_org", "quotes", ["id", "organization_id"])
    op.create_unique_constraint("uq_agreements_id_org", "agreements", ["id", "organization_id"])

    op.create_table(
        "leads",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("company", sa.String(200)),
        sa.Column("email", sa.String(320)),
        sa.Column("phone", sa.String(50)),
        sa.Column("source", sa.String(100)),
        sa.Column("status", sa.String(20), nullable=False, server_default="new"),
        sa.Column("owner_id", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("notes", sa.Text),
        sa.Column(
            "converted_organization_id", sa.BigInteger, sa.ForeignKey("organizations.id")
        ),
        sa.Column("converted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.CheckConstraint(
            "status IN ('new','contacted','qualified','disqualified','converted')",
            name="ck_leads_status",
        ),
    )
    op.create_index("ix_leads_status", "leads", ["status"])

    op.create_table(
        "opportunity_stages",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("probability_bp", sa.Integer, nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.CheckConstraint(
            "probability_bp BETWEEN 0 AND 10000", name="ck_opportunity_stages_probability"
        ),
        sa.CheckConstraint("kind IN ('open','won','lost')", name="ck_opportunity_stages_kind"),
        sa.UniqueConstraint("name", name="uq_opportunity_stages_name"),
    )
    # at most one active won and one active lost stage (the service keeps at least one)
    op.execute(
        "CREATE UNIQUE INDEX uq_opportunity_stages_active_terminal ON opportunity_stages (kind) "
        "WHERE active AND kind IN ('won','lost')"
    )
    op.bulk_insert(
        sa.table(
            "opportunity_stages",
            sa.column("position", sa.Integer),
            sa.column("name", sa.String),
            sa.column("probability_bp", sa.Integer),
            sa.column("kind", sa.String),
        ),
        [
            {"position": p, "name": n, "probability_bp": bp, "kind": k}
            for p, n, bp, k in STAGES
        ],
    )

    op.create_table(
        "opportunities",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        _org_col(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False, server_default="new"),
        sa.Column(
            "stage_id", sa.BigInteger, sa.ForeignKey("opportunity_stages.id"), nullable=False
        ),
        sa.Column("owner_id", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("monthly_cents", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("term_months", sa.Integer, nullable=False, server_default="12"),
        sa.Column("expected_close_date", sa.Date),
        sa.Column("quote_id", sa.BigInteger),
        sa.Column("agreement_id", sa.BigInteger),
        sa.Column("lost_reason", sa.String(300)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.CheckConstraint("kind IN ('new','renewal','upsell')", name="ck_opportunities_kind"),
        sa.CheckConstraint("monthly_cents >= 0", name="ck_opportunities_monthly"),
        sa.CheckConstraint("term_months BETWEEN 1 AND 120", name="ck_opportunities_term"),
        sa.ForeignKeyConstraint(
            ["quote_id", "organization_id"],
            ["quotes.id", "quotes.organization_id"],
            name="fk_opportunities_quote_org",
        ),
        sa.ForeignKeyConstraint(
            ["agreement_id", "organization_id"],
            ["agreements.id", "agreements.organization_id"],
            name="fk_opportunities_agreement_org",
        ),
        sa.UniqueConstraint("id", "organization_id", name="uq_opportunities_id_org"),
    )
    op.create_index("ix_opportunities_stage", "opportunities", ["stage_id"])
    op.create_index("ix_opportunities_org", "opportunities", ["organization_id"])

    op.create_table(
        "renewal_reminders",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        _org_col(),
        sa.Column("agreement_id", sa.BigInteger, nullable=False),
        sa.Column("lead_days", sa.Integer, nullable=False),
        sa.Column("due_on", sa.Date, nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="open"),
        sa.Column("opportunity_id", sa.BigInteger),
        sa.Column("email_message_id", sa.BigInteger, sa.ForeignKey("email_messages.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.CheckConstraint("lead_days > 0", name="ck_renewal_reminders_lead_days"),
        sa.CheckConstraint(
            "status IN ('open','done','dismissed')", name="ck_renewal_reminders_status"
        ),
        sa.ForeignKeyConstraint(
            ["agreement_id", "organization_id"],
            ["agreements.id", "agreements.organization_id"],
            name="fk_renewal_reminders_agreement_org",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id", "organization_id"],
            ["opportunities.id", "opportunities.organization_id"],
            name="fk_renewal_reminders_opportunity_org",
        ),
        sa.UniqueConstraint("agreement_id", "lead_days", name="uq_renewal_reminders_once"),
    )
    op.create_index("ix_renewal_reminders_status", "renewal_reminders", ["status"])

    op.add_column(
        "settings",
        sa.Column(
            "renewal_reminder_days",
            sa.ARRAY(sa.Integer),
            nullable=False,
            server_default=sa.text("'{90,30}'::integer[]"),
        ),
    )
    op.add_column("settings", sa.Column("renewal_email", sa.String(320)))

    for table in SCOPED:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY org_scope ON {table} "
            "USING (app_org_visible(organization_id)) "
            "WITH CHECK (app_org_visible(organization_id))"
        )
    for table in ("leads", "opportunity_stages", *SCOPED):
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_column("settings", "renewal_email")
    op.drop_column("settings", "renewal_reminder_days")
    op.drop_table("renewal_reminders")
    op.drop_table("opportunities")
    op.drop_table("opportunity_stages")
    op.drop_table("leads")
    op.drop_constraint("uq_agreements_id_org", "agreements", type_="unique")
    op.drop_constraint("uq_quotes_id_org", "quotes", type_="unique")
