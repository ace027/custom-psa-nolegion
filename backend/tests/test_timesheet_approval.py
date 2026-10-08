"""Parity phase 2B: submit / approve / return a week, the edit lock, and the payroll CSV."""

import csv
import io
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from tests.test_timekeeping import audit_actions


def monday(weeks_back=0):
    d = date.today() - timedelta(days=date.today().weekday())
    return d - timedelta(weeks=weeks_back)


@pytest.fixture
def cat(admin):
    return next(
        c["id"] for c in admin.get("/api/time-categories").json() if c["name"] == "Training"
    )


@pytest.fixture
def wt(admin):
    return admin.get("/api/work-types").json()[0]["id"]


@pytest.fixture
def tech(login):
    return login("tech")


@pytest.fixture
def week(tech, cat, make_ticket, wt):
    """A tech with 90 ticket minutes and 60 internal minutes on this week's Monday."""
    t = make_ticket(subject="VPN")
    day = monday().isoformat()
    e = tech.post(
        f"/api/tickets/{t['id']}/time", json={"work_type_id": wt, "minutes": 90, "work_date": day}
    )
    assert e.status_code == 201, e.text
    i = tech.post("/api/internal-time", json={"category_id": cat, "minutes": 60, "work_date": day})
    assert i.status_code == 201, i.text
    return dict(ticket=t, time=e.json(), internal=i.json(), start=day)


def submit(c, start):
    return c.post("/api/timesheet/submit", json={"week_start": start})


def test_open_week_is_open_and_submitting_locks_it(tech, week, cat, wt):
    sheet = tech.get("/api/timesheet", params={"week_start": week["start"]}).json()
    assert sheet["status"] == "open"
    r = submit(tech, week["start"])
    assert r.status_code == 200 and r.json()["status"] == "submitted"
    assert tech.get("/api/timesheet", params={"week_start": week["start"]}).json()["status"] == (
        "submitted"
    )
    # every way of changing that week is now refused
    tid, eid, iid = week["ticket"]["id"], week["time"]["id"], week["internal"]["id"]
    refused = [
        tech.post(
            f"/api/tickets/{tid}/time",
            json={"work_type_id": wt, "minutes": 5, "work_date": week["start"]},
        ),
        tech.patch(f"/api/time-entries/{eid}", json={"minutes": 5}),
        tech.post(f"/api/time-entries/{eid}/void"),
        tech.post(
            "/api/internal-time",
            json={"category_id": cat, "minutes": 5, "work_date": week["start"]},
        ),
        tech.patch(f"/api/internal-time/{iid}", json={"minutes": 5}),
        tech.post(f"/api/internal-time/{iid}/void"),
    ]
    assert [r.status_code for r in refused] == [409] * 6
    assert "locked" in refused[0].json()["detail"]
    # moving an entry INTO a locked week is refused too
    other = tech.post(
        "/api/internal-time",
        json={
            "category_id": cat,
            "minutes": 5,
            "work_date": (monday(1) + timedelta(days=1)).isoformat(),
        },
    ).json()
    assert (
        tech.patch(
            f"/api/internal-time/{other['id']}", json={"work_date": week["start"]}
        ).status_code
        == 409
    )
    # other weeks stay editable
    assert tech.patch(f"/api/internal-time/{other['id']}", json={"minutes": 6}).status_code == 200


def test_admin_cannot_edit_a_locked_week_either(admin, tech, week):
    submit(tech, week["start"])
    assert admin.post(f"/api/time-entries/{week['time']['id']}/void").status_code == 409


def test_submit_rules(tech, admin, week):
    assert submit(tech, (monday() + timedelta(days=1)).isoformat()).status_code == 409  # not Monday
    assert submit(tech, (monday() + timedelta(days=7)).isoformat()).status_code == 409  # future
    assert submit(tech, monday(5).isoformat()).status_code == 409  # nothing logged
    assert submit(tech, week["start"]).status_code == 200
    assert submit(tech, week["start"]).status_code == 409  # already submitted


def test_running_timer_blocks_submitting(tech, week, cat):
    tech.post("/api/timer/start", json={"category_id": cat})
    r = submit(tech, week["start"])
    assert r.status_code == 409 and "timer" in r.json()["detail"]


def test_stopping_a_timer_into_a_locked_week_is_refused_and_kept(tech, week, cat, owner):
    # today is inside this week; lock this week, then try to stop a timer
    submit(tech, week["start"])
    tech.post("/api/timer/start", json={"category_id": cat})
    assert tech.post("/api/timer/stop").status_code == 409
    assert tech.get("/api/timer").json() is not None


def test_approve_and_return_are_admin_only(admin, tech, week, login):
    submit(tech, week["start"])
    body = {"user_id": tech.user["id"], "week_start": week["start"]}
    assert tech.post("/api/timesheet/approve", json=body).status_code == 403
    assert tech.post("/api/timesheet/return", json={**body, "reason": "x"}).status_code == 403
    assert login("billing").post("/api/timesheet/approve", json=body).status_code == 403
    assert tech.get("/api/timesheets").status_code == 403
    r = admin.post("/api/timesheet/approve", json=body)
    assert r.status_code == 200 and r.json()["status"] == "approved" and r.json()["approved_at"]
    assert admin.post("/api/timesheet/approve", json=body).status_code == 409


def test_approve_needs_a_submitted_week(admin, tech, week):
    body = {"user_id": tech.user["id"], "week_start": week["start"]}
    assert admin.post("/api/timesheet/approve", json=body).status_code == 404


def test_return_unlocks_with_a_reason_and_can_be_resubmitted(admin, tech, week, owner):
    submit(tech, week["start"])
    body = {"user_id": tech.user["id"], "week_start": week["start"]}
    assert admin.post("/api/timesheet/return", json={**body, "reason": "  "}).status_code == 422
    r = admin.post("/api/timesheet/return", json={**body, "reason": "Missing Tuesday"})
    assert r.status_code == 200 and r.json()["status"] == "returned"
    sheet = tech.get("/api/timesheet", params={"week_start": week["start"]}).json()
    assert sheet["status"] == "returned" and sheet["return_reason"] == "Missing Tuesday"
    assert (
        tech.patch(f"/api/time-entries/{week['time']['id']}", json={"minutes": 100}).status_code
        == 200
    )
    assert submit(tech, week["start"]).json()["status"] == "submitted"
    # an approved week can also be returned
    admin.post("/api/timesheet/approve", json=body)
    assert admin.post("/api/timesheet/return", json={**body, "reason": "Typo"}).status_code == 200
    assert {"timesheet.submit", "timesheet.approve", "timesheet.return"} <= set(
        audit_actions(owner)
    )


def test_admin_can_approve_their_own_week(admin, cat):
    admin.post(
        "/api/internal-time",
        json={"category_id": cat, "minutes": 30, "work_date": monday().isoformat()},
    )
    assert submit(admin, monday().isoformat()).status_code == 200
    r = admin.post(
        "/api/timesheet/approve",
        json={"user_id": admin.user["id"], "week_start": monday().isoformat()},
    )
    assert r.status_code == 200


def test_queue_lists_and_filters(admin, tech, week):
    assert admin.get("/api/timesheets").json() == []
    submit(tech, week["start"])
    rows = admin.get("/api/timesheets").json()
    assert len(rows) == 1 and rows[0]["total_minutes"] == 150 and rows[0]["status"] == "submitted"
    assert admin.get("/api/timesheets", params={"status": "approved"}).json() == []
    assert admin.get("/api/timesheets", params={"status": "nope"}).status_code == 422


def test_payroll_csv_has_only_approved_weeks(admin, tech, week, cat):
    p = {"from": monday(1).isoformat(), "to": (monday() + timedelta(days=6)).isoformat()}
    assert admin.get("/api/timesheets/export.csv", params=p).text.count("\r\n") == 1  # header only
    submit(tech, week["start"])
    assert admin.get("/api/timesheets/export.csv", params=p).text.count("\r\n") == 1  # not approved
    admin.post(
        "/api/timesheet/approve", json={"user_id": tech.user["id"], "week_start": week["start"]}
    )
    r = admin.get("/api/timesheets/export.csv", params=p)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == ["Employee", "Email", "Date", "Category", "Hours"]
    assert sorted((x[3], x[4]) for x in rows[1:]) == [("Ticket time", "1.50"), ("Training", "1.00")]
    assert all(x[1] == tech.user["email"] and x[2] == week["start"] for x in rows[1:])
    # a returned week drops out again
    admin.post(
        "/api/timesheet/return",
        json={"user_id": tech.user["id"], "week_start": week["start"], "reason": "x"},
    )
    assert admin.get("/api/timesheets/export.csv", params=p).text.count("\r\n") == 1


def test_payroll_csv_range_and_voided_time(admin, tech, week, cat, owner):
    submit(tech, week["start"])
    admin.post(
        "/api/timesheet/approve", json={"user_id": tech.user["id"], "week_start": week["start"]}
    )
    owner.execute(text("UPDATE internal_time_entries SET voided_at = now()"))
    p = {"from": week["start"], "to": week["start"]}
    rows = list(csv.reader(io.StringIO(admin.get("/api/timesheets/export.csv", params=p).text)))
    assert [x[3] for x in rows[1:]] == ["Ticket time"]  # voided internal time excluded
    bad = admin.get("/api/timesheets/export.csv", params={"from": "2026-02-02", "to": "2026-01-01"})
    assert bad.status_code == 409
    assert "report.export" in audit_actions(owner)
