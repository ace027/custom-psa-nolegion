"""Integration readiness: UUIDs, RMM client link, asset/ticket sources, note and time types

Revision ID: 0033
Revises: 0032

Columns only (no new table, no RLS or grant change; the app role's table-level INSERT covers the
new columns and ticket_notes / time_entries keep their restricted UPDATE grants):
- organizations, sites, contacts: uuid (NOT NULL, unique, gen_random_uuid()).
- organizations.rmm_client_id: nullable UUID, unique (the future RMM's client id).
- assets.source (manual/rmm/import) and assets.external_id, unique (source, external_id) when set.
  Existing assets with a NinjaOne source row become 'rmm', other synced assets 'import'.
- tickets.source: 'ui' becomes 'manual'; 'api' is new. tickets.external_ref, unique per source
  when set. Automation rule conditions that compare the ticket source to 'ui' now say 'manual'.
- ticket_notes.author_type (human/system/ai); notes with no author user and no author email
  become 'system'.
- time_entries.entry_type (labour/automation); automation time is never billable or invoiced.
- users.entra_tenant_id: the Entra tenant id seen at login.
"""

import json

import sqlalchemy as sa

from alembic import op

revision = "0033"
down_revision = "0032"
UUID_TABLES = ("organizations", "sites", "contacts")
OLD_SOURCES = "source IN ('ui','email','portal','rmm','rule','project')"
# 'project' (0029, set by app/projects.py) stays valid next to the six owner-approved sources
NEW_SOURCES = "source IN ('manual','email','portal','rmm','api','rule','project')"


def _rewrite_rule_conditions(old: str, new: str) -> None:
    """Swap the ticket source value in stored automation conditions (jsonb, done in Python)."""
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, conditions FROM automation_rules")).all()
    for rule_id, conditions in rows:
        changed = False
        for cond in conditions or []:
            if not isinstance(cond, dict) or cond.get("field") != "source":
                continue
            value = cond.get("value")
            if value == old:
                cond["value"], changed = new, True
            elif isinstance(value, list) and old in value:
                cond["value"] = list(dict.fromkeys(new if v == old else v for v in value))
                changed = True
        if changed:
            conn.execute(
                sa.text("UPDATE automation_rules SET conditions = CAST(:c AS jsonb) WHERE id = :i"),
                {"c": json.dumps(conditions), "i": rule_id},
            )


def upgrade() -> None:
    for table in UUID_TABLES:
        op.add_column(
            table,
            sa.Column(
                "uuid",
                sa.UUID,
                nullable=False,
                server_default=sa.text("gen_random_uuid()"),
            ),
        )
        op.create_unique_constraint(f"uq_{table}_uuid", table, ["uuid"])
    op.add_column("organizations", sa.Column("rmm_client_id", sa.UUID))
    op.create_unique_constraint("uq_organizations_rmm_client_id", "organizations", ["rmm_client_id"])

    op.add_column(
        "assets",
        sa.Column("source", sa.String(10), nullable=False, server_default="manual"),
    )
    op.add_column("assets", sa.Column("external_id", sa.String(100)))
    op.create_check_constraint("ck_assets_source", "assets", "source IN ('manual','rmm','import')")
    op.create_index(
        "uq_assets_source_external",
        "assets",
        ["source", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )
    op.execute(
        "UPDATE assets SET source = 'import' "
        "WHERE EXISTS (SELECT 1 FROM asset_sources s WHERE s.asset_id = assets.id)"
    )
    op.execute(
        "UPDATE assets SET source = 'rmm' WHERE EXISTS (SELECT 1 FROM asset_sources s "
        "JOIN integrations i ON i.id = s.integration_id "
        "WHERE s.asset_id = assets.id AND i.kind = 'ninjaone')"
    )

    op.drop_constraint("ck_tickets_source", "tickets", type_="check")
    op.execute("UPDATE tickets SET source = 'manual' WHERE source = 'ui'")
    op.alter_column("tickets", "source", server_default="manual")
    op.create_check_constraint("ck_tickets_source", "tickets", NEW_SOURCES)
    op.add_column("tickets", sa.Column("external_ref", sa.String(200)))
    op.create_index(
        "uq_tickets_source_external_ref",
        "tickets",
        ["source", "external_ref"],
        unique=True,
        postgresql_where=sa.text("external_ref IS NOT NULL"),
    )
    _rewrite_rule_conditions("ui", "manual")

    op.add_column(
        "ticket_notes",
        sa.Column("author_type", sa.String(10), nullable=False, server_default="human"),
    )
    op.create_check_constraint(
        "ck_ticket_notes_author_type", "ticket_notes", "author_type IN ('human','system','ai')"
    )
    op.execute(
        "UPDATE ticket_notes SET author_type = 'system' "
        "WHERE author_user_id IS NULL AND author_email IS NULL"
    )

    op.add_column(
        "time_entries",
        sa.Column("entry_type", sa.String(12), nullable=False, server_default="labour"),
    )
    op.create_check_constraint(
        "ck_time_entries_entry_type", "time_entries", "entry_type IN ('labour','automation')"
    )
    op.create_check_constraint(
        "ck_time_entries_automation_unbilled",
        "time_entries",
        "entry_type <> 'automation' OR (billable = false AND invoice_line_id IS NULL)",
    )

    op.add_column("users", sa.Column("entra_tenant_id", sa.String(64)))


def downgrade() -> None:
    op.drop_column("users", "entra_tenant_id")

    op.drop_constraint("ck_time_entries_automation_unbilled", "time_entries", type_="check")
    op.drop_constraint("ck_time_entries_entry_type", "time_entries", type_="check")
    op.drop_column("time_entries", "entry_type")

    op.drop_constraint("ck_ticket_notes_author_type", "ticket_notes", type_="check")
    op.drop_column("ticket_notes", "author_type")

    _rewrite_rule_conditions("manual", "ui")
    op.drop_index("uq_tickets_source_external_ref", "tickets")
    op.drop_column("tickets", "external_ref")
    op.drop_constraint("ck_tickets_source", "tickets", type_="check")
    op.execute("UPDATE tickets SET source = 'ui' WHERE source IN ('manual','api')")
    op.alter_column("tickets", "source", server_default="ui")
    op.create_check_constraint("ck_tickets_source", "tickets", OLD_SOURCES)

    op.drop_index("uq_assets_source_external", "assets")
    op.drop_constraint("ck_assets_source", "assets", type_="check")
    op.drop_column("assets", "external_id")
    op.drop_column("assets", "source")

    op.drop_constraint("uq_organizations_rmm_client_id", "organizations", type_="unique")
    op.drop_column("organizations", "rmm_client_id")
    for table in reversed(UUID_TABLES):
        op.drop_constraint(f"uq_{table}_uuid", table, type_="unique")
        op.drop_column(table, "uuid")
