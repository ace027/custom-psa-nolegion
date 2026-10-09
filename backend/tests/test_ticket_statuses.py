"""Parity phase 1C: custom statuses mapped to the five built-in behaviours."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


def statuses(admin, **p):
    return admin.get("/api/ticket-statuses", params=p).json()


def by_name(admin, name):
    return next(s for s in statuses(admin, include_archived=True) if s["name"] == name)


def test_five_builtin_statuses_exist_in_order(admin):
    got = statuses(admin)
    assert [s["behavior"] for s in got] == [
        "new",
        "open",
        "waiting_on_customer",
        "resolved",
        "closed",
    ]


def test_create_rename_reorder_archive_and_audit(admin):
    r = admin.post(
        "/api/ticket-statuses",
        json={"name": "Waiting on vendor", "behavior": "waiting_on_customer"},
    )
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert (
        admin.post(
            "/api/ticket-statuses", json={"name": "waiting ON vendor", "behavior": "open"}
        ).status_code
        == 409
    )
    assert (
        admin.post("/api/ticket-statuses", json={"name": "X", "behavior": "bogus"}).status_code
        == 422
    )
    p = admin.patch(
        f"/api/ticket-statuses/{sid}", json={"name": "Waiting on supplier", "position": 5}
    )
    assert p.status_code == 200 and p.json()["behavior"] == "waiting_on_customer"
    assert statuses(admin)[0]["id"] == sid  # position 5 sorts first
    assert (
        admin.patch(f"/api/ticket-statuses/{sid}", json={"behavior": "open"}).json()["behavior"]
        == "waiting_on_customer"
    )
    assert admin.post(f"/api/ticket-statuses/{sid}/archive").status_code == 200
    assert sid not in [s["id"] for s in statuses(admin)]
    assert admin.post(f"/api/ticket-statuses/{sid}/unarchive").status_code == 200
    actions = [
        a["action"]
        for a in admin.get("/api/audit", params={"action": "ticket_status."}).json()["items"]
    ]
    assert {"ticket_status.create", "ticket_status.update", "ticket_status.archive"} <= set(actions)


def test_the_last_status_of_a_behaviour_cannot_be_archived(admin):
    resolved = by_name(admin, "Resolved")
    r = admin.post(f"/api/ticket-statuses/{resolved['id']}/archive")
    assert r.status_code == 409 and "at least one" in r.json()["detail"]
    extra = admin.post(
        "/api/ticket-statuses", json={"name": "Fixed", "behavior": "resolved"}
    ).json()
    assert admin.post(f"/api/ticket-statuses/{resolved['id']}/archive").status_code == 200
    assert admin.post(f"/api/ticket-statuses/{extra['id']}/archive").status_code == 409


def test_status_permissions(login, admin):
    tech = login("tech")
    assert tech.get("/api/ticket-statuses").status_code == 200
    assert (
        tech.post("/api/ticket-statuses", json={"name": "X", "behavior": "open"}).status_code == 403
    )
    sid = statuses(admin)[0]["id"]
    assert tech.patch(f"/api/ticket-statuses/{sid}", json={"name": "Y"}).status_code == 403
    assert tech.post(f"/api/ticket-statuses/{sid}/archive").status_code == 403


def test_tickets_carry_a_named_status_and_behave_like_its_behaviour(admin, make_ticket, owner):
    t = make_ticket()
    assert t["status"] == "new" and t["status_name"] == "New"
    vendor = admin.post(
        "/api/ticket-statuses",
        json={"name": "Waiting on vendor", "behavior": "waiting_on_customer"},
    ).json()
    r = admin.patch(f"/api/tickets/{t['id']}", json={"status_id": vendor["id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "waiting_on_customer" and body["status_name"] == "Waiting on vendor"
    assert body["sla_state"] == "paused"  # behaves like waiting: the clock is stopped
    # filter by the named status
    ids = [
        x["id"]
        for x in admin.get("/api/tickets", params={"status_id": vendor["id"]}).json()["items"]
    ]
    assert ids == [t["id"]]
    # setting only a behaviour keeps a named status of that behaviour, else uses the first one
    same = admin.patch(f"/api/tickets/{t['id']}", json={"status": "waiting_on_customer"}).json()
    assert same["status_name"] == "Waiting on vendor"
    back = admin.patch(f"/api/tickets/{t['id']}", json={"status": "open"}).json()
    assert back["status_name"] == "Open" and back["sla_state"] != "paused"


def test_archived_status_cannot_be_chosen_but_existing_tickets_keep_it(admin, make_ticket):
    t = make_ticket()
    a = admin.post("/api/ticket-statuses", json={"name": "Scheduled", "behavior": "open"}).json()
    admin.patch(f"/api/tickets/{t['id']}", json={"status_id": a["id"]})
    admin.post(f"/api/ticket-statuses/{a['id']}/archive")
    assert admin.get(f"/api/tickets/{t['id']}").json()["status_name"] == "Scheduled"
    other = make_ticket()
    assert (
        admin.patch(f"/api/tickets/{other['id']}", json={"status_id": a["id"]}).status_code == 409
    )
    assert admin.patch(f"/api/tickets/{other['id']}", json={"status_id": 999999}).status_code == 409


def test_customer_reply_on_a_custom_waiting_status_reopens(admin, make_ticket, org_ctx):
    from app.mail import ingest
    from tests.mailfakes import MAILBOX, FakeMail, msg

    t = make_ticket(contact_id=org_ctx["contact"])
    vendor = admin.post(
        "/api/ticket-statuses",
        json={"name": "Waiting on vendor", "behavior": "waiting_on_customer"},
    ).json()
    admin.patch(f"/api/tickets/{t['id']}", json={"status_id": vendor["id"]})
    mail = FakeMail()
    mail.add(msg(subject=f"RE: [#{t['number']}] Printer down", body="Here is the log"))
    assert ingest.poll_once(mail, MAILBOX) == {"appended": 1}
    got = admin.get(f"/api/tickets/{t['id']}").json()
    assert got["status"] == "open" and got["status_name"] == "Open"


def test_bulk_can_set_a_named_status(admin, make_ticket):
    a = admin.post("/api/ticket-statuses", json={"name": "Scheduled", "behavior": "open"}).json()
    t1, t2 = make_ticket(), make_ticket()
    r = admin.post(
        "/api/tickets/bulk",
        json={"ticket_ids": [t1["id"], t2["id"]], "changes": {"status_id": a["id"]}},
    )
    assert r.json()["updated"] == 2
    assert admin.get(f"/api/tickets/{t1['id']}").json()["status_name"] == "Scheduled"


def test_database_refuses_a_status_that_contradicts_its_behaviour(admin, make_ticket, owner):
    t = make_ticket()
    resolved = by_name(admin, "Resolved")
    with pytest.raises(DBAPIError):
        owner.execute(
            text("UPDATE tickets SET status_id = :s WHERE id = :i"),
            {"s": resolved["id"], "i": t["id"]},
        )
