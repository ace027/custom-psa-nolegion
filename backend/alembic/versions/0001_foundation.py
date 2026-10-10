"""Foundation: organizations, sites, contacts, users, sessions, audit_log, RLS

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None

APP_ROLE = "psa_app"  # created outside migrations (deploy/postgres-init, tests/conftest)

TS = dict(server_default=sa.text("now()"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("billing_address", sa.Text),
        sa.Column("notes", sa.Text),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.Column("updated_at", sa.DateTime(timezone=True), **TS),
        sa.CheckConstraint("status IN ('active','inactive')", name="ck_organizations_status"),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_organizations_name_active ON organizations (lower(name)) "
        "WHERE archived_at IS NULL"
    )

    op.create_table(
        "sites",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("organization_id", sa.BigInteger, sa.ForeignKey("organizations.id"),
                  nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("address_line1", sa.String(200)),
        sa.Column("address_line2", sa.String(200)),
        sa.Column("city", sa.String(100)),
        sa.Column("state", sa.String(100)),
        sa.Column("postal_code", sa.String(20)),
        sa.Column("notes", sa.Text),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.Column("updated_at", sa.DateTime(timezone=True), **TS),
    )
    op.create_index("ix_sites_organization_id", "sites", ["organization_id"])

    op.create_table(
        "contacts",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("organization_id", sa.BigInteger, sa.ForeignKey("organizations.id"),
                  nullable=False),
        sa.Column("site_id", sa.BigInteger, sa.ForeignKey("sites.id")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320)),
        sa.Column("phone", sa.String(50)),
        sa.Column("title", sa.String(100)),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("is_billing_contact", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.Column("updated_at", sa.DateTime(timezone=True), **TS),
    )
    op.create_index("ix_contacts_organization_id", "contacts", ["organization_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_contacts_org_email_active ON contacts "
        "(organization_id, lower(email)) WHERE archived_at IS NULL AND email IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_contacts_one_primary_per_org ON contacts (organization_id) "
        "WHERE is_primary AND archived_at IS NULL"
    )

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("entra_oid", sa.String(64), unique=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.Column("updated_at", sa.DateTime(timezone=True), **TS),
        sa.CheckConstraint("role IN ('admin','tech','billing','read_only')", name="ck_users_role"),
    )
    op.execute("CREATE UNIQUE INDEX uq_users_email_lower ON users (lower(email))")

    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip", sa.String(64)),
        sa.Column("user_agent", sa.String(300)),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), **TS),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("actor_id", sa.BigInteger),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(50)),
        sa.Column("entity_id", sa.BigInteger),
        sa.Column("organization_id", sa.BigInteger),
        sa.Column("before", JSONB),
        sa.Column("after", JSONB),
        sa.Column("detail", JSONB),
        sa.Column("request_id", sa.String(64)),
        sa.Column("ip", sa.String(64)),
    )
    op.create_index("ix_audit_log_occurred_at", "audit_log", ["occurred_at"])
    op.create_index("ix_audit_log_organization_id", "audit_log", ["organization_id"])
    op.create_index("ix_audit_entity", "audit_log", ["entity_type", "entity_id"])

    # ---- Row-level security -------------------------------------------------------------
    # The API sets `app.org_scope` per transaction (SET LOCAL semantics via set_config(..,true)):
    #   'all'        -> staff, may see every client
    #   '12' / '1,2' -> only those organization ids (client portal, later)
    #   unset / ''   -> NOTHING (fail closed)
    op.execute(
        """
        CREATE FUNCTION app_org_visible(org bigint) RETURNS boolean
        LANGUAGE sql STABLE AS $$
          SELECT CASE coalesce(current_setting('app.org_scope', true), '')
                   WHEN 'all' THEN true
                   WHEN '' THEN false
                   ELSE org = ANY (string_to_array(current_setting('app.org_scope', true), ',')::bigint[])
                 END
        $$
        """
    )
    for table, col in (("organizations", "id"), ("sites", "organization_id"),
                       ("contacts", "organization_id")):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY org_scope ON {table} USING (app_org_visible({col})) "
            f"WITH CHECK (app_org_visible({col}))"
        )

    # ---- Least-privilege grants for the runtime role -------------------------------------
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    for table in ("organizations", "sites", "contacts", "users"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {APP_ROLE}")  # no DELETE: archive
    op.execute(f"GRANT SELECT, INSERT, DELETE ON sessions TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON audit_log TO {APP_ROLE}")  # append-only
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    for table in ("audit_log", "sessions", "users", "contacts", "sites", "organizations"):
        op.drop_table(table)
    op.execute("DROP FUNCTION app_org_visible(bigint)")
