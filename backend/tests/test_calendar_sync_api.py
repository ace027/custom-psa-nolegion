"""Outlook sync API (REQ-04): busy blocks in availability, sync state, status, retry, setting."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import Engine

from app import scheduling as svc
from app.db import new_session, set_org_scope
from app.deps import Ctx
from app.errors import NotFound
from app.models import User
from app.scope import Scope

MON = datetime(2030, 1, 7, tzinfo=UTC)
FETCHED = datetime(2030, 1, 7, 6, 0, tzinfo=UTC)


def at(hour: int, day: int = 0) -> datetime:
    return MON + timedelta(days=day, hours=hour)


@pytest.fixture
def tech(login):
    return login("tech", "tech1@example.com")


@pytest.fixture
def enabled(owner):
    owner.execute(text("UPDATE settings SET outlook_sync_enabled = true"))


def book(admin, ticket_id, tech, start=None, end=None):
    r = admin.post(
        "/api/appointments",
        json={
            "ticket_id": ticket_id,
            "tech_id": tech.user["id"],
            "starts_at": (start or at(15)).isoformat(),
            "ends_at": (end or at(16)).isoformat(),
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def add_block(owner, user_id, start, end, status="busy"):
    owner.execute(
        text("INSERT INTO busy_blocks (user_id, starts_at, ends_at, status) VALUES (:u,:s,:e,:t)"),
        {"u": user_id, "s": start, "e": end, "t": status},
    )


def set_state(owner, appt, state, error=None):
    owner.execute(
        text(
            "UPDATE appointment_sync SET state = :s, last_error = :e, updated_at = now() "
            "WHERE appointment_id = :i"
        ),
        {"s": state, "e": error, "i": appt},
    )


def avail(client, tech):
    r = client.get(
        "/api/availability",
        params={"from": at(0).isoformat(), "to": at(24).isoformat(), "user_ids": tech.user["id"]},
    )
    assert r.status_code == 200, r.text
    return r.json()[0]


# ---- availability ------------------------------------------------------------------------------
def test_availability_returns_busy_blocks_and_fetch_time(admin, owner, tech):
    uid = tech.user["id"]
    a = avail(admin, tech)
    assert a["outlook_busy"] == [] and a["outlook_fetched_at"] is None
    add_block(owner, uid, at(18), at(19), "tentative")
    add_block(owner, uid, at(40), at(41))  # outside the range
    owner.execute(
        text("INSERT INTO calendar_busy_status (user_id, fetched_at) VALUES (:u, :f)"),
        {"u": uid, "f": FETCHED},
    )
    a = avail(admin, tech)
    assert [(b["starts_at"], b["status"]) for b in a["outlook_busy"]] == [
        ("2030-01-07T18:00:00Z", "tentative")
    ]
    assert set(a["outlook_busy"][0]) == {"starts_at", "ends_at", "status"}
    assert a["outlook_fetched_at"] == "2030-01-07T06:00:00Z"


def test_exact_match_with_synced_appointment_is_hidden(admin, owner, make_ticket, tech):
    appt = book(admin, make_ticket()["id"], tech)
    add_block(owner, tech.user["id"], at(15), at(16))
    assert len(avail(admin, tech)["outlook_busy"]) == 1  # pending: not hidden yet
    set_state(owner, appt["id"], "synced")
    assert avail(admin, tech)["outlook_busy"] == []


def test_partial_overlap_with_synced_appointment_is_kept(admin, owner, make_ticket, tech):
    appt = book(admin, make_ticket()["id"], tech)
    set_state(owner, appt["id"], "synced")
    add_block(owner, tech.user["id"], at(15), at(17))
    add_block(owner, tech.user["id"], at(14), at(16))
    assert len(avail(admin, tech)["outlook_busy"]) == 2


# ---- appointment sync field --------------------------------------------------------------------
def test_sync_is_off_when_disabled_and_real_when_enabled(admin, owner, make_ticket, tech):
    appt = book(admin, make_ticket()["id"], tech)
    assert appt["sync"] == {"state": "off", "last_error": None}
    set_state(owner, appt["id"], "failed", "boom")
    assert admin.get(f"/api/appointments/{appt['id']}").json()["sync"]["state"] == "off"
    owner.execute(text("UPDATE settings SET outlook_sync_enabled = true"))
    assert admin.get(f"/api/appointments/{appt['id']}").json()["sync"] == {
        "state": "failed",
        "last_error": "boom",
    }
    rows = admin.get(
        "/api/appointments", params={"from": at(0).isoformat(), "to": at(24).isoformat()}
    ).json()
    assert rows[0]["sync"]["state"] == "failed"


def test_list_query_count_is_bounded(admin, owner, make_ticket, tech, enabled):
    for i in range(50):
        book(admin, make_ticket()["id"], tech, at(1) + timedelta(minutes=i), at(2))
    seen = []

    def count(conn, cursor, statement, *a):
        seen.append(statement)

    event.listen(Engine, "before_cursor_execute", count)
    try:
        r = admin.get(
            "/api/appointments", params={"from": at(0).isoformat(), "to": at(24).isoformat()}
        )
    finally:
        event.remove(Engine, "before_cursor_execute", count)
    assert r.status_code == 200 and len(r.json()) == 50
    assert len(seen) < 15, len(seen)


# ---- settings ----------------------------------------------------------------------------------
def test_setting_is_admin_write_only(admin, tech):
    assert admin.get("/api/settings").json()["outlook_sync_enabled"] is False
    assert tech.patch("/api/settings", json={"outlook_sync_enabled": True}).status_code == 403
    r = admin.patch("/api/settings", json={"outlook_sync_enabled": True})
    assert r.status_code == 200 and r.json()["outlook_sync_enabled"] is True
    assert tech.get("/api/settings").json()["outlook_sync_enabled"] is True


# ---- status ------------------------------------------------------------------------------------
def test_status_counts_and_lists_failures_newest_first(admin, owner, make_ticket, tech, enabled):
    ids = [
        book(admin, make_ticket()["id"], tech, at(1) + timedelta(minutes=i), at(2))["id"]
        for i in range(23)
    ]
    for n, i in enumerate(ids[:22]):  # 22 failed, ids[22] stays pending
        owner.execute(
            text(
                "UPDATE appointment_sync SET state='failed', last_error=:e, "
                "updated_at = :t WHERE appointment_id=:i"
            ),
            {"e": f"err{n}", "t": FETCHED + timedelta(minutes=n), "i": i},
        )
    s = tech.get("/api/calendar-sync/status").json()
    assert s["enabled"] is True and s["pending"] == 1 and s["failed"] == 22
    assert len(s["failures"]) == 20
    assert s["failures"][0]["appointment_id"] == ids[21]
    assert s["failures"][0]["last_error"] == "err21"
    assert set(s["failures"][0]) == {
        "appointment_id",
        "ticket_id",
        "tech_id",
        "last_error",
        "updated_at",
    }
    assert s["busy_fetched_at"] is None and s["busy_errors"] == 0


def test_status_reports_oldest_fetch_and_errors(admin, owner, login):
    a = login("tech", "a@example.com").user["id"]
    b = login("tech", "b@example.com").user["id"]
    for uid, ts, err in ((a, FETCHED, None), (b, FETCHED + timedelta(hours=1), "bad")):
        owner.execute(
            text("INSERT INTO calendar_busy_status VALUES (:u, :f, :e)"),
            {"u": uid, "f": ts, "e": err},
        )
    s = admin.get("/api/calendar-sync/status").json()
    assert s["busy_fetched_at"] == "2030-01-07T06:00:00Z" and s["busy_errors"] == 1
    assert s["enabled"] is False


# ---- retry -------------------------------------------------------------------------------------
def test_retry_resets_a_failed_row_and_audits(admin, owner, make_ticket, tech, enabled):
    appt = book(admin, make_ticket()["id"], tech)
    set_state(owner, appt["id"], "failed", "boom")
    owner.execute(text("UPDATE appointment_sync SET attempts = 6"))
    r = admin.post(f"/api/appointments/{appt['id']}/sync/retry")
    assert r.status_code == 200, r.text
    assert r.json()["sync"] == {"state": "pending", "last_error": None}
    row = owner.execute(text("SELECT state, attempts, last_error FROM appointment_sync")).one()
    assert tuple(row) == ("pending", 0, None)
    actions = [x.action for x in owner.execute(text("SELECT action FROM audit_log"))]
    assert "appointment.sync_retry" in actions


def test_retry_of_a_non_failed_row_is_409(admin, owner, make_ticket, tech, enabled):
    appt = book(admin, make_ticket()["id"], tech)
    url = f"/api/appointments/{appt['id']}/sync/retry"
    assert admin.post(url).status_code == 409  # pending
    set_state(owner, appt["id"], "synced")
    assert admin.post(url).status_code == 409


def test_retry_unknown_appointment_is_404(admin):
    assert admin.post("/api/appointments/999999/sync/retry").status_code == 404


def test_read_only_cannot_retry(admin, login, owner, make_ticket, tech):
    appt = book(admin, make_ticket()["id"], tech)
    set_state(owner, appt["id"], "failed", "boom")
    ro = login("read_only", "ro@example.com")
    assert ro.post(f"/api/appointments/{appt['id']}/sync/retry").status_code == 403
    assert ro.get("/api/calendar-sync/status").status_code == 200


def test_retry_outside_scope_is_404(admin, owner, make_ticket, tech):
    appt = book(admin, make_ticket()["id"], tech)
    set_state(owner, appt["id"], "failed", "boom")
    with new_session() as db:
        scope = Scope.orgs(appt["organization_id"] + 1000)
        set_org_scope(db, scope.rls_value())
        user = db.get(User, tech.user["id"])
        ctx = Ctx(db=db, user=user, scope=scope)
        with pytest.raises(NotFound):
            svc.retry_sync(ctx, appt["id"])
        assert svc.sync_status(ctx)["failed"] == 0
    state = owner.execute(text("SELECT state FROM appointment_sync")).scalar_one()
    assert state == "failed"
