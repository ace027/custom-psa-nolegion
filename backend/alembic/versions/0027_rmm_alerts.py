"""RMM alerts to tickets: rmm_alerts, tickets.asset_id, ticket source 'rmm'

Revision ID: 0027
Revises: 0026

rmm_alerts is client-scoped like asset_sources: organization_id with forced RLS. One open row per
(integration, condition); repeats bump `occurrences`. Asset and ticket links are composite FKs on
(id, organization_id) so an alert can never point at another client's asset or ticket.
"""

import sqlalchemy as sa

from alembic import op

revision = "0027"
down_revision = "0026"
APP_ROLE = "psa_app"
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_unique_constraint("uq_assets_id_org", "assets", ["id", "organization_id"])

    op.add_column("tickets", sa.Column("asset_id", sa.BigInteger, nullable=True))
    op.create_foreign_key(
        "fk_tickets_asset_org",
        "tickets",
        "assets",
        ["asset_id", "organization_id"],
        ["id", "organization_id"],
    )
    op.create_index("ix_tickets_asset", "tickets", ["asset_id"])
    op.drop_constraint("ck_tickets_source", "tickets", type_="check")
    op.create_check_constraint(
        "ck_tickets_source", "tickets", "source IN ('ui','email','portal','rmm')"
    )

    op.add_column("integrations", sa.Column("alerts_polled_at", sa.DateTime(timezone=True)))
    op.add_column("integrations", sa.Column("alerts_requested_at", sa.DateTime(timezone=True)))
    op.add_column("integrations", sa.Column("alerts_last_error", sa.Text))

    op.create_table(
        "rmm_alerts",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column(
            "organization_id", sa.BigInteger, sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column(
            "integration_id", sa.BigInteger, sa.ForeignKey("integrations.id"), nullable=False
        ),
        sa.Column("external_id", sa.Text, nullable=False),
        sa.Column("condition_key", sa.Text, nullable=False),
        sa.Column("device_external_id", sa.Text, nullable=False),
        sa.Column("asset_id", sa.BigInteger, nullable=False),
        sa.Column("ticket_id", sa.BigInteger),
        sa.Column("severity", sa.Text, nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False, server_default="open"),
        sa.Column("occurrences", sa.Integer, nullable=False, server_default="1"),
        sa.Column("missed_polls", sa.Integer, nullable=False, server_default="0"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("cleared_at", sa.DateTime(timezone=True)),
        sa.Column("resolution", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.CheckConstraint("state IN ('open','cleared')", name="ck_rmm_alerts_state"),
        sa.CheckConstraint(
            "severity IN ('NONE','MINOR','MODERATE','MAJOR','CRITICAL')",
            name="ck_rmm_alerts_severity",
        ),
        sa.CheckConstraint(
            "resolution IS NULL OR resolution IN ('resolved','noted','none','superseded')",
            name="ck_rmm_alerts_resolution",
        ),
        sa.CheckConstraint("(state = 'open') = (cleared_at IS NULL)", name="ck_rmm_alerts_cleared"),
        sa.CheckConstraint("occurrences >= 1", name="ck_rmm_alerts_occurrences"),
        sa.CheckConstraint("missed_polls >= 0", name="ck_rmm_alerts_missed_polls"),
        sa.ForeignKeyConstraint(
            ["asset_id", "organization_id"],
            ["assets.id", "assets.organization_id"],
            name="fk_rmm_alerts_asset_org",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id", "organization_id"],
            ["tickets.id", "tickets.organization_id"],
            name="fk_rmm_alerts_ticket_org",
        ),
    )
    op.create_index(
        "uq_rmm_alerts_open",
        "rmm_alerts",
        ["integration_id", "condition_key"],
        unique=True,
        postgresql_where=sa.text("state = 'open'"),
    )
    op.create_index(
        "ix_rmm_alerts_condition", "rmm_alerts", ["integration_id", "condition_key", "created_at"]
    )
    op.create_index("ix_rmm_alerts_ticket", "rmm_alerts", ["ticket_id"])

    op.execute("ALTER TABLE rmm_alerts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE rmm_alerts FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY org_scope ON rmm_alerts "
        "USING (app_org_visible(organization_id)) "
        "WITH CHECK (app_org_visible(organization_id))"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON rmm_alerts TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("rmm_alerts")
    op.drop_column("integrations", "alerts_last_error")
    op.drop_column("integrations", "alerts_requested_at")
    op.drop_column("integrations", "alerts_polled_at")
    op.execute("UPDATE tickets SET source = 'ui' WHERE source = 'rmm'")
    op.drop_constraint("ck_tickets_source", "tickets", type_="check")
    op.create_check_constraint("ck_tickets_source", "tickets", "source IN ('ui','email','portal')")
    op.drop_index("ix_tickets_asset", table_name="tickets")
    op.drop_constraint("fk_tickets_asset_org", "tickets", type_="foreignkey")
    op.drop_column("tickets", "asset_id")
    op.drop_constraint("uq_assets_id_org", "assets", type_="unique")
