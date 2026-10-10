"""Scheduling schema guards (migration 0024): CHECK constraints, the appointments composite FK,
RLS on appointments and the runtime role's grants. These talk to the database directly."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app import permissions as P
from app.db import new_session, set_org_scope

START = "2026-03-02 09:00+00"


@pytest.fixture
def tech(make_user):
    return make_user("tech")["id"]


@pytest.fixture
def two_tickets(make_org_with_ticket):
    (org_a, t_a), (org_b, t_b) = make_org_with_ticket("Org A"), make_org_with_ticket("Org B")
    return (org_a["id"], t_a["id"]), (org_b["id"], t_b["id"])


def add_appt(conn, org, ticket, tech, starts=START, ends="2026-03-02 10:00+00", **extra):
    cols = {
        "organization_id": org,
        "ticket_id": ticket,
        "tech_id": tech,
        "starts_at": starts,
        "ends_at": ends,
        **extra,
    }
    names = ", ".join(cols)
    values = ", ".join(f":{c}" for c in cols)
    return conn.execute(
        text(f"INSERT INTO appointments ({names}) VALUES ({values}) RETURNING id"), cols
    ).scalar_one()


def add_time_off(conn, user, starts=START, ends="2026-03-03 09:00+00", **extra):
    cols = {"user_id": user, "requested_by": user, "starts_at": starts, "ends_at": ends, **extra}
    names = ", ".join(cols)
    values = ", ".join(f":{c}" for c in cols)
    return conn.execute(
        text(f"INSERT INTO user_time_off ({names}) VALUES ({values}) RETURNING id"), cols
    ).scalar_one()


def add_hours(conn, user, weekday, start, end):
    conn.execute(
        text(
            "INSERT INTO user_work_hours (user_id, weekday, start_minute, end_minute) "
            "VALUES (:u, :w, :s, :e)"
        ),
        {"u": user, "w": weekday, "s": start, "e": end},
    )


# ---- (a) CHECK / UNIQUE / FK constraints ----
def test_work_hours_constraints(owner, tech):
    add_hours(owner, tech, 0, 540, 1020)
    add_hours(owner, tech, 6, 0, 1440)  # a full day is fine
    for weekday, start, end, name in [
        (1, 600, 600, "ck_user_work_hours_range"),
        (1, 700, 600, "ck_user_work_hours_range"),
        (1, 0, 1441, "ck_user_work_hours_range"),
        (1, -1, 600, "ck_user_work_hours_range"),
        (7, 540, 1020, "ck_user_work_hours_weekday"),
        (0, 600, 900, "uq_user_work_hours_day"),
    ]:
        with pytest.raises(IntegrityError, match=name):
            add_hours(owner, tech, weekday, start, end)


def test_a_user_without_work_hours_is_valid(owner, tech):
    """No rows = the organization's default business hours."""
    n = owner.execute(text("SELECT count(*) FROM user_work_hours WHERE user_id = :u"), {"u": tech})
    assert n.scalar_one() == 0
    assert (
        owner.execute(text("SELECT timezone FROM users WHERE id = :u"), {"u": tech}).scalar()
        is None
    )


def test_time_off_constraints(owner, tech):
    add_time_off(owner, tech)
    assert owner.execute(text("SELECT status FROM user_time_off")).scalar_one() == "pending"
    with pytest.raises(IntegrityError, match="ck_user_time_off_range"):
        add_time_off(owner, tech, ends=START)
    with pytest.raises(IntegrityError, match="ck_user_time_off_range"):
        add_time_off(owner, tech, ends="2027-03-04 09:00+00")
    with pytest.raises(IntegrityError, match="ck_user_time_off_status"):
        add_time_off(owner, tech, status="maybe")
    for status in ("approved", "rejected"):
        with pytest.raises(IntegrityError, match="ck_user_time_off_decided"):
            add_time_off(owner, tech, status=status)
    add_time_off(owner, tech, status="approved", decided_by=tech, decided_at=START)
    add_time_off(owner, tech, status="cancelled")


def test_appointment_constraints(owner, two_tickets, tech):
    (a, ta), (b, _) = two_tickets
    add_appt(owner, a, ta, tech)
    assert owner.execute(text("SELECT status, client_visible FROM appointments")).one() == (
        "scheduled",
        True,
    )
    with pytest.raises(IntegrityError, match="ck_appointments_range"):
        add_appt(owner, a, ta, tech, ends=START)
    with pytest.raises(IntegrityError, match="ck_appointments_range"):
        add_appt(owner, a, ta, tech, ends="2026-03-03 09:01+00")
    with pytest.raises(IntegrityError, match="ck_appointments_status"):
        add_appt(owner, a, ta, tech, status="done")
    with pytest.raises(IntegrityError, match="ck_appointments_cancelled"):
        add_appt(owner, a, ta, tech, status="cancelled")
    with pytest.raises(IntegrityError, match="ck_appointments_cancelled"):
        add_appt(owner, a, ta, tech, cancelled_at=START)
    add_appt(owner, a, ta, tech, status="cancelled", cancelled_at=START, cancelled_by=tech)
    add_appt(owner, a, ta, tech, ends="2026-03-03 09:00+00")  # exactly 24 h is allowed
    # the appointment's client must be the ticket's client
    with pytest.raises(IntegrityError, match="fk_appointments_ticket_org"):
        add_appt(owner, b, ta, tech)


def test_ticket_without_a_client_cannot_have_appointments(owner, two_tickets, tech):
    (_, ta), _ = two_tickets
    with pytest.raises(IntegrityError, match="organization_id"):
        add_appt(owner, None, ta, tech)


# ---- (b) composite FK cascade ----
def test_appointments_follow_their_ticket_to_another_client(owner, two_tickets, tech):
    (a, ta), (b, _) = two_tickets
    appt = add_appt(owner, a, ta, tech)
    owner.execute(text("UPDATE tickets SET organization_id = :b WHERE id = :t"), {"b": b, "t": ta})
    org = owner.execute(text("SELECT organization_id FROM appointments WHERE id = :i"), {"i": appt})
    assert org.scalar_one() == b


# ---- (c) RLS ----
def test_rls_scopes_appointments(owner, two_tickets, tech):
    (a, ta), (b, tb) = two_tickets
    add_appt(owner, a, ta, tech)
    add_appt(owner, b, tb, tech)
    with new_session() as db:
        assert db.execute(text("SELECT count(*) FROM appointments")).scalar_one() == 0  # no scope
        set_org_scope(db, str(a))
        orgs = {r[0] for r in db.execute(text("SELECT organization_id FROM appointments"))}
        assert orgs == {a}
        res = db.execute(
            text("UPDATE appointments SET notes = 'pwned' WHERE organization_id = :b"), {"b": b}
        )
        assert res.rowcount == 0
        with pytest.raises(DBAPIError, match="row-level security"):
            add_appt(db, b, tb, tech)
        db.rollback()
        set_org_scope(db, f"{a},{b}")
        orgs = {r[0] for r in db.execute(text("SELECT organization_id FROM appointments"))}
        assert orgs == {a, b}
        db.rollback()


def test_rls_is_forced_on_appointments(owner):
    row = owner.execute(
        text(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'appointments'"
        )
    ).one()
    assert row == (True, True)


# ---- (d) grants ----
@pytest.mark.parametrize("table", ["appointments", "user_time_off"])
def test_runtime_role_cannot_delete_appointments_or_time_off(owner, two_tickets, tech, table):
    (a, ta), _ = two_tickets
    add_appt(owner, a, ta, tech)
    add_time_off(owner, tech)
    with new_session() as db:
        set_org_scope(db, "all")
        with pytest.raises(DBAPIError, match="permission denied"):
            db.execute(text(f"DELETE FROM {table}"))
        db.rollback()


def test_runtime_role_can_manage_work_hours(owner, tech):
    add_hours(owner, tech, 0, 540, 1020)
    with new_session() as db:
        db.execute(
            text("UPDATE user_work_hours SET end_minute = 1000 WHERE user_id = :u"), {"u": tech}
        )
        assert (
            db.execute(text("DELETE FROM user_work_hours WHERE user_id = :u"), {"u": tech}).rowcount
            == 1
        )
        db.rollback()


# ---- (e) permission matrix ----
def test_scheduling_permissions():
    assert P.SCHEDULE_READ == "schedule:read"
    assert P.SCHEDULE_WRITE == "schedule:write"
    assert P.TIMEOFF_APPROVE == "timeoff:approve"
    for role in P.ROLES:
        assert P.has_permission(role, P.SCHEDULE_READ)
    assert {r for r in P.ROLES if P.has_permission(r, P.SCHEDULE_WRITE)} == {"admin", "tech"}
    assert {r for r in P.ROLES if P.has_permission(r, P.TIMEOFF_APPROVE)} == {"admin"}
