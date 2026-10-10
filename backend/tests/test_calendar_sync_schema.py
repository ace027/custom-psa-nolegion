"""Outlook sync schema guards (migration 0025): CHECK constraints, forced RLS on appointment_sync,
the cascade from appointments and the runtime role's grants."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import new_session, set_org_scope

START = "2026-03-02 09:00+00"
END = "2026-03-02 10:00+00"


@pytest.fixture
def tech(make_user):
    return make_user("tech")["id"]


@pytest.fixture
def two_tickets(make_org_with_ticket):
    (org_a, t_a), (org_b, t_b) = make_org_with_ticket("Org A"), make_org_with_ticket("Org B")
    return (org_a["id"], t_a["id"]), (org_b["id"], t_b["id"])


def add_appt(conn, org, ticket, tech):
    return conn.execute(
        text(
            "INSERT INTO appointments (organization_id, ticket_id, tech_id, starts_at, ends_at) "
            "VALUES (:o, :t, :u, :s, :e) RETURNING id"
        ),
        {"o": org, "t": ticket, "u": tech, "s": START, "e": END},
    ).scalar_one()


def add_sync(conn, appt, org, **extra):
    cols = {"appointment_id": appt, "organization_id": org, **extra}
    names = ", ".join(cols)
    values = ", ".join(f":{c}" for c in cols)
    conn.execute(text(f"INSERT INTO appointment_sync ({names}) VALUES ({values})"), cols)


def add_busy(conn, user, starts=START, ends=END):
    conn.execute(
        text(
            "INSERT INTO busy_blocks (user_id, starts_at, ends_at, status) VALUES (:u, :s, :e, 'busy')"
        ),
        {"u": user, "s": starts, "e": ends},
    )


def test_defaults_and_state_check(owner, two_tickets, tech):
    (a, ta), _ = two_tickets
    appt = add_appt(owner, a, ta, tech)
    add_sync(owner, appt, a)
    row = owner.execute(
        text(
            "SELECT state, generation, desired_version, synced_version, attempts, "
            "graph_event_id FROM appointment_sync"
        )
    ).one()
    assert row == ("pending", 1, 1, 0, 0, None)
    appt2 = add_appt(owner, a, ta, tech)
    with pytest.raises(IntegrityError, match="ck_appointment_sync_state"):
        add_sync(owner, appt2, a, state="weird")
    for state in ("synced", "failed", "skipped"):
        owner.execute(
            text("UPDATE appointment_sync SET state = :s WHERE appointment_id = :i"),
            {"s": state, "i": appt},
        )


def test_busy_block_range_check(owner, tech):
    add_busy(owner, tech)
    with pytest.raises(IntegrityError, match="ck_busy_blocks_range"):
        add_busy(owner, tech, ends=START)
    with pytest.raises(IntegrityError, match="ck_busy_blocks_range"):
        add_busy(owner, tech, ends="2026-03-02 08:00+00")


def test_rls_is_forced_on_appointment_sync(owner):
    row = owner.execute(
        text(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname = 'appointment_sync'"
        )
    ).one()
    assert row == (True, True)


def test_rls_scopes_appointment_sync(owner, two_tickets, tech):
    (a, ta), (b, tb) = two_tickets
    add_sync(owner, add_appt(owner, a, ta, tech), a)
    add_sync(owner, add_appt(owner, b, tb, tech), b)
    with new_session() as db:
        assert db.execute(text("SELECT count(*) FROM appointment_sync")).scalar_one() == 0
        set_org_scope(db, str(a))
        orgs = {r[0] for r in db.execute(text("SELECT organization_id FROM appointment_sync"))}
        assert orgs == {a}
        res = db.execute(
            text("UPDATE appointment_sync SET last_error = 'x' WHERE organization_id = :b"),
            {"b": b},
        )
        assert res.rowcount == 0
        set_org_scope(db, "all")
        assert db.execute(text("SELECT count(*) FROM appointment_sync")).scalar_one() == 2
        db.rollback()


def test_deleting_an_appointment_cascades_its_sync_row(owner, two_tickets, tech):
    (a, ta), _ = two_tickets
    appt = add_appt(owner, a, ta, tech)
    add_sync(owner, appt, a)
    owner.execute(text("DELETE FROM appointments WHERE id = :i"), {"i": appt})
    assert owner.execute(text("SELECT count(*) FROM appointment_sync")).scalar_one() == 0


def test_deleting_a_user_cascades_the_busy_cache(owner, tech):
    add_busy(owner, tech)
    owner.execute(text("INSERT INTO calendar_busy_status (user_id) VALUES (:u)"), {"u": tech})
    owner.execute(text("DELETE FROM users WHERE id = :u"), {"u": tech})
    assert owner.execute(text("SELECT count(*) FROM busy_blocks")).scalar_one() == 0
    assert owner.execute(text("SELECT count(*) FROM calendar_busy_status")).scalar_one() == 0


def test_outlook_sync_setting_defaults_off(owner):
    assert owner.execute(text("SELECT outlook_sync_enabled FROM settings")).scalar_one() is False


def test_runtime_role_can_write_the_busy_cache(owner, tech):
    with new_session() as db:
        add_busy(db, tech)
        db.execute(
            text("INSERT INTO calendar_busy_status (user_id, fetched_at) VALUES (:u, now())"),
            {"u": tech},
        )
        db.execute(text("UPDATE busy_blocks SET status = 'oof' WHERE user_id = :u"), {"u": tech})
        db.rollback()
