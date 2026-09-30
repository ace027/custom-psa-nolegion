"""Client data isolation: app-layer Scope AND Postgres RLS, tested independently."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app import repositories as repo
from app.db import new_session, set_org_scope
from app.scope import Scope


@pytest.fixture
def two_orgs(admin, make_org):
    a, b = make_org("Org A"), make_org("Org B")
    for org in (a, b):
        admin.post(f"/api/organizations/{org['id']}/sites", json={"name": f"Site {org['id']}"})
        admin.post(
            f"/api/organizations/{org['id']}/contacts",
            json={"name": f"Contact {org['id']}", "email": f"c{org['id']}@x.com"},
        )
    return a["id"], b["id"]


def visible_ids(db, table):
    return sorted(r[0] for r in db.execute(text(f"SELECT id FROM {table}")))


def test_rls_fails_closed_when_scope_unset(two_orgs):
    with new_session() as db:  # runtime role, NO scope set
        for table in ("organizations", "sites", "contacts"):
            assert visible_ids(db, table) == []


def test_rls_all_scope_sees_everything(two_orgs):
    with new_session() as db:
        set_org_scope(db, "all")
        assert len(visible_ids(db, "organizations")) == 2


def test_rls_restricts_to_listed_orgs(two_orgs):
    a, b = two_orgs
    with new_session() as db:
        set_org_scope(db, str(a))
        assert visible_ids(db, "organizations") == [a]
        assert {r[0] for r in db.execute(text("SELECT organization_id FROM sites"))} == {a}
        assert {r[0] for r in db.execute(text("SELECT organization_id FROM contacts"))} == {a}
        set_org_scope(db, f"{a},{b}")
        assert visible_ids(db, "organizations") == [a, b]


def test_rls_blocks_cross_org_writes(two_orgs):
    a, b = two_orgs
    with new_session() as db:
        set_org_scope(db, str(a))
        # invisible rows cannot be updated...
        res = db.execute(
            text("UPDATE sites SET name = 'pwned' WHERE organization_id = :b"), {"b": b}
        )
        assert res.rowcount == 0
        # ...and rows cannot be inserted into an org outside the scope
        with pytest.raises((ProgrammingError, DBAPIError)):
            db.execute(text("INSERT INTO sites (organization_id, name) VALUES (:b, 'x')"), {"b": b})


def test_scope_is_transaction_local_and_does_not_leak_through_the_pool(two_orgs):
    a, _ = two_orgs
    with new_session() as db:
        set_org_scope(db, str(a))
        assert visible_ids(db, "organizations") == [a]
        db.commit()
        # new transaction on the same session/connection: scope must be gone
        assert visible_ids(db, "organizations") == []


def test_runtime_role_is_not_owner_and_cannot_bypass_rls():
    with new_session() as db:
        row = db.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).one()
        assert row.rolsuper is False and row.rolbypassrls is False
        owners = {
            r[0]
            for r in db.execute(
                text("SELECT tableowner FROM pg_tables WHERE schemaname = 'public'")
            )
        }
        assert "psa_app" not in owners


def test_repository_scope_filters_without_rls(two_orgs):
    a, b = two_orgs
    with new_session() as db:
        set_org_scope(db, "all")  # RLS wide open: only the app-layer Scope is filtering
        scoped = Scope.orgs(a)
        orgs, total = repo.list_organizations(
            db, scoped, q=None, include_archived=False, limit=50, offset=0
        )
        assert [o.id for o in orgs] == [a] and total == 1
        assert repo.get_organization(db, scoped, b) is None
        assert repo.list_sites(db, scoped, b, False) == []
        assert repo.list_contacts(db, scoped, b, False) == []
        site_b = db.execute(
            text("SELECT id FROM sites WHERE organization_id = :b"), {"b": b}
        ).scalar_one()
        assert repo.get_site(db, scoped, site_b) is None
        assert repo.get_site(db, Scope.all(), site_b).organization_id == b
        assert repo.get_organization(db, Scope.all(), b).id == b


def test_scope_helpers():
    assert Scope.all().allows(5) and Scope.all().rls_value() == "all"
    s = Scope.orgs(2, 1)
    assert s.allows(1) and not s.allows(3) and s.rls_value() == "1,2"


# ---- Phase 2 tables ----
@pytest.fixture
def two_org_tickets(admin, make_org, owner):
    ids = []
    for name in ("Org A", "Org B"):
        org = make_org(name)
        t = admin.post("/api/tickets", json={"organization_id": org["id"], "subject": name}).json()
        admin.post(f"/api/tickets/{t['id']}/notes", json={"body": "n"})
        wt = admin.get("/api/work-types").json()[0]["id"]
        admin.post(f"/api/tickets/{t['id']}/time", json={"work_type_id": wt, "minutes": 5})
        ids.append((org["id"], t["id"]))
    owner.execute(
        text(
            "INSERT INTO tickets (queue_id, priority_id, subject, source, requester_email) "
            "SELECT q.id, p.id, 'unmatched', 'email', 'x@y.com' FROM queues q, priorities p "
            "WHERE q.is_default AND p.is_default"
        )
    )
    return ids


PHASE2_TABLES = ["tickets", "ticket_notes", "time_entries"]


@pytest.mark.parametrize("table", PHASE2_TABLES)
def test_phase2_rls_fails_closed_and_scopes(two_org_tickets, table):
    (a, _), (b, _) = two_org_tickets
    with new_session() as db:
        assert visible_ids(db, table) == []  # no scope -> nothing
        set_org_scope(db, str(a))
        assert {r[0] for r in db.execute(text(f"SELECT organization_id FROM {table}"))} == {a}
        set_org_scope(db, f"{a},{b}")
        assert {r[0] for r in db.execute(text(f"SELECT organization_id FROM {table}"))} >= {a, b}


def test_unmatched_tickets_are_invisible_to_org_scoped_principals(two_org_tickets):
    (a, _), (b, _) = two_org_tickets
    with new_session() as db:
        set_org_scope(db, f"{a},{b}")
        subjects = {r[0] for r in db.execute(text("SELECT subject FROM tickets"))}
        assert "unmatched" not in subjects
        set_org_scope(db, "all")
        assert "unmatched" in {r[0] for r in db.execute(text("SELECT subject FROM tickets"))}


def test_repository_scope_filters_tickets_notes_and_time(two_org_tickets):
    (a, ta), (b, tb) = two_org_tickets
    with new_session() as db:
        set_org_scope(db, "all")  # RLS open: only the app-layer Scope filters
        scope = Scope.orgs(a)
        assert repo.get_ticket(db, scope, ta) is not None
        assert repo.get_ticket(db, scope, tb) is None
        assert repo.get_ticket_by_number(db, scope, 10002) is None
        assert repo.list_notes(db, scope, tb) == []
        assert repo.list_time_entries(db, scope, tb, False) == []
        items, total = repo.list_tickets(
            db,
            scope,
            statuses=None,
            open_only=False,
            queue_id=None,
            assignee_id=None,
            unassigned=False,
            organization_id=None,
            priority_id=None,
            needs_triage=False,
            q=None,
            limit=50,
            offset=0,
        )
        assert [t.id for t in items] == [ta] and total == 1  # unmatched excluded too


def test_rls_blocks_writing_tickets_into_other_orgs(two_org_tickets):
    (a, _), (b, _) = two_org_tickets
    with new_session() as db:
        set_org_scope(db, str(a))
        with pytest.raises((ProgrammingError, DBAPIError)):
            db.execute(
                text(
                    "INSERT INTO tickets (organization_id, queue_id, priority_id, subject) "
                    "SELECT :o, q.id, p.id, 'x' FROM queues q, priorities p "
                    "WHERE q.is_default AND p.is_default"
                ),
                {"o": b},
            )


def test_notes_are_immutable_and_time_entries_cannot_be_deleted(two_org_tickets):
    with new_session() as db:
        set_org_scope(db, "all")
        for stmt in (
            "UPDATE ticket_notes SET body = 'tampered'",
            "DELETE FROM ticket_notes",
            "DELETE FROM time_entries",
            "DELETE FROM tickets",
            "UPDATE attachments SET filename = 'x'",
        ):
            with pytest.raises(DBAPIError):
                db.execute(text(stmt))
            db.rollback()
        # ...but the one column triage needs is allowed
        set_org_scope(db, "all")
        db.execute(text("UPDATE ticket_notes SET organization_id = organization_id"))


# audit_log carries organization_id for filtering but is deliberately NOT under RLS: it is written
# by auth events that have no org scope, is append-only at the grant level, and is only ever
# exposed through the admin-only /api/audit endpoint.
RLS_EXEMPT = {"audit_log"}


def rls_gaps(conn) -> list[str]:
    """Client-owned tables (organizations + anything with an organization_id column) that lack
    FORCE ROW LEVEL SECURITY or an org_scope policy."""
    rows = conn.execute(
        text(
            """
            SELECT c.relname,
                   (c.relrowsecurity AND c.relforcerowsecurity) AS forced,
                   EXISTS (SELECT 1 FROM pg_policies p WHERE p.tablename = c.relname
                           AND p.policyname = 'org_scope') AS has_policy
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r'
              AND (c.relname = 'organizations' OR EXISTS (
                    SELECT 1 FROM information_schema.columns col
                    WHERE col.table_schema = 'public' AND col.table_name = c.relname
                      AND col.column_name = 'organization_id'))
            """
        )
    )
    return sorted(
        r.relname for r in rows if r.relname not in RLS_EXEMPT and not (r.forced and r.has_policy)
    )


def test_every_client_owned_table_has_forced_rls_and_a_policy(owner):
    """Guard for future phases: a new table with organization_id must ship with RLS."""
    assert rls_gaps(owner) == []
    tables = {
        r[0]
        for r in owner.execute(
            text(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema='public' AND column_name='organization_id'"
            )
        )
    }
    assert {
        "sites",
        "contacts",
        "tickets",
        "ticket_notes",
        "time_entries",
        "email_messages",
        "attachments",
    } <= tables
