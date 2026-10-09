"""Parity phase 2A: timers, internal time and the weekly timesheet."""

from datetime import date, timedelta

import pytest
from sqlalchemy import text


def _today():
    return date.today()


def _monday(d=None):
    d = d or _today()
    return d - timedelta(days=d.weekday())


@pytest.fixture
def wt(admin):
    return admin.get("/api/work-types").json()[0]["id"]


@pytest.fixture
def cat(admin):
    return next(
        c["id"] for c in admin.get("/api/time-categories").json() if c["name"] == "Training"
    )


@pytest.fixture
def ticket(make_ticket):
    return make_ticket(subject="Printer down")


def backdate(owner, user_id, minutes):
    owner.execute(
        text("UPDATE timers SET started_at = now() - make_interval(mins => :m) WHERE user_id=:u"),
        {"m": minutes, "u": user_id},
    )


def audit_actions(owner):
    return [r[0] for r in owner.execute(text("SELECT action FROM audit_log ORDER BY id"))]


# ---- categories -------------------------------------------------------------------------------
def test_categories_are_seeded_and_manageable(admin):
    names = {c["name"] for c in admin.get("/api/time-categories").json()}
    assert {"Administration", "Training", "Meeting", "Paid time off"} <= names
    r = admin.post("/api/time-categories", json={"name": "Travel"})
    assert r.status_code == 201
    assert admin.post("/api/time-categories", json={"name": "travel"}).status_code == 409
    cid = r.json()["id"]
    assert (
        admin.patch(f"/api/time-categories/{cid}", json={"name": "Drive time"}).status_code == 200
    )
    assert admin.post(f"/api/time-categories/{cid}/archive").status_code == 200
    assert admin.post(f"/api/time-categories/{cid}/unarchive").status_code == 200


# ---- internal time ----------------------------------------------------------------------------
def test_internal_time_create_edit_void(admin, cat, owner):
    r = admin.post("/api/internal-time", json={"category_id": cat, "minutes": 90, "note": "SC-900"})
    assert r.status_code == 201, r.text
    e = r.json()
    assert e["user_id"] == admin.user["id"] and e["work_date"] == _today().isoformat()
    r = admin.patch(f"/api/internal-time/{e['id']}", json={"minutes": 60})
    assert r.status_code == 200 and r.json()["minutes"] == 60
    r = admin.post(f"/api/internal-time/{e['id']}/void")
    assert r.status_code == 200 and r.json()["voided_at"]
    assert admin.patch(f"/api/internal-time/{e['id']}", json={"minutes": 5}).status_code == 409
    assert admin.post(f"/api/internal-time/{e['id']}/void").status_code == 409
    acts = audit_actions(owner)
    assert {"internal_time.create", "internal_time.update", "internal_time.void"} <= set(acts)


def test_internal_time_validation(admin, cat):
    assert (
        admin.post("/api/internal-time", json={"category_id": cat, "minutes": 0}).status_code == 422
    )
    assert (
        admin.post("/api/internal-time", json={"category_id": cat, "minutes": 1441}).status_code
        == 422
    )
    assert admin.post(
        "/api/internal-time", json={"category_id": 99999, "minutes": 5}
    ).status_code in (
        404,
        409,
    )


def test_internal_time_permissions(admin, login, cat):
    tech, ro = login("tech"), login("read_only")
    assert ro.post("/api/internal-time", json={"category_id": cat, "minutes": 5}).status_code == 403
    e = tech.post("/api/internal-time", json={"category_id": cat, "minutes": 30}).json()
    assert e["user_id"] == tech.user["id"]
    other = login("tech", "other@example.com")
    assert other.patch(f"/api/internal-time/{e['id']}", json={"minutes": 5}).status_code == 403
    assert other.post(f"/api/internal-time/{e['id']}/void").status_code == 403
    # an admin may enter time for a tech
    r = admin.post(
        "/api/internal-time",
        json={"category_id": cat, "minutes": 15, "user_id": tech.user["id"]},
    )
    assert r.status_code == 201 and r.json()["user_id"] == tech.user["id"]
    assert (
        tech.post(
            "/api/internal-time",
            json={"category_id": cat, "minutes": 15, "user_id": admin.user["id"]},
        ).status_code
        == 403
    )


# ---- timers -----------------------------------------------------------------------------------
def test_timer_on_a_ticket_becomes_normal_time(admin, ticket, wt, owner):
    assert admin.get("/api/timer").json() is None
    r = admin.post("/api/timer/start", json={"ticket_id": ticket["id"], "work_type_id": wt})
    assert r.status_code == 201, r.text
    assert r.json()["ticket_number"] == ticket["number"]
    assert admin.get("/api/timer").json()["ticket_id"] == ticket["id"]
    backdate(owner, admin.user["id"], 17)
    r = admin.post("/api/timer/stop")
    assert r.status_code == 200 and r.json()["kind"] == "ticket" and r.json()["minutes"] == 17
    assert admin.get("/api/timer").json() is None
    times = admin.get(f"/api/tickets/{ticket['id']}/time").json()
    assert [t["minutes_actual"] for t in times] == [17]
    assert {"timer.start", "timer.stop"} <= set(audit_actions(owner))


def test_timer_rounds_up_and_is_at_least_a_minute(admin, ticket, wt, owner):
    admin.post("/api/timer/start", json={"ticket_id": ticket["id"], "work_type_id": wt})
    assert admin.post("/api/timer/stop").json()["minutes"] == 1
    admin.post("/api/timer/start", json={"ticket_id": ticket["id"], "work_type_id": wt})
    owner.execute(
        text("UPDATE timers SET started_at = now() - interval '61 seconds' WHERE user_id=:u"),
        {"u": admin.user["id"]},
    )
    assert admin.post("/api/timer/stop").json()["minutes"] == 2


def test_internal_timer(admin, cat, owner):
    r = admin.post("/api/timer/start", json={"category_id": cat, "billable": True})
    assert r.status_code == 201 and r.json()["billable"] is False
    backdate(owner, admin.user["id"], 45)
    out = admin.post("/api/timer/stop").json()
    assert out["kind"] == "internal" and out["minutes"] == 45
    ts = admin.get("/api/timesheet", params={"week_start": _monday().isoformat()}).json()
    assert ts["internal_minutes"] == 45


def test_only_one_timer_at_a_time(admin, ticket, wt, cat):
    assert admin.post("/api/timer/start", json={"category_id": cat}).status_code == 201
    r = admin.post("/api/timer/start", json={"ticket_id": ticket["id"], "work_type_id": wt})
    assert r.status_code == 409 and "already running" in r.json()["detail"]
    assert admin.delete("/api/timer").status_code == 204
    assert admin.delete("/api/timer").status_code == 404
    assert admin.post("/api/timer/stop").status_code == 404


def test_timer_start_rules(admin, ticket, wt, cat):
    assert admin.post("/api/timer/start", json={}).status_code == 409
    both = {"ticket_id": ticket["id"], "work_type_id": wt, "category_id": cat}
    assert admin.post("/api/timer/start", json=both).status_code == 409
    assert admin.post("/api/timer/start", json={"ticket_id": ticket["id"]}).status_code == 409
    assert (
        admin.post("/api/timer/start", json={"ticket_id": 99999, "work_type_id": wt}).status_code
        == 404
    )
    assert admin.post("/api/timer/start", json={"category_id": 99999}).status_code in (404, 409)


def test_timer_over_24_hours_must_be_discarded(admin, cat, owner):
    admin.post("/api/timer/start", json={"category_id": cat})
    backdate(owner, admin.user["id"], 25 * 60)
    r = admin.post("/api/timer/stop")
    assert r.status_code == 409 and "24 hours" in r.json()["detail"]
    assert admin.get("/api/timer").json() is not None  # still there until discarded
    assert admin.delete("/api/timer").status_code == 204
    assert "timer.discard" in audit_actions(owner)


def test_timers_are_per_person_and_techs_can_use_them(admin, login, cat):
    tech, ro = login("tech"), login("read_only")
    assert admin.post("/api/timer/start", json={"category_id": cat}).status_code == 201
    assert tech.post("/api/timer/start", json={"category_id": cat}).status_code == 201
    assert tech.get("/api/timer").json()["category_id"] == cat
    assert ro.get("/api/timer").status_code == 403
    assert ro.post("/api/timer/start", json={"category_id": cat}).status_code == 403


# ---- timesheet --------------------------------------------------------------------------------
def test_timesheet_merges_ticket_and_internal_time(admin, ticket, wt, cat, log):
    monday = _monday()
    log(ticket["id"], wt, 30, billable=True)
    log(ticket["id"], wt, 20, billable=False)
    admin.post("/api/internal-time", json={"category_id": cat, "minutes": 60})
    voided = admin.post("/api/internal-time", json={"category_id": cat, "minutes": 500}).json()
    admin.post(f"/api/internal-time/{voided['id']}/void")
    ts = admin.get("/api/timesheet", params={"week_start": monday.isoformat()}).json()
    assert ts["week_end"] == (monday + timedelta(days=6)).isoformat()
    assert ts["total_minutes"] == 110 and ts["internal_minutes"] == 60
    assert ts["billable_minutes"] >= 30
    assert len(ts["days"]) == 7 and sum(d["minutes"] for d in ts["days"]) == 110
    assert {e["kind"] for e in ts["entries"]} == {"ticket", "internal"}
    assert len(ts["entries"]) == 3
    # an empty past week
    empty = admin.get(
        "/api/timesheet", params={"week_start": (monday - timedelta(days=70)).isoformat()}
    )
    assert empty.json()["total_minutes"] == 0


def test_timesheet_week_must_start_monday(admin):
    tuesday = _monday() + timedelta(days=1)
    r = admin.get("/api/timesheet", params={"week_start": tuesday.isoformat()})
    assert r.status_code == 409


def test_timesheet_other_peoples_sheets_are_admin_only(admin, login, cat):
    tech = login("tech")
    tech.post("/api/internal-time", json={"category_id": cat, "minutes": 25})
    p = {"week_start": _monday().isoformat()}
    assert (
        admin.get("/api/timesheet", params={**p, "user_id": tech.user["id"]}).json()[
            "total_minutes"
        ]
        == 25
    )
    assert tech.get("/api/timesheet", params={**p, "user_id": admin.user["id"]}).status_code == 403
    assert tech.get("/api/timesheet", params={**p, "user_id": tech.user["id"]}).status_code == 200
    assert admin.get("/api/timesheet", params={**p, "user_id": 99999}).status_code == 404
    assert login("read_only").get("/api/timesheet", params=p).status_code == 403
