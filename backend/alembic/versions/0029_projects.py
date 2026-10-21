"""Projects: projects, project_phases, project_tasks, project_task_dependencies

Revision ID: 0029
Revises: 0028

All four tables are client-scoped (organization_id, forced RLS org_scope). Links between them and
to tickets are composite FKs on (id, organization_id) so a row can never point at another client's
project, phase or ticket. Adds tickets.project_id, invoice_lines.project_id, the 'project' invoice
line kind and the 'project' ticket source.
"""

import sqlalchemy as sa

from alembic import op

revision = "0029"
down_revision = "0028"
APP_ROLE = "psa_app"
NOW = sa.text("now()")
TABLES = ("projects", "project_phases", "project_tasks", "project_task_dependencies")


def _org_col() -> sa.Column:
    return sa.Column(
        "organization_id", sa.BigInteger, sa.ForeignKey("organizations.id"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        _org_col(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("billing_mode", sa.String(20)),
        sa.Column("fixed_fee_cents", sa.BigInteger),
        sa.Column("budget_cents", sa.BigInteger),
        sa.Column("taxable", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("start_date", sa.Date),
        sa.Column("due_date", sa.Date),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("approved_by_id", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("fixed_fee_invoice_line_id", sa.BigInteger, sa.ForeignKey("invoice_lines.id")),
        sa.Column("owner_id", sa.BigInteger, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.CheckConstraint(
            "status IN ('draft','active','on_hold','completed','cancelled')",
            name="ck_projects_status",
        ),
        sa.CheckConstraint(
            "billing_mode IS NULL OR billing_mode IN ('fixed_fee','tm')",
            name="ck_projects_billing_mode",
        ),
        sa.CheckConstraint(
            "fixed_fee_cents IS NULL OR fixed_fee_cents > 0", name="ck_projects_fixed_fee"
        ),
        sa.CheckConstraint("budget_cents IS NULL OR budget_cents > 0", name="ck_projects_budget"),
        sa.UniqueConstraint("id", "organization_id", name="uq_projects_id_org"),
    )
    op.create_index("ix_projects_org_status", "projects", ["organization_id", "status"])

    op.create_table(
        "project_phases",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        _org_col(),
        sa.Column("project_id", sa.BigInteger, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("due_date", sa.Date),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["project_id", "organization_id"],
            ["projects.id", "projects.organization_id"],
            name="fk_project_phases_project_org",
        ),
        sa.UniqueConstraint("id", "organization_id", name="uq_project_phases_id_org"),
    )
    op.create_index("ix_project_phases_project", "project_phases", ["project_id"])

    op.create_table(
        "project_tasks",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        _org_col(),
        sa.Column("project_id", sa.BigInteger, nullable=False),
        sa.Column("phase_id", sa.BigInteger),
        sa.Column("ticket_id", sa.BigInteger, nullable=False),
        sa.Column("estimate_minutes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("start_date", sa.Date),
        sa.Column("due_date", sa.Date),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("estimate_minutes >= 0", name="ck_project_tasks_estimate"),
        sa.ForeignKeyConstraint(
            ["project_id", "organization_id"],
            ["projects.id", "projects.organization_id"],
            name="fk_project_tasks_project_org",
        ),
        sa.ForeignKeyConstraint(
            ["phase_id", "organization_id"],
            ["project_phases.id", "project_phases.organization_id"],
            name="fk_project_tasks_phase_org",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id", "organization_id"],
            ["tickets.id", "tickets.organization_id"],
            name="fk_project_tasks_ticket_org",
        ),
        sa.UniqueConstraint("ticket_id", name="uq_project_tasks_ticket"),
        sa.UniqueConstraint("id", "organization_id", name="uq_project_tasks_id_org"),
    )
    op.create_index("ix_project_tasks_project", "project_tasks", ["project_id"])
    op.create_index("ix_project_tasks_phase", "project_tasks", ["phase_id"])

    op.create_table(
        "project_task_dependencies",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        _org_col(),
        sa.Column("task_id", sa.BigInteger, nullable=False),
        sa.Column("depends_on_task_id", sa.BigInteger, nullable=False),
        sa.CheckConstraint("task_id <> depends_on_task_id", name="ck_project_task_deps_self"),
        sa.ForeignKeyConstraint(
            ["task_id", "organization_id"],
            ["project_tasks.id", "project_tasks.organization_id"],
            name="fk_project_task_deps_task_org",
        ),
        sa.ForeignKeyConstraint(
            ["depends_on_task_id", "organization_id"],
            ["project_tasks.id", "project_tasks.organization_id"],
            name="fk_project_task_deps_dep_org",
        ),
        sa.UniqueConstraint("task_id", "depends_on_task_id", name="uq_project_task_deps"),
    )
    op.create_index("ix_project_task_deps_dep", "project_task_dependencies", ["depends_on_task_id"])

    op.add_column("tickets", sa.Column("project_id", sa.BigInteger, nullable=True))
    op.create_foreign_key(
        "fk_tickets_project_org",
        "tickets",
        "projects",
        ["project_id", "organization_id"],
        ["id", "organization_id"],
    )
    op.create_index("ix_tickets_project", "tickets", ["project_id"])
    op.add_column(
        "invoice_lines",
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("projects.id"), nullable=True),
    )
    op.create_index("ix_invoice_lines_project", "invoice_lines", ["project_id"])

    op.drop_constraint("ck_invoice_lines_kind", "invoice_lines", type_="check")
    op.create_check_constraint(
        "ck_invoice_lines_kind",
        "invoice_lines",
        "kind IN ('time','product','agreement','manual','proration','project')",
    )
    op.drop_constraint("ck_tickets_source", "tickets", type_="check")
    op.create_check_constraint(
        "ck_tickets_source",
        "tickets",
        "source IN ('ui','email','portal','rmm','rule','project')",
    )

    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY org_scope ON {table} "
            "USING (app_org_visible(organization_id)) "
            "WITH CHECK (app_org_visible(organization_id))"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {APP_ROLE}")
    op.execute(f"GRANT DELETE ON project_phases, project_task_dependencies TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("UPDATE tickets SET source = 'ui' WHERE source = 'project'")
    op.execute("DELETE FROM invoice_lines WHERE kind = 'project'")
    op.drop_constraint("ck_tickets_source", "tickets", type_="check")
    op.create_check_constraint(
        "ck_tickets_source", "tickets", "source IN ('ui','email','portal','rmm','rule')"
    )
    op.drop_constraint("ck_invoice_lines_kind", "invoice_lines", type_="check")
    op.create_check_constraint(
        "ck_invoice_lines_kind",
        "invoice_lines",
        "kind IN ('time','product','agreement','manual','proration')",
    )
    op.drop_index("ix_invoice_lines_project", table_name="invoice_lines")
    op.drop_column("invoice_lines", "project_id")
    op.drop_index("ix_tickets_project", table_name="tickets")
    op.drop_constraint("fk_tickets_project_org", "tickets", type_="foreignkey")
    op.drop_column("tickets", "project_id")
    op.drop_table("project_task_dependencies")
    op.drop_table("project_tasks")
    op.drop_table("project_phases")
    op.drop_table("projects")
