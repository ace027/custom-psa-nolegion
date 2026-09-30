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
