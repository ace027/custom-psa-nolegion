"""On-call API: rotations, members, overrides, who-is-on and the schedule (REQ-05)."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import text

ANCHOR = "2030-01-07"  # a Monday
START = datetime(2030, 1, 7, tzinfo=UTC)


@pytest.fixture
def tech(login):
    return login("tech")


@pytest.fixture
def techs(make_user):
    return [make_user("tech", f"t{i}@example.com")["id"] for i in range(3)]


def rotation_body(members=(), **kw):
    return {
        "name": "Primary",
        "handoff_weekday": 0,
        "handoff_time": "09:00:00",
        "anchor_date": ANCHOR,
        "member_ids": list(members),
        **kw,
    }


def make_rotation(client, members=(), **kw):
    r = client.post("/api/v1/oncall/rotations", json=rotation_body(members, **kw))
    assert r.status_code == 201, r.text
    return r.json()


def iso(dt):
    return dt.isoformat()


def audit_actions(owner):
    return [
        r.action
        for r in owner.execute(
            text("SELECT action FROM audit_log WHERE action LIKE 'oncall.%' ORDER BY id")
        )
    ]


def test_crud_round_trip_and_member_reorder(admin, techs, owner):
    a, b, c = techs
    r = make_rotation(admin, [a, b])
    assert [m["user_id"] for m in r["members"]] == [a, b]
    assert [m["position"] for m in r["members"]] == [0, 1]
    assert admin.get("/api/v1/oncall/rotations").json()[0]["id"] == r["id"]

    p = admin.patch(
        f"/api/v1/oncall/rotations/{r['id']}", json={"member_ids": [c, b, a], "name": "Night"}
    )
    assert p.status_code == 200, p.text
    assert p.json()["name"] == "Night"
    assert [m["user_id"] for m in p.json()["members"]] == [c, b, a]
    assert [m["position"] for m in p.json()["members"]] == [0, 1, 2]

    p = admin.patch(f"/api/v1/oncall/rotations/{r['id']}", json={"member_ids": [a]})
    assert [m["user_id"] for m in p.json()["members"]] == [a]
    p = admin.patch(f"/api/v1/oncall/rotations/{r['id']}", json={"active": False})
    assert p.json()["active"] is False and len(p.json()["members"]) == 1

    o = admin.post(
        f"/api/v1/oncall/rotations/{r['id']}/overrides",
        json={"user_id": b, "starts_at": iso(START), "ends_at": iso(START + timedelta(days=1))},
    )
    assert o.status_code == 201, o.text
    assert o.json()["user_name"]
    assert len(admin.get(f"/api/v1/oncall/rotations/{r['id']}/overrides").json()) == 1
    assert admin.delete(f"/api/v1/oncall/overrides/{o.json()['id']}").status_code == 204
    assert admin.get(f"/api/v1/oncall/rotations/{r['id']}/overrides").json() == []
    assert audit_actions(owner) == [
        "oncall.rotation_create",
        "oncall.rotation_update",
        "oncall.rotation_update",
        "oncall.rotation_update",
        "oncall.override_create",
        "oncall.override_delete",
    ]


def test_unknown_or_inactive_members_are_422(admin, make_user):
    gone = make_user("tech", "gone@example.com", active=False)["id"]
    assert admin.post("/api/v1/oncall/rotations", json=rotation_body([999999])).status_code == 422
    assert admin.post("/api/v1/oncall/rotations", json=rotation_body([gone])).status_code == 422
    r = make_rotation(admin)
    assert (
        admin.patch(f"/api/v1/oncall/rotations/{r['id']}", json={"member_ids": [gone]}).status_code
        == 422
    )
    ov = admin.post(
        f"/api/v1/oncall/rotations/{r['id']}/overrides",
        json={"user_id": gone, "starts_at": iso(START), "ends_at": iso(START + timedelta(1))},
    )
    assert ov.status_code == 422


def test_anchor_weekday_mismatch_is_422(admin):
    bad = rotation_body(handoff_weekday=2)
    assert admin.post("/api/v1/oncall/rotations", json=bad).status_code == 422
    r = make_rotation(admin)
    assert (
        admin.patch(f"/api/v1/oncall/rotations/{r['id']}", json={"handoff_weekday": 3}).status_code
        == 422
    )


def test_read_roles_can_get_but_not_write(login, admin, techs):
    r = make_rotation(admin, techs[:1])
    for role in ("billing", "read_only"):
        c = login(role)
        assert c.get("/api/v1/oncall/rotations").status_code == 200
        assert c.get(f"/api/v1/oncall/rotations/{r['id']}/overrides").status_code == 200
        assert c.get("/api/v1/oncall/now").status_code == 200
        params = {"start": iso(START), "end": iso(START + timedelta(days=7))}
        assert c.get("/api/v1/oncall/schedule", params=params).status_code == 200
        assert c.post("/api/v1/oncall/rotations", json=rotation_body()).status_code == 403
        assert c.patch(f"/api/v1/oncall/rotations/{r['id']}", json={"name": "x"}).status_code == 403
        body = {"user_id": techs[0], "starts_at": iso(START), "ends_at": iso(START + timedelta(1))}
        assert c.post(f"/api/v1/oncall/rotations/{r['id']}/overrides", json=body).status_code == 403
        assert c.delete("/api/v1/oncall/overrides/1").status_code == 403


def test_tech_and_admin_can_write(tech, admin, techs):
    r = make_rotation(tech, techs[:1])
    assert tech.patch(f"/api/v1/oncall/rotations/{r['id']}", json={"name": "T"}).status_code == 200
    assert admin.patch(f"/api/v1/oncall/rotations/{r['id']}", json={"name": "A"}).status_code == 200


def test_override_wins_in_now(admin, techs):
    a, b, _ = techs
    r = make_rotation(admin, [a], anchor_date="2020-01-06")  # a Monday long ago
    now = admin.get("/api/v1/oncall/now").json()
    assert now[0]["user_id"] == a and now[0]["source"] == "rotation"
    t = datetime.now(UTC)
    admin.post(
        f"/api/v1/oncall/rotations/{r['id']}/overrides",
        json={
            "user_id": b,
            "starts_at": iso(t - timedelta(hours=1)),
            "ends_at": iso(t + timedelta(hours=1)),
        },
    )
    now = admin.get("/api/v1/oncall/now").json()
    assert now[0]["user_id"] == b and now[0]["source"] == "override"
    assert now[0]["user_name"] and now[0]["until"]


def test_rotation_without_members_and_removed_member_override(admin, techs):
    a, b, _ = techs
    empty = make_rotation(admin, name="Empty", anchor_date="2020-01-06")
    now = admin.get("/api/v1/oncall/now").json()
    assert now == [
        {
            "rotation_id": empty["id"],
            "rotation_name": "Empty",
            "user_id": None,
            "user_name": None,
            "until": None,
            "source": None,
        }
    ]
    sched = admin.get(
        "/api/v1/oncall/schedule", params={"start": iso(START), "end": iso(START + timedelta(7))}
    )
    assert sched.json() == []

    r = make_rotation(admin, [a, b], name="Two")
    admin.post(
        f"/api/v1/oncall/rotations/{r['id']}/overrides",
        json={"user_id": b, "starts_at": iso(START), "ends_at": iso(START + timedelta(days=2))},
    )
    admin.patch(f"/api/v1/oncall/rotations/{r['id']}", json={"member_ids": [a]})  # b removed
    shifts = admin.get(
        "/api/v1/oncall/schedule", params={"start": iso(START), "end": iso(START + timedelta(7))}
    ).json()
    mine = [s for s in shifts if s["rotation_id"] == r["id"]]
    assert [(s["user_id"], s["source"]) for s in mine] == [(b, "override"), (a, "rotation")]


def test_schedule_window_limits(admin, techs):
    make_rotation(admin, techs[:2])
    ok = admin.get(
        "/api/v1/oncall/schedule", params={"start": iso(START), "end": iso(START + timedelta(31))}
    )
    assert ok.status_code == 200, ok.text
    assert len(ok.json()) >= 4
    over = admin.get(
        "/api/v1/oncall/schedule",
        params={"start": iso(START), "end": iso(START + timedelta(31, seconds=1))},
    )
    assert over.status_code == 422
    for end in (START, START - timedelta(1)):
        r = admin.get("/api/v1/oncall/schedule", params={"start": iso(START), "end": iso(end)})
        assert r.status_code == 422


def test_unknown_ids_are_404(admin, techs):
    body = {"user_id": techs[0], "starts_at": iso(START), "ends_at": iso(START + timedelta(1))}
    assert admin.patch("/api/v1/oncall/rotations/999", json={"name": "x"}).status_code == 404
    assert admin.get("/api/v1/oncall/rotations/999/overrides").status_code == 404
    assert admin.post("/api/v1/oncall/rotations/999/overrides", json=body).status_code == 404
    assert admin.delete("/api/v1/oncall/overrides/999").status_code == 404


def test_anchor_date_outside_2000_2100_is_422(admin):
    for bad in ("1999-12-27", "2101-01-04", "0001-01-01", "9999-12-27"):
        d = date.fromisoformat(bad)
        r = admin.post(
            "/api/v1/oncall/rotations",
            json=rotation_body(anchor_date=bad, handoff_weekday=d.weekday()),
        )
        assert r.status_code == 422, bad
        assert "between the years 2000 and 2100" in r.text
    for edge in ("2000-01-03", "2100-12-27"):  # both Mondays, inclusive bounds
        d = date.fromisoformat(edge)
        assert d.weekday() == 0
        r = admin.post("/api/v1/oncall/rotations", json=rotation_body(anchor_date=edge))
        assert r.status_code == 201, r.text
    rot = make_rotation(admin)
    r = admin.patch(f"/api/v1/oncall/rotations/{rot['id']}", json={"anchor_date": "9999-12-27"})
    assert r.status_code == 422
    assert "between the years 2000 and 2100" in r.text


def test_schedule_far_dates_are_422_not_500(admin, techs):
    make_rotation(admin, techs[:2])
    far = datetime(9999, 12, 31, tzinfo=UTC)
    for start in (datetime(1, 1, 2, tzinfo=UTC), far - timedelta(days=1)):
        r = admin.get(
            "/api/v1/oncall/schedule",
            params={"start": iso(start), "end": iso(start + timedelta(days=1))},
        )
        assert r.status_code in (200, 422), r.text
    r = admin.get(
        "/api/v1/oncall/schedule", params={"start": iso(far - timedelta(hours=1)), "end": iso(far)}
    )
    assert r.status_code in (200, 422), r.text


def test_service_overflow_maps_to_invalid_oncall(admin, techs, monkeypatch):
    from app import oncall as oncall_math

    make_rotation(admin, techs[:2])

    def boom(*a, **k):
        raise OverflowError("date value out of range")

    monkeypatch.setattr(oncall_math, "shifts", boom)
    r = admin.get(
        "/api/v1/oncall/schedule", params={"start": iso(START), "end": iso(START + timedelta(1))}
    )
    assert r.status_code == 422, r.text
