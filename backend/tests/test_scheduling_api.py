"""Scheduling API: working hours, time off, appointments and availability (REQ-02)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

MON = datetime(2030, 1, 7, tzinfo=UTC)  # a Monday; org default is Mon-Fri 08:00-17:00 Chicago


def at(hour: int, minute: int = 0, day: int = 0) -> str:
    """ISO UTC time on MON + day. Chicago 08:00-17:00 is 14:00-23:00Z in January."""
    return (MON + timedelta(days=day, hours=hour, minutes=minute)).isoformat()


@pytest.fixture
def tech(login):
    return login("tech")


@pytest.fixture
def tech2(login):
    return login("tech", "tech2@example.com")


@pytest.fixture
def ticket(make_ticket):
    return make_ticket()


def book(client, ticket_id, tech_id, start, end, **kw):
    return client.post(
        "/api/appointments",
        json={"ticket_id": ticket_id, "tech_id": tech_id, "starts_at": start, "ends_at": end, **kw},
    )


def request_off(client, start, end, **kw):
    return client.post("/api/time-off", json={"starts_at": start, "ends_at": end, **kw})


def audit_actions(owner, entity_type):
    return [
        r.action
        for r in owner.execute(
            text("SELECT action FROM audit_log WHERE entity_type = :t ORDER BY id"),
            {"t": entity_type},
        )
    ]


# ---- schedule ----------------------------------------------------------------------------------
def test_schedule_defaults_and_self_edit(tech, owner):
    uid = tech.user["id"]
    r = tech.get(f"/api/users/{uid}/schedule")
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["timezone"] == "America/Chicago" and s["timezone_override"] is None
    assert s["uses_default_hours"] is True
    assert [d["weekday"] for d in s["work_hours"]] == [0, 1, 2, 3, 4]
    assert s["work_hours"][0] == {"weekday": 0, "start_minute": 480, "end_minute": 1020}

    body = {
        "timezone": "America/New_York",
        "work_hours": [
            {"weekday": 2, "start_minute": 600, "end_minute": 1440},
            {"weekday": 0, "start_minute": 540, "end_minute": 1020},
        ],
    }
    r = tech.put(f"/api/users/{uid}/schedule", json=body)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["timezone"] == "America/New_York" and s["timezone_override"] == "America/New_York"
    assert s["uses_default_hours"] is False
    assert [d["weekday"] for d in s["work_hours"]] == [0, 2]
    assert tech.get(f"/api/users/{uid}/schedule").json() == s

    # null work_hours and timezone revert to the org defaults
    r = tech.put(f"/api/users/{uid}/schedule", json={"timezone": None, "work_hours": None})
    assert r.status_code == 200
    assert r.json()["uses_default_hours"] is True and r.json()["timezone"] == "America/Chicago"
    assert audit_actions(owner, "users").count("schedule.update") == 2


def test_schedule_permissions(admin, tech, tech2, login):
    r = admin.put(
        f"/api/users/{tech.user['id']}/schedule",
        json={"work_hours": [{"weekday": 5, "start_minute": 0, "end_minute": 600}]},
    )
    assert r.status_code == 200, r.text
    assert (
        admin.get(f"/api/users/{tech.user['id']}/schedule").json()["work_hours"][0]["weekday"] == 5
    )
    assert tech.put(f"/api/users/{tech2.user['id']}/schedule", json={}).status_code == 403
    assert tech.get(f"/api/users/{tech2.user['id']}/schedule").status_code == 403
    biller = login("billing")
    assert biller.put(f"/api/users/{biller.user['id']}/schedule", json={}).status_code == 403
    # admins cannot give working hours to non-bookable users
    assert admin.put(f"/api/users/{biller.user['id']}/schedule", json={}).status_code == 409
    assert admin.get("/api/users/999999/schedule").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"timezone": "Mars/Olympus_Mons"},
        {"timezone": "../etc/passwd"},
        {"work_hours": []},
        {
            "work_hours": [
                {"weekday": 1, "start_minute": 480, "end_minute": 600},
                {"weekday": 1, "start_minute": 700, "end_minute": 800},
            ]
        },
        {"work_hours": [{"weekday": 1, "start_minute": 600, "end_minute": 600}]},
        {"work_hours": [{"weekday": 7, "start_minute": 0, "end_minute": 60}]},
    ],
)
def test_schedule_validation(tech, body):
    r = tech.put(f"/api/users/{tech.user['id']}/schedule", json=body)
    assert r.status_code == 422, r.text


# ---- time off ----------------------------------------------------------------------------------
def test_time_off_request_approve_reject(admin, tech, tech2, owner):
    r = request_off(tech, at(14), at(23), reason="Dentist")
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["status"] == "pending" and t["requested_by"] == tech.user["id"]
    assert t["decided_by"] is None and t["reason"] == "Dentist"

    assert tech.post(f"/api/time-off/{t['id']}/approve", json={}).status_code == 403
    r = admin.post(f"/api/time-off/{t['id']}/approve", json={"note": "Enjoy"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved" and r.json()["decided_by"] == admin.user["id"]
    assert r.json()["decision_note"] == "Enjoy" and r.json()["decided_at"]
    assert admin.post(f"/api/time-off/{t['id']}/reject", json={}).status_code == 409

    t2 = request_off(tech, at(14, day=1), at(23, day=1)).json()
    r = admin.post(f"/api/time-off/{t2['id']}/reject", json={"note": "Busy week"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert admin.post("/api/time-off/999999/approve", json={}).status_code == 404

    # reasons are private to the owner and approvers
    def reasons(client):
        rows = client.get("/api/time-off", params={"user_id": tech.user["id"]}).json()
        return [x["reason"] for x in rows]

    assert reasons(tech) == ["Dentist", None]
    assert reasons(admin) == ["Dentist", None]
    assert reasons(tech2) == [None, None]
    assert [
        x["status"] for x in tech2.get("/api/time-off", params={"status": "approved"}).json()
    ] == ["approved"]
    rows = admin.get("/api/time-off", params={"from": at(0, day=1), "to": at(0, day=2)}).json()
    assert [x["id"] for x in rows] == [t2["id"]]
    assert audit_actions(owner, "user_time_off") == [
        "time_off.create",
        "time_off.approve",
        "time_off.create",
        "time_off.reject",
    ]


def test_admin_created_time_off_is_approved(admin, tech, tech2, login):
    r = request_off(admin, at(14), at(23), user_id=tech.user["id"])
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "approved" and r.json()["decided_by"] == admin.user["id"]
    assert r.json()["user_id"] == tech.user["id"]
    assert request_off(tech, at(14), at(23), user_id=tech2.user["id"]).status_code == 403
    biller = login("billing")
    assert request_off(biller, at(14), at(23)).status_code == 403
    assert request_off(admin, at(14), at(23), user_id=biller.user["id"]).status_code == 409


def test_time_off_cancel_rules(admin, tech, tech2):
    pending = request_off(tech, at(14), at(23)).json()
    assert tech2.post(f"/api/time-off/{pending['id']}/cancel").status_code == 403
    r = tech.post(f"/api/time-off/{pending['id']}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert tech.post(f"/api/time-off/{pending['id']}/cancel").status_code == 409

    future = request_off(admin, at(14), at(23), user_id=tech.user["id"]).json()
    assert tech.post(f"/api/time-off/{future['id']}/cancel").json()["status"] == "cancelled"

    past = request_off(
        admin, "2020-03-02T14:00:00Z", "2020-03-02T23:00:00Z", user_id=tech.user["id"]
    ).json()
    assert past["status"] == "approved"
    assert admin.post(f"/api/time-off/{past['id']}/cancel").status_code == 409

    rejected = request_off(tech, at(14, day=2), at(23, day=2)).json()
    admin.post(f"/api/time-off/{rejected['id']}/reject", json={})
    assert admin.post(f"/api/time-off/{rejected['id']}/cancel").status_code == 409


def test_time_off_validation(tech):
    assert request_off(tech, "2030-01-07T14:00:00", "2030-01-07T23:00:00").status_code == 422
    assert request_off(tech, at(23), at(14)).status_code == 422
    assert request_off(tech, at(0), at(0, day=400)).status_code == 422
    assert request_off(tech, at(14), at(23), reason="x" * 501).status_code == 422
    r = tech.get("/api/time-off", params={"from": "2030-01-07T00:00:00"})
    assert r.status_code == 422


# ---- appointments ------------------------------------------------------------------------------
def test_appointment_inside_hours_has_no_conflicts(admin, tech, ticket, owner):
    r = book(admin, ticket["id"], tech.user["id"], at(15), at(17), notes="Bring a cable")
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["conflicts"] == []
    assert a["status"] == "scheduled" and a["created_by"] == admin.user["id"]
    assert a["organization_id"] == ticket["organization_id"]
    assert a["organization_name"] == "Acme Corp"
    assert a["ticket_number"] == ticket["number"] and a["ticket_subject"] == "Printer down"
    assert a["tech_name"] == "tech user" and a["client_visible"] is True
    assert a["notes"] == "Bring a cable"
    got = tech.get(f"/api/appointments/{a['id']}")
    assert got.status_code == 200 and got.json()["conflicts"] == []
    assert tech.get("/api/appointments/999999").status_code == 404
    assert audit_actions(owner, "appointments") == ["appointment.create"]


def test_appointment_conflict_kinds(admin, tech, ticket):
    tid, uid = ticket["id"], tech.user["id"]
    outside = book(tech, tid, uid, at(12), at(15)).json()  # starts 06:00 Chicago
    assert outside["conflicts"] == [
        {"kind": "outside_hours", "time_off_id": None, "appointment_id": None}
    ]
    weekend = book(tech, tid, uid, at(15, day=5), at(16, day=5)).json()
    assert [c["kind"] for c in weekend["conflicts"]] == ["outside_hours"]

    approved = request_off(admin, at(14, day=1), at(18, day=1), user_id=uid).json()
    pending = request_off(tech, at(14, day=2), at(18, day=2)).json()
    on_pto = book(tech, tid, uid, at(15, day=1), at(16, day=1)).json()
    assert on_pto["conflicts"] == [
        {"kind": "time_off", "time_off_id": approved["id"], "appointment_id": None}
    ]
    on_pending = book(tech, tid, uid, at(15, day=2), at(16, day=2)).json()
    assert on_pending["conflicts"] == [
        {"kind": "time_off_pending", "time_off_id": pending["id"], "appointment_id": None}
    ]


def test_double_booking_warns_but_saves(admin, tech, ticket):
    tid, uid = ticket["id"], tech.user["id"]
    first = book(admin, tid, uid, at(15, day=3), at(17, day=3)).json()
    second = book(admin, tid, uid, at(16, day=3), at(18, day=3))
    assert second.status_code == 201
    assert second.json()["conflicts"] == [
        {"kind": "overlap", "time_off_id": None, "appointment_id": first["id"]}
    ]
    assert admin.get(f"/api/appointments/{first['id']}").json()["conflicts"] == [
        {"kind": "overlap", "time_off_id": None, "appointment_id": second.json()["id"]}
    ]
    touching = book(admin, tid, uid, at(18, day=3), at(19, day=3)).json()
    assert touching["conflicts"] == []
    rows = admin.get("/api/appointments", params={"ticket_id": tid}).json()
    assert [r["id"] for r in rows] == [first["id"], second.json()["id"], touching["id"]]


def test_appointment_ticket_rules(admin, tech, ticket, make_ticket, owner):
    uid = tech.user["id"]
    orphan = make_ticket(subject="From email")
    owner.execute(
        text(
            "UPDATE tickets SET organization_id = NULL, contact_id = NULL, source = 'email' WHERE id = :i"
        ),
        {"i": orphan["id"]},
    )
    r = book(admin, orphan["id"], uid, at(15), at(16))
    assert r.status_code == 409 and "client" in r.json()["detail"]

    closed = make_ticket(subject="Done")
    assert admin.patch(f"/api/tickets/{closed['id']}", json={"status": "closed"}).status_code == 200
    r = book(admin, closed["id"], uid, at(15), at(16))
    assert r.status_code == 409 and "Reopen" in r.json()["detail"]

    assert book(admin, 999999, uid, at(15), at(16)).status_code == 404
    assert book(admin, ticket["id"], uid, at(15), at(15, day=1, minute=1)).status_code == 422
    assert book(admin, ticket["id"], uid, at(16), at(15)).status_code == 422
    assert book(admin, ticket["id"], uid, "2030-01-07T15:00:00", at(16)).status_code == 422


def test_appointment_role_rules(admin, tech, ticket, login):
    biller, ro = login("billing"), login("read_only")
    assert book(biller, ticket["id"], tech.user["id"], at(15), at(16)).status_code == 403
    assert book(ro, ticket["id"], tech.user["id"], at(15), at(16)).status_code == 403
    for target in (biller, ro):
        r = book(admin, ticket["id"], target.user["id"], at(15), at(16))
        assert r.status_code == 409 and "admins and techs" in r.json()["detail"]
    a = book(admin, ticket["id"], tech.user["id"], at(15), at(16)).json()
    for reader in (biller, ro):
        assert reader.get(f"/api/appointments/{a['id']}").status_code == 200
        rows = reader.get("/api/appointments", params={"from": at(0), "to": at(0, day=1)}).json()
        assert [x["id"] for x in rows] == [a["id"]]
        assert reader.post(f"/api/appointments/{a['id']}/cancel", json={}).status_code == 403


def test_patch_reassigns_and_recomputes(admin, tech, tech2, ticket, owner):
    blocker = book(admin, ticket["id"], tech2.user["id"], at(15), at(16)).json()
    a = book(admin, ticket["id"], tech.user["id"], at(15), at(16)).json()
    assert a["conflicts"] == []
    r = tech.patch(f"/api/appointments/{a['id']}", json={"tech_id": tech2.user["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["tech_id"] == tech2.user["id"]
    assert r.json()["conflicts"] == [
        {"kind": "overlap", "time_off_id": None, "appointment_id": blocker["id"]}
    ]
    r = tech.patch(
        f"/api/appointments/{a['id']}",
        json={"starts_at": at(17), "ends_at": at(18), "notes": None, "client_visible": False},
    )
    assert r.json()["conflicts"] == [] and r.json()["client_visible"] is False
    assert tech.patch(f"/api/appointments/{a['id']}", json={"ends_at": at(16)}).status_code == 422
    assert (
        tech.patch(f"/api/appointments/{a['id']}", json={"ends_at": at(18, day=1)}).status_code
        == 422
    )
    r = tech.patch(f"/api/appointments/{a['id']}", json={"tech_id": admin.user["id"] + 999})
    assert r.status_code == 409

    r = tech.post(f"/api/appointments/{a['id']}/cancel", json={"reason": "Client rescheduled"})
    assert r.status_code == 200
    c = r.json()
    assert (
        c["status"] == "cancelled"
        and c["cancelled_at"]
        and c["cancel_reason"] == "Client rescheduled"
    )
    assert c["conflicts"] == []
    assert tech.post(f"/api/appointments/{a['id']}/cancel", json={}).status_code == 409
    assert tech.patch(f"/api/appointments/{a['id']}", json={"notes": "x"}).status_code == 409
    row = owner.execute(
        text("SELECT cancelled_by FROM appointments WHERE id = :i"), {"i": a["id"]}
    ).one()
    assert row.cancelled_by == tech.user["id"]
    actions = [
        r.action
        for r in owner.execute(
            text(
                "SELECT action FROM audit_log WHERE entity_type='appointments' AND entity_id=:i ORDER BY id"
            ),
            {"i": a["id"]},
        )
    ]
    assert actions == [
        "appointment.create",
        "appointment.update",
        "appointment.update",
        "appointment.cancel",
    ]
    org_ids = {
        r.organization_id
        for r in owner.execute(
            text("SELECT organization_id FROM audit_log WHERE entity_type='appointments'")
        )
    }
    assert org_ids == {ticket["organization_id"]}


def test_list_appointments_filters_and_ranges(admin, tech, tech2, ticket):
    a = book(admin, ticket["id"], tech.user["id"], at(15), at(16)).json()
    b = book(admin, ticket["id"], tech2.user["id"], at(15, day=1), at(16, day=1)).json()
    admin.post(f"/api/appointments/{b['id']}/cancel", json={})

    assert admin.get("/api/appointments").status_code == 422
    assert admin.get("/api/appointments", params={"from": at(0)}).status_code == 422
    r = admin.get("/api/appointments", params={"from": at(0), "to": at(0, day=63)})
    assert r.status_code == 422
    r = admin.get("/api/appointments", params={"from": at(0), "to": at(0, day=62)})
    assert [x["id"] for x in r.json()] == [a["id"]]
    r = admin.get(
        "/api/appointments",
        params={"from": at(0), "to": at(0, day=62), "include_cancelled": True},
    )
    assert [x["id"] for x in r.json()] == [a["id"], b["id"]]
    r = admin.get(
        "/api/appointments",
        params={
            "from": at(0),
            "to": at(0, day=7),
            "tech_id": tech2.user["id"],
            "include_cancelled": True,
        },
    )
    assert [x["id"] for x in r.json()] == [b["id"]]
    r = admin.get("/api/appointments", params={"from": at(16), "to": at(17)})
    assert r.json() == []  # half-open: ends exactly at `from`
    r = admin.get("/api/appointments", params={"ticket_id": ticket["id"]})
    assert [x["id"] for x in r.json()] == [a["id"]]


# ---- availability ------------------------------------------------------------------------------
def test_availability_uses_tech_timezone(admin, tech, ticket, login):
    uid = tech.user["id"]
    assert (
        tech.put(f"/api/users/{uid}/schedule", json={"timezone": "America/New_York"}).status_code
        == 200
    )
    # New York 08:00-17:00 on the Monday is 13:00-22:00Z (org Chicago would be 14:00-23:00Z)
    request_off(admin, at(14), at(15), user_id=uid)  # approved
    request_off(tech, at(18), at(19))  # pending: does not block
    appt = book(admin, ticket["id"], uid, at(16), at(17)).json()
    r = admin.get(
        "/api/availability", params={"user_ids": str(uid), "from": at(0), "to": at(0, day=1)}
    )
    assert r.status_code == 200, r.text
    [row] = r.json()
    assert row["user_id"] == uid and row["timezone"] == "America/New_York"

    def spans(items):
        return [(i["starts_at"][11:16], i["ends_at"][11:16]) for i in items]

    assert spans(row["working"]) == [("13:00", "22:00")]
    assert spans(row["time_off"]) == [("14:00", "15:00")]
    assert spans(row["appointments"]) == [("16:00", "17:00")]
    assert row["appointments"][0]["id"] == appt["id"]
    assert spans(row["free"]) == [("13:00", "14:00"), ("15:00", "16:00"), ("17:00", "22:00")]

    # no user_ids: every active admin and tech (the org default applies to the admin)
    rows = login("read_only").get("/api/availability", params={"from": at(0), "to": at(0, day=1)})
    assert rows.status_code == 200
    by_user = {x["user_id"]: x for x in rows.json()}
    assert set(by_user) == {admin.user["id"], uid}
    assert spans(by_user[admin.user["id"]]["free"]) == [("14:00", "23:00")]


def test_availability_validation(admin, tech, login):
    params = {"from": at(0), "to": at(0, day=32), "user_ids": str(tech.user["id"])}
    assert admin.get("/api/availability", params=params).status_code == 422
    params = {"from": at(0), "to": at(0, day=1), "user_ids": "1,abc"}
    assert admin.get("/api/availability", params=params).status_code == 422
    params = {"from": at(0, day=1), "to": at(0)}
    assert admin.get("/api/availability", params=params).status_code == 422
    params = {"from": "2030-01-07T00:00:00", "to": "2030-01-08T00:00:00"}
    assert admin.get("/api/availability", params=params).status_code == 422
    biller = login("billing")
    params = {"from": at(0), "to": at(0, day=1), "user_ids": str(biller.user["id"])}
    assert admin.get("/api/availability", params=params).status_code == 409
