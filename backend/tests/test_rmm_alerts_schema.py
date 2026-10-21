"""RMM alert schema guards (migration 0027): privileges, forced RLS, one open alert per
condition, CHECKs, cross-client composite FKs and the 'rmm' ticket source."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import new_session, set_org_scope


@pytest.fixture
def two_tickets(make_org_with_ticket):
    (org_a, t_a), (org_b, t_b) = make_org_with_ticket("Org A"), make_org_with_ticket("Org B")
    return (org_a["id"], t_a["id"]), (org_b["id"], t_b["id"])


def add_integration(conn, name="Ninja"):
    return conn.execute(
        text(
            "INSERT INTO integrations (kind, name, base_url) "
            "VALUES ('ninjaone', :n, 'https://example.test') RETURNING id"
        ),
        {"n": name},
    ).scalar_one()


def add_asset(conn, org, name="PC-1"):
    return conn.execute(
        text(
            "INSERT INTO assets (organization_id, kind, name) "
            "VALUES (:o, 'computer', :n) RETURNING id"
        ),
        {"o": org, "n": name},
    ).scalar_one()


def add_alert(conn, org, integ, asset, cond="d1:c1", **extra):
    cols = {
        "organization_id": org,
        "integration_id": integ,
        "external_id": "uid-1",
        "condition_key": cond,
        "device_external_id": "d1",
        "asset_id": asset,
        "severity": "MAJOR",
        "message": "Disk low",
        **extra,
    }
    names = ", ".join(cols)
    values = ", ".join(f":{c}" for c in cols)
    conn.execute(text(f"INSERT INTO rmm_alerts ({names}) VALUES ({values})"), cols)


def priv(owner, sql, *args):
    return owner.execute(text(sql), dict(zip(("a", "b", "c"), args, strict=False))).scalar_one()


def test_runtime_role_privileges(owner):
    for p in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        has = priv(owner, "SELECT has_table_privilege('psa_app', 'rmm_alerts', :a)", p)
        assert has == (p != "DELETE"), p
    for p in ("SELECT", "UPDATE"):
        assert priv(
            owner, "SELECT has_column_privilege('psa_app', 'tickets', 'asset_id', :a)", p
        ), p
    assert priv(owner, "SELECT has_table_privilege('psa_app', 'integrations', 'UPDATE')")


def test_rls_is_forced_on_rmm_alerts(owner):
    row = owner.execute(
        text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname='rmm_alerts'")
    ).one()
    assert row == (True, True)
    has_org = owner.execute(
        text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'rmm_alerts' AND column_name = 'organization_id'"
        )
    ).scalar_one()
    assert has_org == 1


def test_rls_scopes_rmm_alerts(owner, two_tickets):
    (a, _), (b, _) = two_tickets
    integ = add_integration(owner)
    add_alert(owner, a, integ, add_asset(owner, a), cond="a:c")
    add_alert(owner, b, integ, add_asset(owner, b), cond="b:c")
    with new_session() as db:
        assert db.execute(text("SELECT count(*) FROM rmm_alerts")).scalar_one() == 0
        set_org_scope(db, str(a))
        orgs = {r[0] for r in db.execute(text("SELECT organization_id FROM rmm_alerts"))}
        assert orgs == {a}
        set_org_scope(db, "all")
        assert db.execute(text("SELECT count(*) FROM rmm_alerts")).scalar_one() == 2
        db.rollback()


def test_one_open_alert_per_condition(owner, two_tickets):
    (a, _), _ = two_tickets
    integ = add_integration(owner)
    asset = add_asset(owner, a)
    add_alert(owner, a, integ, asset)
    with pytest.raises(IntegrityError, match="uq_rmm_alerts_open"):
        add_alert(owner, a, integ, asset)
    add_alert(owner, a, integ, asset, state="cleared", cleared_at="2026-03-02 10:00+00")


def test_checks(owner, two_tickets):
    (a, _), _ = two_tickets
    integ = add_integration(owner)
    asset = add_asset(owner, a)
    bad = {
        "ck_rmm_alerts_state": {"state": "weird", "cleared_at": "2026-03-02 10:00+00"},
        "ck_rmm_alerts_severity": {"severity": "HUGE"},
        "ck_rmm_alerts_resolution": {"resolution": "weird"},
        "ck_rmm_alerts_cleared": {"cleared_at": "2026-03-02 10:00+00"},
        "ck_rmm_alerts_occurrences": {"occurrences": 0},
        "ck_rmm_alerts_missed_polls": {"missed_polls": -1},
    }
    for name, extra in bad.items():
        with pytest.raises(IntegrityError, match=name):
            add_alert(owner, a, integ, asset, **extra)


def test_cross_org_links_rejected(owner, two_tickets):
    (a, ta), (b, tb) = two_tickets
    integ = add_integration(owner)
    asset_a, asset_b = add_asset(owner, a), add_asset(owner, b)
    with pytest.raises(IntegrityError, match="fk_rmm_alerts_asset_org"):
        add_alert(owner, a, integ, asset_b)
    with pytest.raises(IntegrityError, match="fk_rmm_alerts_ticket_org"):
        add_alert(owner, a, integ, asset_a, ticket_id=tb)
    add_alert(owner, a, integ, asset_a, ticket_id=ta)
    with pytest.raises(IntegrityError, match="fk_tickets_asset_org"):
        owner.execute(
            text("UPDATE tickets SET asset_id = :s WHERE id = :t"), {"s": asset_b, "t": ta}
        )
    owner.execute(text("UPDATE tickets SET asset_id = :s WHERE id = :t"), {"s": asset_a, "t": ta})


def test_ticket_source_rmm_allowed(owner, two_tickets):
    (_, ta), _ = two_tickets
    owner.execute(text("UPDATE tickets SET source = 'rmm' WHERE id = :t"), {"t": ta})
    with pytest.raises(IntegrityError, match="ck_tickets_source"):
        owner.execute(text("UPDATE tickets SET source = 'bogus' WHERE id = :t"), {"t": ta})
