"""Client notices and on-call schema guards (migration 0026): privileges, forced RLS, the
one-pending-notice index and the anchor weekday CHECK."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import new_session, set_org_scope

START = "2026-03-02 09:00+00"
END = "2026-03-02 10:00+00"
MONDAY = "2026-03-02"
TUESDAY = "2026-03-03"

GRANTED = {
    "appointment_notices": ("SELECT", "INSERT", "UPDATE"),
    "oncall_rotations": ("SELECT", "INSERT", "UPDATE"),
    "oncall_members": ("SELECT", "INSERT", "UPDATE", "DELETE"),
    "oncall_overrides": ("SELECT", "INSERT", "UPDATE", "DELETE"),
}


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


def add_notice(conn, appt, org, state="pending", **extra):
    cols = {
        "organization_id": org,
        "appointment_id": appt,
        "state": state,
        "send_after": START,
        "starts_at": START,
        "ends_at": END,
        **extra,
    }
    names = ", ".join(cols)
    values = ", ".join(f":{c}" for c in cols)
    conn.execute(text(f"INSERT INTO appointment_notices ({names}) VALUES ({values})"), cols)


def add_rotation(conn, weekday=0, anchor=MONDAY):
    return conn.execute(
        text(
            "INSERT INTO oncall_rotations (name, handoff_weekday, handoff_time, anchor_date) "
            "VALUES ('Primary', :w, '09:00', :a) RETURNING id"
        ),
        {"w": weekday, "a": anchor},
    ).scalar_one()


def test_runtime_role_privileges(owner):
    for table, granted in GRANTED.items():
        for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            has = owner.execute(
                text("SELECT has_table_privilege('psa_app', :t, :p)"), {"t": table, "p": priv}
            ).scalar_one()
            assert has == (priv in granted), f"{table} {priv}"


def test_rls_is_forced_on_notices_and_oncall_is_staff_internal(owner):
    for table in GRANTED:
        row = owner.execute(
            text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = :t"),
            {"t": table},
        ).one()
        client_owned = table == "appointment_notices"
        assert row == (client_owned, client_owned), table
        has_org = owner.execute(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = 'organization_id'"
            ),
            {"t": table},
        ).scalar_one()
        assert has_org == (1 if client_owned else 0), table


def test_rls_scopes_appointment_notices(owner, two_tickets, tech):
    (a, ta), (b, tb) = two_tickets
    add_notice(owner, add_appt(owner, a, ta, tech), a)
    add_notice(owner, add_appt(owner, b, tb, tech), b)
    with new_session() as db:
        assert db.execute(text("SELECT count(*) FROM appointment_notices")).scalar_one() == 0
        set_org_scope(db, str(a))
        orgs = {r[0] for r in db.execute(text("SELECT organization_id FROM appointment_notices"))}
        assert orgs == {a}
        set_org_scope(db, "all")
        assert db.execute(text("SELECT count(*) FROM appointment_notices")).scalar_one() == 2
        db.rollback()


def test_oncall_rotations_are_not_org_scoped(owner, two_tickets):
    (a, _), _ = two_tickets
    add_rotation(owner)
    add_rotation(owner)
    with new_session() as db:
        set_org_scope(db, str(a))
        assert db.execute(text("SELECT count(*) FROM oncall_rotations")).scalar_one() == 2
        db.rollback()


def test_only_one_pending_notice_per_appointment(owner, two_tickets, tech):
    (a, ta), _ = two_tickets
    appt = add_appt(owner, a, ta, tech)
    add_notice(owner, appt, a)
    with pytest.raises(IntegrityError, match="uq_appointment_notices_pending"):
        add_notice(owner, appt, a)
    add_notice(owner, appt, a, state="sent", kind="booked")
    add_notice(owner, appt, a, state="skipped")


def test_notice_state_and_kind_checks(owner, two_tickets, tech):
    (a, ta), _ = two_tickets
    appt = add_appt(owner, a, ta, tech)
    with pytest.raises(IntegrityError, match="ck_appointment_notices_state"):
        add_notice(owner, appt, a, state="weird")
    with pytest.raises(IntegrityError, match="ck_appointment_notices_kind"):
        add_notice(owner, appt, a, kind="weird")


def test_anchor_weekday_check(owner):
    add_rotation(owner, weekday=0, anchor=MONDAY)
    with pytest.raises(IntegrityError, match="ck_oncall_rotations_anchor"):
        add_rotation(owner, weekday=0, anchor=TUESDAY)
    add_rotation(owner, weekday=1, anchor=TUESDAY)


def test_new_columns_default(owner, two_tickets, tech):
    (a, ta), _ = two_tickets
    appt = add_appt(owner, a, ta, tech)
    assert (
        owner.execute(
            text("SELECT notify_client FROM appointments WHERE id = :i"), {"i": appt}
        ).scalar_one()
        is True
    )
    assert (
        owner.execute(text("SELECT appointment_emails_enabled FROM settings")).scalar_one() is False
    )


def test_member_and_override_constraints(owner, tech):
    rot = add_rotation(owner)
    member = "INSERT INTO oncall_members (rotation_id, user_id, position) VALUES (:r, :u, :p)"
    owner.execute(text(member), {"r": rot, "u": tech, "p": 0})
    with pytest.raises(IntegrityError, match="uq_oncall_members_user"):
        owner.execute(text(member), {"r": rot, "u": tech, "p": 1})
    with pytest.raises(IntegrityError, match="ck_oncall_overrides_range"):
        owner.execute(
            text(
                "INSERT INTO oncall_overrides (rotation_id, user_id, starts_at, ends_at) "
                "VALUES (:r, :u, :s, :s)"
            ),
            {"r": rot, "u": tech, "s": START},
        )
