"""New-client quoting: prospects, onsite surveys, rate card, quotes

Revision ID: 0009
Revises: 0008
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
APP_ROLE = "psa_app"
TS = dict(server_default=sa.text("now()"), nullable=False)
CLIENT_OWNED = ("site_surveys", "survey_devices", "survey_apps", "quotes")


def _ts():
    return [sa.Column("created_at", sa.DateTime(timezone=True), **TS),
            sa.Column("updated_at", sa.DateTime(timezone=True), **TS)]


def upgrade() -> None:
    op.drop_constraint("ck_organizations_status", "organizations")
    op.create_check_constraint("ck_organizations_status", "organizations",
                               "status IN ('active','inactive','prospect')")

    # Rate card and uplift percentages: one MSP-level row, like `settings` (not client data).
    op.create_table(
        "quote_settings",
        sa.Column("id", sa.SmallInteger, primary_key=True),
        sa.Column("per_user_rate_cents", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("workstation_rate_cents", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("server_rate_cents", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("network_rate_cents", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("other_rate_cents", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("hardware_uplift_bp", sa.Integer, nullable=False, server_default="2500"),
        sa.Column("server_uplift_bp", sa.Integer, nullable=False, server_default="0"),
        sa.Column("legacy_app_uplift_bp", sa.Integer, nullable=False, server_default="0"),
        sa.Column("term_months", sa.Integer, nullable=False, server_default="12"),
        sa.Column("valid_days", sa.Integer, nullable=False, server_default="30"),
        sa.Column("agreement_taxable", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("intro_text", sa.Text),
        sa.Column("updated_at", sa.DateTime(timezone=True), **TS),
        sa.CheckConstraint("id = 1", name="ck_quote_settings_single"),
        sa.CheckConstraint(
            "per_user_rate_cents >= 0 AND workstation_rate_cents >= 0 AND server_rate_cents >= 0 "
            "AND network_rate_cents >= 0 AND other_rate_cents >= 0", name="ck_quote_rates"),
        sa.CheckConstraint(
            "hardware_uplift_bp BETWEEN 0 AND 100000 AND server_uplift_bp BETWEEN 0 AND 100000 "
            "AND legacy_app_uplift_bp BETWEEN 0 AND 100000", name="ck_quote_uplifts"),
        sa.CheckConstraint("term_months BETWEEN 1 AND 120 AND valid_days BETWEEN 1 AND 365",
                           name="ck_quote_terms"),
    )
    op.execute("INSERT INTO quote_settings (id) VALUES (1)")

    org = lambda: sa.Column("organization_id", sa.BigInteger,  # noqa: E731
                            sa.ForeignKey("organizations.id"), nullable=False)
    op.create_table(
        "site_surveys",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        org(),
        sa.Column("status", sa.String(12), nullable=False, server_default="scheduled"),
        sa.Column("scheduled_for", sa.DateTime(timezone=True)),
        sa.Column("tech_id", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("user_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("site_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("notes", sa.Text),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("users.id")),
        *_ts(),
        sa.CheckConstraint("status IN ('scheduled','in_progress','completed')",
                           name="ck_surveys_status"),
        sa.CheckConstraint("user_count >= 0 AND site_count >= 0", name="ck_surveys_counts"),
    )
    op.create_index("ix_site_surveys_org", "site_surveys", ["organization_id"])
    op.create_table(
        "survey_devices",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("survey_id", sa.BigInteger, sa.ForeignKey("site_surveys.id"), nullable=False),
        org(),
        sa.Column("device_class", sa.String(12), nullable=False),
        sa.Column("label", sa.String(200)),
        sa.Column("make_model", sa.String(200)),
        sa.Column("serial", sa.String(100)),
        sa.Column("warranty_end", sa.Date),
        sa.Column("warranty_status", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("priced", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text),
        sa.CheckConstraint("device_class IN ('workstation','server','network','other')",
                           name="ck_survey_devices_class"),
        sa.CheckConstraint("warranty_status IN ('in_warranty','out_of_warranty','unknown')",
                           name="ck_survey_devices_warranty"),
    )
    op.create_index("ix_survey_devices_survey", "survey_devices", ["survey_id"])
    op.create_table(
        "survey_apps",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("survey_id", sa.BigInteger, sa.ForeignKey("site_surveys.id"), nullable=False),
        org(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("vendor", sa.String(200)),
        sa.Column("legacy", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text),
    )
    op.create_index("ix_survey_apps_survey", "survey_apps", ["survey_id"])

    op.create_table(
        "quotes",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        org(),
        sa.Column("survey_id", sa.BigInteger, sa.ForeignKey("site_surveys.id"), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False, server_default="new"),
        sa.Column("agreement_id", sa.BigInteger, sa.ForeignKey("agreements.id")),  # reprice target
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("replaces_quote_id", sa.BigInteger, sa.ForeignKey("quotes.id")),
        sa.Column("status", sa.String(14), nullable=False, server_default="draft"),
        sa.Column("snapshot", JSONB, nullable=False),  # rates, counts, factors: frozen at creation
        sa.Column("base_cents", sa.BigInteger, nullable=False),
        sa.Column("uplift_bp", sa.Integer, nullable=False),
        sa.Column("computed_price_cents", sa.BigInteger, nullable=False),
        sa.Column("final_price_cents", sa.BigInteger, nullable=False),
        sa.Column("adjustment_reason", sa.Text),
        sa.Column("adjusted_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("term_months", sa.Integer, nullable=False),
        sa.Column("valid_until", sa.Date),
        sa.Column("effective_date", sa.Date),
        sa.Column("notes", sa.Text),
        sa.Column("decision_note", sa.Text),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("approved_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("sent_to", sa.Text),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decided_by", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("resulting_agreement_id", sa.BigInteger, sa.ForeignKey("agreements.id")),
        sa.Column("created_by", sa.BigInteger, sa.ForeignKey("users.id")),
        *_ts(),
        sa.CheckConstraint("kind IN ('new','reprice')", name="ck_quotes_kind"),
        sa.CheckConstraint(
            "status IN ('draft','needs_approval','approved','sent','accepted','declined',"
            "'cancelled')", name="ck_quotes_status"),
        sa.CheckConstraint(
            "base_cents >= 0 AND computed_price_cents >= 0 AND final_price_cents >= 0 "
            "AND uplift_bp >= 0 AND term_months > 0", name="ck_quotes_money"),
        sa.CheckConstraint("kind <> 'reprice' OR agreement_id IS NOT NULL",
                           name="ck_quotes_reprice_agreement"),
        sa.CheckConstraint(
            "final_price_cents = computed_price_cents OR (adjustment_reason IS NOT NULL "
            "AND adjusted_by IS NOT NULL)", name="ck_quotes_adjustment_reason"),
    )
    op.create_index("ix_quotes_org", "quotes", ["organization_id"])
    op.create_index("ix_quotes_status", "quotes", ["status"])
    # one live (not yet decided) quote per survey keeps "which one is current" unambiguous
    op.execute("CREATE UNIQUE INDEX uq_quotes_survey_open ON quotes (survey_id) WHERE status IN "
               "('draft','needs_approval','approved','sent')")

    op.execute(
        """
        CREATE FUNCTION quotes_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'quotes are never deleted; cancel them instead';
          END IF;
          IF OLD.status IN ('accepted','declined','cancelled') THEN
            RAISE EXCEPTION 'a % quote is final', OLD.status;
          END IF;
          IF OLD.status = 'sent' THEN
            IF NEW.status NOT IN ('sent','accepted','declined','cancelled') THEN
              RAISE EXCEPTION 'a sent quote can only be accepted, declined or cancelled';
            END IF;
            IF (NEW.organization_id, NEW.survey_id, NEW.kind, NEW.agreement_id, NEW.version,
                NEW.replaces_quote_id, NEW.snapshot::text, NEW.base_cents, NEW.uplift_bp,
                NEW.computed_price_cents, NEW.final_price_cents, NEW.adjustment_reason,
                NEW.adjusted_by, NEW.term_months, NEW.valid_until, NEW.approved_by,
                NEW.approved_at, NEW.sent_at, NEW.sent_to)
               IS DISTINCT FROM
               (OLD.organization_id, OLD.survey_id, OLD.kind, OLD.agreement_id, OLD.version,
                OLD.replaces_quote_id, OLD.snapshot::text, OLD.base_cents, OLD.uplift_bp,
                OLD.computed_price_cents, OLD.final_price_cents, OLD.adjustment_reason,
                OLD.adjusted_by, OLD.term_months, OLD.valid_until, OLD.approved_by,
                OLD.approved_at, OLD.sent_at, OLD.sent_to) THEN
              RAISE EXCEPTION 'a sent quote cannot be changed; revise it instead';
            END IF;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute("CREATE TRIGGER quotes_guard BEFORE UPDATE OR DELETE ON quotes "
               "FOR EACH ROW EXECUTE FUNCTION quotes_guard()")

    # A completed survey is the evidence behind a quote: freeze it (and its rows).
    op.execute(
        """
        CREATE FUNCTION surveys_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE sid bigint; st text;
        BEGIN
          IF TG_TABLE_NAME = 'site_surveys' THEN
            IF TG_OP = 'DELETE' THEN
              RAISE EXCEPTION 'surveys are never deleted';
            END IF;
            IF OLD.status = 'completed' THEN
              RAISE EXCEPTION 'a completed survey is immutable; start a new survey';
            END IF;
            RETURN NEW;
          END IF;
          sid := CASE WHEN TG_OP = 'DELETE' THEN OLD.survey_id ELSE NEW.survey_id END;
          SELECT status INTO st FROM site_surveys WHERE id = sid;
          IF st = 'completed' THEN
            RAISE EXCEPTION 'a completed survey is immutable; start a new survey';
          END IF;
          RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END $$
        """
    )
    for table in ("site_surveys", "survey_devices", "survey_apps"):
        op.execute(f"CREATE TRIGGER {table}_guard BEFORE UPDATE OR DELETE ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION surveys_guard()")
    for table in ("survey_devices", "survey_apps"):  # inserts into a completed survey
        op.execute(f"CREATE TRIGGER {table}_ins_guard BEFORE INSERT ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION surveys_guard()")

    for table in CLIENT_OWNED:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY org_scope ON {table} USING (app_org_visible(organization_id)) "
                   f"WITH CHECK (app_org_visible(organization_id))")
    op.execute(f"GRANT SELECT, UPDATE ON quote_settings TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON site_surveys, quotes TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON survey_devices, survey_apps "
               f"TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    for table in ("quotes", "survey_apps", "survey_devices", "site_surveys"):
        op.drop_table(table)
    op.execute("DROP FUNCTION quotes_guard()")
    op.execute("DROP FUNCTION surveys_guard()")
    op.drop_table("quote_settings")
    op.execute("UPDATE organizations SET status = 'inactive' WHERE status = 'prospect'")
    op.drop_constraint("ck_organizations_status", "organizations")
    op.create_check_constraint("ck_organizations_status", "organizations",
                               "status IN ('active','inactive')")
