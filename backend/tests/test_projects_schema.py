"""Project schema guards (migration 0029): privileges, forced RLS, CHECKs, cross-client composite
FKs, dependency rules and the 'project' invoice line kind / ticket source."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import new_session, set_org_scope

TABLES = ("projects", "project_phases", "project_tasks", "project_task_dependencies")


@pytest.fixture
def two_tickets(make_org_with_ticket):
    (org_a, t_a), (org_b, t_b) = make_org_with_ticket("Org A"), make_org_with_ticket("Org B")
    return (org_a["id"], t_a["id"]), (org_b["id"], t_b["id"])


def add_project(conn, org, name="Rollout", **extra):
    cols = {"organization_id": org, "name": name, **extra}
    names = ", ".join(cols)
    values = ", ".join(f":{c}" for c in cols)
    return conn.execute(
        text(f"INSERT INTO projects ({names}) VALUES ({values}) RETURNING id"), cols
    ).scalar_one()


def add_phase(conn, org, project, name="Phase 1"):
    return conn.execute(
        text(
            "INSERT INTO project_phases (organization_id, project_id, name) "
            "VALUES (:o, :p, :n) RETURNING id"
        ),
        {"o": org, "p": project, "n": name},
    ).scalar_one()


def add_task(conn, org, project, ticket, phase=None, **extra):
    cols = {
        "organization_id": org,
        "project_id": project,
        "ticket_id": ticket,
        "phase_id": phase,
        **extra,
    }
    names = ", ".join(cols)
    values = ", ".join(f":{c}" for c in cols)
    return conn.execute(
        text(f"INSERT INTO project_tasks ({names}) VALUES ({values}) RETURNING id"), cols
    ).scalar_one()


def add_dep(conn, org, task, dep):
    conn.execute(
        text(
            "INSERT INTO project_task_dependencies (organization_id, task_id, depends_on_task_id) "
            "VALUES (:o, :t, :d)"
        ),
        {"o": org, "t": task, "d": dep},
    )


def new_ticket(owner, org, subject="Extra"):
    return owner.execute(
        text(
            "INSERT INTO tickets (organization_id, queue_id, priority_id, subject) "
            "SELECT :o, (SELECT min(id) FROM queues), (SELECT min(id) FROM priorities), :s "
            "RETURNING id"
        ),
        {"o": org, "s": subject},
    ).scalar_one()


def test_columns(owner):
    def cols(table):
        return {
            r[0]
            for r in owner.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
                {"t": table},
            )
        }

    assert {
        "organization_id",
        "name",
        "description",
        "status",
        "billing_mode",
        "fixed_fee_cents",
        "budget_cents",
        "taxable",
        "start_date",
        "due_date",
        "approved_at",
        "approved_by_id",
        "fixed_fee_invoice_line_id",
        "owner_id",
        "created_at",
        "updated_at",
    } <= cols("projects")
    assert {"project_id", "name", "position", "due_date", "completed_at"} <= cols("project_phases")
    assert {"phase_id", "ticket_id", "estimate_minutes", "position"} <= cols("project_tasks")
    assert {"task_id", "depends_on_task_id"} <= cols("project_task_dependencies")
    assert "project_id" in cols("tickets")
    assert "project_id" in cols("invoice_lines")


def test_runtime_role_privileges(owner):
    for table in TABLES:
        for p in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            has = owner.execute(
                text("SELECT has_table_privilege('psa_app', :t, :p)"), {"t": table, "p": p}
            ).scalar_one()
            can_delete = table in ("project_phases", "project_task_dependencies")
            assert has == (p != "DELETE" or can_delete), (table, p)


def test_rls_is_forced(owner):
    for table in TABLES:
        row = owner.execute(
            text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = :t"),
            {"t": table},
        ).one()
        assert row == (True, True), table
        has_org = owner.execute(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = 'organization_id'"
            ),
            {"t": table},
        ).scalar_one()
        assert has_org == 1


def test_rls_scopes_projects(owner, two_tickets):
    (a, ta), (b, tb) = two_tickets
    pa, pb = add_project(owner, a, "A"), add_project(owner, b, "B")
    add_phase(owner, a, pa)
    add_phase(owner, b, pb)
    add_task(owner, a, pa, ta)
    add_task(owner, b, pb, tb)
    with new_session() as db:
        for table in TABLES[:3]:
            assert db.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
        set_org_scope(db, str(a))
        for table in TABLES[:3]:
            orgs = {r[0] for r in db.execute(text(f"SELECT organization_id FROM {table}"))}
            assert orgs == {a}, table
        set_org_scope(db, "all")
        assert db.execute(text("SELECT count(*) FROM projects")).scalar_one() == 2
        db.rollback()


def test_project_checks(owner, two_tickets):
    (a, _), _ = two_tickets
    bad = {
        "ck_projects_status": {"status": "weird"},
        "ck_projects_billing_mode": {"billing_mode": "retainer"},
        "ck_projects_fixed_fee": {"fixed_fee_cents": 0},
        "ck_projects_budget": {"budget_cents": 0},
    }
    for name, extra in bad.items():
        with pytest.raises(IntegrityError, match=name):
            add_project(owner, a, **extra)
    with pytest.raises(IntegrityError, match="ck_projects_fixed_fee"):
        add_project(owner, a, fixed_fee_cents=-5)
    with pytest.raises(IntegrityError, match="ck_projects_budget"):
        add_project(owner, a, budget_cents=-1)
    pid = add_project(owner, a, billing_mode="tm", budget_cents=100000)
    row = owner.execute(
        text("SELECT status, taxable FROM projects WHERE id = :p"), {"p": pid}
    ).one()
    assert row == ("draft", False)
    add_project(owner, a, billing_mode="fixed_fee", fixed_fee_cents=1)


def test_task_estimate_check(owner, two_tickets):
    (a, ta), _ = two_tickets
    pa = add_project(owner, a)
    with pytest.raises(IntegrityError, match="ck_project_tasks_estimate"):
        add_task(owner, a, pa, ta, estimate_minutes=-1)
    add_task(owner, a, pa, ta, estimate_minutes=0)


def test_one_task_per_ticket(owner, two_tickets):
    (a, ta), _ = two_tickets
    pa = add_project(owner, a)
    add_task(owner, a, pa, ta)
    with pytest.raises(IntegrityError, match="uq_project_tasks_ticket"):
        add_task(owner, a, pa, ta)


def test_cross_org_links_rejected(owner, two_tickets):
    (a, ta), (b, tb) = two_tickets
    pa, pb = add_project(owner, a, "A"), add_project(owner, b, "B")
    phase_b = add_phase(owner, b, pb)
    with pytest.raises(IntegrityError, match="fk_project_phases_project_org"):
        add_phase(owner, a, pb)
    with pytest.raises(IntegrityError, match="fk_project_tasks_ticket_org"):
        add_task(owner, a, pa, tb)
    with pytest.raises(IntegrityError, match="fk_project_tasks_project_org"):
        add_task(owner, a, pb, ta)
    with pytest.raises(IntegrityError, match="fk_project_tasks_phase_org"):
        add_task(owner, a, pa, ta, phase=phase_b)
    with pytest.raises(IntegrityError, match="fk_tickets_project_org"):
        owner.execute(text("UPDATE tickets SET project_id = :p WHERE id = :t"), {"p": pb, "t": ta})
    owner.execute(text("UPDATE tickets SET project_id = :p WHERE id = :t"), {"p": pa, "t": ta})


def test_dependencies(owner, two_tickets):
    (a, ta), (b, tb) = two_tickets
    pa = add_project(owner, a)
    t2 = new_ticket(owner, a)
    task1, task2 = add_task(owner, a, pa, ta), add_task(owner, a, pa, t2)
    pb = add_project(owner, b)
    task_b = add_task(owner, b, pb, tb)
    with pytest.raises(IntegrityError, match="ck_project_task_deps_self"):
        add_dep(owner, a, task1, task1)
    add_dep(owner, a, task2, task1)
    with pytest.raises(IntegrityError, match="uq_project_task_deps"):
        add_dep(owner, a, task2, task1)
    with pytest.raises(IntegrityError, match="fk_project_task_deps_dep_org"):
        add_dep(owner, a, task1, task_b)
    with pytest.raises(IntegrityError, match="fk_project_task_deps_task_org"):
        add_dep(owner, a, task_b, task1)


def test_invoice_line_kind_and_ticket_source(owner, two_tickets):
    (a, ta), _ = two_tickets
    owner.execute(text("UPDATE tickets SET source = 'project' WHERE id = :t"), {"t": ta})
    with pytest.raises(IntegrityError, match="ck_tickets_source"):
        owner.execute(text("UPDATE tickets SET source = 'bogus' WHERE id = :t"), {"t": ta})

    pa = add_project(owner, a)
    inv = owner.execute(
        text("INSERT INTO invoices (organization_id, status) VALUES (:o, 'draft') RETURNING id"),
        {"o": a},
    ).scalar_one()

    def line(kind):
        owner.execute(
            text(
                "INSERT INTO invoice_lines (invoice_id, organization_id, kind, description, "
                "quantity, unit_price_cents, amount_cents, project_id) "
                "VALUES (:i, :o, :k, 'x', 1, 100, 100, :p)"
            ),
            {"i": inv, "o": a, "k": kind, "p": pa},
        )

    line("project")
    with pytest.raises(IntegrityError, match="ck_invoice_lines_kind"):
        line("bogus")
