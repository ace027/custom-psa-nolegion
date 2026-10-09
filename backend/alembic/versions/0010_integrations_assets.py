"""vCISO Phase 1: vendor integrations, asset inventory, warranty

Revision ID: 0010
Revises: 0009
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0010"
down_revision = "0009"
APP_ROLE = "psa_app"
TS = dict(server_default=sa.text("now()"), nullable=False)
CLIENT_OWNED = ("assets", "asset_sources", "asset_overrides")


def _ts():
    return [sa.Column("created_at", sa.DateTime(timezone=True), **TS),
            sa.Column("updated_at", sa.DateTime(timezone=True), **TS)]


def upgrade() -> None:
    # Per-client publish switch and per-contact flag for the portal "Devices and warranty" page.
    op.add_column("organizations", sa.Column("assets_published", sa.Boolean, nullable=False,
                                             server_default=sa.text("false")))
    op.add_column("contacts", sa.Column("portal_assets", sa.Boolean, nullable=False,
                                        server_default=sa.text("false")))

    # MSP-level (not client data): no organization_id, so no RLS, same as `settings`.
    op.create_table(
        "integrations",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("base_url", sa.String(300), nullable=False),
        sa.Column("credentials", sa.Text),  # Fernet ciphertext only; the key is in the environment
        sa.Column("credentials_set_at", sa.DateTime(timezone=True)),
        sa.Column("config", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("status", sa.String(10), nullable=False, server_default="unknown"),
        sa.Column("last_error", sa.Text),
        sa.Column("last_sync_at", sa.DateTime(timezone=True)),
        sa.Column("sync_requested_at", sa.DateTime(timezone=True)),
        *_ts(),
        sa.CheckConstraint("kind IN ('ninjaone','hudu')", name="ck_integrations_kind"),
        sa.CheckConstraint("status IN ('unknown','ok','error')", name="ck_integrations_status"),
    )
    # psa_organization_id is deliberately NOT called organization_id: this table is MSP-level
    # (an unmapped / ignored vendor client has no organization), so it is outside the RLS guard.
    op.create_table(
        "integration_client_maps",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("integration_id", sa.BigInteger, sa.ForeignKey("integrations.id"),
                  nullable=False),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("external_name", sa.String(300), nullable=False),
        sa.Column("psa_organization_id", sa.BigInteger, sa.ForeignKey("organizations.id")),
        sa.Column("ignored", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), **TS),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), **TS),
        sa.UniqueConstraint("integration_id", "external_id", name="uq_client_map_external"),
        sa.CheckConstraint("NOT (ignored AND psa_organization_id IS NOT NULL)",
                           name="ck_client_map_ignored_or_mapped"),
    )
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("integration_id", sa.BigInteger, sa.ForeignKey("integrations.id"),
                  nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), **TS),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(10), nullable=False, server_default="running"),
        sa.Column("added", sa.Integer, nullable=False, server_default="0"),
        sa.Column("changed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("retired", sa.Integer, nullable=False, server_default="0"),
        sa.Column("clients_synced", sa.Integer, nullable=False, server_default="0"),
        sa.Column("clients_failed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text),
        sa.CheckConstraint("status IN ('running','ok','partial','failed')",
                           name="ck_sync_runs_status"),
    )
    op.create_index("ix_sync_runs_integration", "sync_runs", ["integration_id", "started_at"])

    org = lambda: sa.Column("organization_id", sa.BigInteger,  # noqa: E731
                            sa.ForeignKey("organizations.id"), nullable=False)
    op.create_table(
        "assets",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        org(),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("manufacturer", sa.String(200)),
        sa.Column("model", sa.String(200)),
        sa.Column("serial", sa.String(100)),
        sa.Column("serial_norm", sa.String(100)),
        sa.Column("warranty_start", sa.Date),
        sa.Column("warranty_end", sa.Date),
        sa.Column("conflict", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), **TS),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), **TS),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        *_ts(),
        sa.CheckConstraint("kind IN ('computer','server','network','other')",
                           name="ck_assets_kind"),
    )
    op.create_index("ix_assets_org", "assets", ["organization_id"])
    op.create_index("ix_assets_org_serial", "assets", ["organization_id", "serial_norm"])
    op.create_table(
        "asset_sources",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("asset_id", sa.BigInteger, sa.ForeignKey("assets.id"), nullable=False),
        org(),
        sa.Column("integration_id", sa.BigInteger, sa.ForeignKey("integrations.id"),
                  nullable=False),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("data", JSONB, nullable=False),  # what the vendor reported, normalized
        sa.Column("data_hash", sa.String(64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), **TS),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), **TS),
        sa.UniqueConstraint("integration_id", "external_id", name="uq_asset_source_external"),
    )
    op.create_index("ix_asset_sources_asset", "asset_sources", ["asset_id"])
    op.create_table(
        "asset_overrides",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("asset_id", sa.BigInteger, sa.ForeignKey("assets.id"), nullable=False),
        org(),
        sa.Column("field", sa.String(20), nullable=False),
        sa.Column("value_date", sa.Date, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("users.id")),
        *_ts(),
        sa.UniqueConstraint("asset_id", "field", name="uq_asset_override_field"),
        sa.CheckConstraint("field IN ('warranty_start','warranty_end')",
                           name="ck_asset_overrides_field"),
        sa.CheckConstraint("length(trim(reason)) > 0", name="ck_asset_overrides_reason"),
    )

    for table in CLIENT_OWNED:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY org_scope ON {table} USING (app_org_visible(organization_id)) "
                   f"WITH CHECK (app_org_visible(organization_id))")
    # Assets are never deleted (retire instead); sources and overrides may be removed.
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON assets, integrations, "
               f"integration_client_maps, sync_runs TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON asset_sources, asset_overrides "
               f"TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    for table in ("asset_overrides", "asset_sources", "assets", "sync_runs",
                  "integration_client_maps", "integrations"):
        op.drop_table(table)
    op.drop_column("contacts", "portal_assets")
    op.drop_column("organizations", "assets_published")
