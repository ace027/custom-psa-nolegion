from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from app import ticket_services as svc
from app.sla import Calendar, add_business_minutes, business_minutes_between

CT = ZoneInfo("America/Chicago")
CAL = Calendar(CT, frozenset({0, 1, 2, 3, 4}), 480, 1020)


def ct(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=CT).astimezone(UTC)


def pri(admin, name):
    return next(p["id"] for p in admin.get("/api/priorities").json() if p["name"] == name)


@pytest.fixture
def freeze(monkeypatch):
    """Control the service clock. Usage: freeze(ct(2026, 9, 28, 10))"""

    def _set(when):
        monkeypatch.setattr(svc, "now", lambda: when)

    return _set


def set_created(owner, admin, ticket_id, when):
    """Backdate a ticket and recompute its SLA (toggle priority to force recompute)."""
    owner.execute(
        text("UPDATE tickets SET created_at = :t WHERE id = :i"), {"t": when, "i": ticket_id}
    )
    t = admin.get(f"/api/tickets/{ticket_id}").json()
    other = pri(admin, "Low" if t["priority_name"] != "Low" else "High")
    admin.patch(f"/api/tickets/{ticket_id}", json={"priority_id": other})
    admin.patch(f"/api/tickets/{ticket_id}", json={"priority_id": t["priority_id"]})
    return admin.get(f"/api/tickets/{ticket_id}").json()


# ---- creation ----
def test_create_applies_defaults_numbers_and_sla(make_ticket, admin):
    t = make_ticket(description="It is jammed")
    assert t["number"] == 10001 and make_ticket()["number"] == 10002
    assert t["status"] == "new" and t["queue_name"] == "Support" and t["priority_name"] == "Normal"
    assert t["source"] == "ui" and not t["needs_triage"]
    assert t["sla_first_response_due"] and t["sla_resolution_due"]
    assert t["sla_state"] in ("ok", "at_risk")
    actions = [
        a["action"] for a in admin.get("/api/audit", params={"action": "ticket."}).json()["items"]
    ]
    assert "ticket.create" in actions


def test_create_validates_references(admin, org_ctx, make_org, make_ticket, login):
    other = make_org("Other Co")
    other_contact = admin.post(
        f"/api/organizations/{other['id']}/contacts", json={"name": "Zed"}
    ).json()
    base = {"organization_id": org_ctx["org"], "subject": "x"}
    assert admin.post("/api/tickets", json={**base, "organization_id": 999}).status_code == 404
    assert (
        admin.post("/api/tickets", json={**base, "contact_id": other_contact["id"]}).status_code
        == 409
    )
    billing = login("billing")
    assert (
        admin.post("/api/tickets", json={**base, "assignee_id": billing.user["id"]}).status_code
        == 409
    )
    assert admin.post("/api/tickets", json={**base, "queue_id": 999}).status_code == 409
    assert admin.post("/api/tickets", json={**base, "subject": ""}).status_code == 422
    ok = admin.post(
        "/api/tickets",
        json={**base, "contact_id": org_ctx["contact"], "assignee_id": admin.user["id"]},
    )
    assert ok.status_code == 201 and ok.json()["assignee_name"] == "admin user"


def test_get_list_filters_and_search(admin, make_ticket, org_ctx):
    a = make_ticket(subject="Email broken")
    b = make_ticket(subject="VPN slow", assignee_id=admin.user["id"])
    assert admin.get(f"/api/tickets/{a['id']}").json()["subject"] == "Email broken"
    assert admin.get("/api/tickets/999").status_code == 404
    assert admin.get("/api/tickets").json()["total"] == 2
    assert admin.get("/api/tickets", params={"unassigned": True}).json()["total"] == 1
    assert (
        admin.get("/api/tickets", params={"assignee_id": admin.user["id"]}).json()["items"][0]["id"]
        == b["id"]
    )
    assert admin.get("/api/tickets", params={"q": "vpn"}).json()["total"] == 1
    assert admin.get("/api/tickets", params={"q": f"#{a['number']}"}).json()["total"] == 1
    assert (
        admin.get("/api/tickets", params={"organization_id": org_ctx["org"]}).json()["total"] == 2
    )
    assert admin.get("/api/tickets", params={"status": "closed"}).json()["total"] == 0
    assert admin.get("/api/tickets", params={"needs_triage": True}).json()["total"] == 0
    assert (
        admin.get("/api/tickets", params={"open_only": True, "queue_id": a["queue_id"]}).json()[
            "total"
        ]
        == 2
    )
    assert (
        admin.get("/api/tickets", params={"priority_id": a["priority_id"], "limit": 1})
        .json()["items"]
        .__len__()
        == 1
    )


# ---- updates and status transitions ----
def test_assigning_a_new_ticket_opens_it(admin, make_ticket):
    t = make_ticket()
    r = admin.patch(f"/api/tickets/{t['id']}", json={"assignee_id": admin.user["id"]}).json()
    assert r["status"] == "open" and r["assignee_name"] == "admin user"


def test_status_lifecycle_and_timestamps(admin, make_ticket):
    t = make_ticket()
    url = f"/api/tickets/{t['id']}"
    r = admin.patch(url, json={"status": "resolved"}).json()
    assert r["resolved_at"] and r["sla_state"] == "done"
    r = admin.patch(url, json={"status": "closed"}).json()
    assert r["closed_at"] and r["resolved_at"]  # keeps original resolution time
    r = admin.patch(url, json={"status": "open"}).json()  # reopen
    assert r["resolved_at"] is None and r["closed_at"] is None
    assert admin.patch(url, json={"status": "bogus"}).status_code == 422


def test_update_fields_validation_and_audit(admin, make_ticket, org_ctx):
    t = make_ticket()
    url = f"/api/tickets/{t['id']}"
    r = admin.patch(
        url,
        json={
            "subject": "New subject",
            "contact_id": org_ctx["contact"],
            "category_id": admin.get("/api/categories").json()[0]["id"],
        },
    )
    assert r.status_code == 200 and r.json()["subject"] == "New subject"
    assert admin.patch(url, json={"subject": None}).status_code == 409
    assert admin.patch(url, json={"queue_id": None}).status_code == 409
    assert admin.patch(url, json={"contact_id": 999}).status_code == 409
    assert admin.patch(url, json={"priority_id": 999}).status_code == 409
    assert admin.patch("/api/tickets/999", json={"subject": "x"}).status_code == 404
    up = admin.get(
        "/api/audit", params={"entity_type": "tickets", "action": "ticket.update"}
    ).json()["items"]
    assert (
        up[0]["before"]["subject"] == "Printer down" and up[0]["after"]["subject"] == "New subject"
    )


def test_cannot_change_org_of_matched_ticket(admin, make_ticket, make_org):
    t = make_ticket()
    other = make_org("Other")
    assert (
        admin.patch(f"/api/tickets/{t['id']}", json={"organization_id": other["id"]}).status_code
        == 409
    )


# ---- SLA ----
def test_priority_change_recomputes_due_dates(admin, make_ticket):
    t = make_ticket()
    urgent = admin.patch(
        f"/api/tickets/{t['id']}", json={"priority_id": pri(admin, "Urgent")}
    ).json()
    assert urgent["sla_resolution_due"] < t["sla_resolution_due"]


def test_pause_credits_business_minutes_and_shifts_due(admin, owner, make_ticket, freeze):
    t = make_ticket()
    created = ct(2026, 9, 28, 9)  # Monday 09:00 Central
    t = set_created(owner, admin, t["id"], created)
    base_due = add_business_minutes(created, 1440, CAL)
    assert datetime.fromisoformat(t["sla_resolution_due"]) == base_due

    freeze(ct(2026, 9, 28, 10))  # Mon 10:00: waiting on customer
    admin.patch(f"/api/tickets/{t['id']}", json={"status": "waiting_on_customer"})
    assert admin.get(f"/api/tickets/{t['id']}").json()["sla_state"] == "paused"

    freeze(ct(2026, 9, 29, 10))  # Tue 10:00: customer replied -> reopen
    r = admin.patch(f"/api/tickets/{t['id']}", json={"status": "open"}).json()
    paused = business_minutes_between(ct(2026, 9, 28, 10), ct(2026, 9, 29, 10), CAL)
    assert paused == 9 * 60  # 7h Monday (10-17) + 2h Tuesday (8-10)
    expected = add_business_minutes(created, 1440 + paused, CAL)
    assert datetime.fromisoformat(r["sla_resolution_due"]) == expected
    with_owner = owner.execute(text("SELECT sla_paused_minutes, sla_paused_at FROM tickets")).one()
    assert with_owner.sla_paused_minutes == paused and with_owner.sla_paused_at is None


def test_sla_states_ok_at_risk_breached(admin, owner, make_ticket, freeze):
    t = make_ticket(priority_id=pri(admin, "High"))  # 60 min first response, 480 resolution
    created = ct(2026, 9, 28, 9)
    set_created(owner, admin, t["id"], created)

    def state():
        return admin.get(f"/api/tickets/{t['id']}").json()["sla_state"]

    freeze(ct(2026, 9, 28, 9, 5))
    assert state() == "ok"
    freeze(ct(2026, 9, 28, 9, 50))  # 10 of 60 min left <= 25%
    assert state() == "at_risk"
    freeze(ct(2026, 9, 28, 10, 30))
    assert state() == "breached"  # first response overdue
    admin.post(f"/api/tickets/{t['id']}/notes", json={"body": "hi", "visibility": "customer"})
    freeze(ct(2026, 9, 28, 10, 31))
    assert state() == "ok"  # first response met; resolution has plenty of time
    freeze(ct(2026, 9, 29, 10))
    assert state() == "breached"  # 480 business minutes have elapsed


def test_resolved_ticket_is_no_longer_at_risk(admin, make_ticket):
    t = make_ticket()
    admin.patch(f"/api/tickets/{t['id']}", json={"status": "resolved"})
    d = admin.get("/api/dashboard").json()
    assert d["counts"]["open"] == 0 and d["sla_at_risk"] == []


def test_priority_without_sla_targets_has_state_none(admin, make_ticket):
    p = admin.post("/api/priorities", json={"name": "Project", "rank": 9}).json()
    assert make_ticket(priority_id=p["id"])["sla_state"] == "none"


# ---- notes ----
def test_notes_visibility_and_first_response(admin, make_ticket, login):
    t = make_ticket()
    n = admin.post(f"/api/tickets/{t['id']}/notes", json={"body": "internal thought"})
    assert n.status_code == 201 and n.json()["visibility"] == "internal"
    assert admin.get(f"/api/tickets/{t['id']}").json()["first_responded_at"] is None
    admin.post(
        f"/api/tickets/{t['id']}/notes", json={"body": "we're on it", "visibility": "customer"}
    )
    assert admin.get(f"/api/tickets/{t['id']}").json()["first_responded_at"]
    notes = admin.get(f"/api/tickets/{t['id']}/notes").json()
    assert [x["visibility"] for x in notes] == ["internal", "customer"]
    assert notes[0]["author_name"] == "admin user"
    assert admin.get("/api/tickets/999/notes").status_code == 404
    assert admin.post("/api/tickets/999/notes", json={"body": "x"}).status_code == 404
    assert admin.post(f"/api/tickets/{t['id']}/notes", json={"body": ""}).status_code == 422
    assert login("read_only").get(f"/api/tickets/{t['id']}/notes").status_code == 200


def test_emailing_a_customer_note_queues_an_outbound_message(admin, owner, make_ticket, org_ctx):
    t = make_ticket(contact_id=org_ctx["contact"])
    r = admin.post(
        f"/api/tickets/{t['id']}/notes",
        json={"body": "Fixed!", "visibility": "customer", "send_email": True},
    )
    assert r.status_code == 201 and r.json()["email_status"] == "pending"
    row = owner.execute(
        text("SELECT to_emails, subject, send_status, direction FROM email_messages")
    ).one()
    assert row.to_emails == ["pat@acme.com"] and row.direction == "out"
    assert row.subject == f"[#{t['number']}] Printer down" and row.send_status == "pending"


def test_email_note_rules(admin, make_ticket, org_ctx):
    no_contact = make_ticket()
    url = f"/api/tickets/{no_contact['id']}/notes"
    assert (
        admin.post(
            url, json={"body": "x", "visibility": "customer", "send_email": True}
        ).status_code
        == 409
    )  # nobody to email
    with_contact = make_ticket(contact_id=org_ctx["contact"])
    assert (
        admin.post(
            f"/api/tickets/{with_contact['id']}/notes",
            json={"body": "x", "visibility": "internal", "send_email": True},
        ).status_code
        == 409
    )  # internal notes never leave


# ---- time ----
@pytest.mark.parametrize(
    "minutes,billable,expected",
    [
        (1, True, 15),
        (15, True, 15),
        (16, True, 30),
        (60, True, 60),
        (61, True, 75),
        (30, False, 0),
    ],
)
def test_billable_rounding_rule(admin, make_ticket, minutes, billable, expected):
    t = make_ticket()
    wt = admin.get("/api/work-types").json()[0]["id"]
    r = admin.post(
        f"/api/tickets/{t['id']}/time",
        json={"work_type_id": wt, "minutes": minutes, "billable": billable},
    )
    assert r.status_code == 201, r.text
    assert r.json()["minutes_actual"] == minutes and r.json()["minutes_billable"] == expected


def test_billable_minutes_unit():
    assert svc.billable_minutes(7, True, 15) == 15
    assert svc.billable_minutes(45, True, 15) == 45
    assert svc.billable_minutes(46, True, 15) == 60
    assert svc.billable_minutes(10, True, 6) == 12
    assert svc.billable_minutes(10, False, 15) == 0


def test_time_increment_setting_applies_to_new_entries(admin, make_ticket):
    admin.patch("/api/settings", json={"billing_increment_minutes": 30})
    t = make_ticket()
    wt = admin.get("/api/work-types").json()[0]["id"]
    r = admin.post(f"/api/tickets/{t['id']}/time", json={"work_type_id": wt, "minutes": 31})
    assert r.json()["minutes_billable"] == 60


def test_time_entry_lifecycle_and_permissions(admin, login, make_ticket):
    tech = login("tech")
    t = make_ticket()
    wt = admin.get("/api/work-types").json()[0]["id"]
    body = {"work_type_id": wt, "minutes": 20, "note": "swapped toner", "work_date": "2026-09-28"}
    mine = tech.post(f"/api/tickets/{t['id']}/time", json=body)
    assert mine.status_code == 201 and mine.json()["user_id"] == tech.user["id"]
    assert mine.json()["work_date"] == "2026-09-28"
    # a tech cannot log time for someone else, or touch someone else's entry
    assert (
        tech.post(
            f"/api/tickets/{t['id']}/time", json={**body, "user_id": admin.user["id"]}
        ).status_code
        == 403
    )
    theirs = admin.post(f"/api/tickets/{t['id']}/time", json=body).json()
    assert tech.patch(f"/api/time-entries/{theirs['id']}", json={"minutes": 5}).status_code == 403
    assert tech.post(f"/api/time-entries/{theirs['id']}/void").status_code == 403
    # admin can log for another user and edit anyone's
    for_tech = admin.post(f"/api/tickets/{t['id']}/time", json={**body, "user_id": tech.user["id"]})
    assert for_tech.status_code == 201 and for_tech.json()["user_id"] == tech.user["id"]
    edited = tech.patch(
        f"/api/time-entries/{mine.json()['id']}",
        json={"minutes": 46, "billable": True, "note": None},
    )
    assert edited.json()["minutes_actual"] == 46 and edited.json()["minutes_billable"] == 60
    assert edited.json()["note"] is None
    assert tech.post(f"/api/time-entries/{mine.json()['id']}/void").json()["voided_at"]
    assert tech.post(f"/api/time-entries/{mine.json()['id']}/void").status_code == 409
    assert (
        tech.patch(f"/api/time-entries/{mine.json()['id']}", json={"minutes": 5}).status_code == 409
    )
    listed = admin.get(f"/api/tickets/{t['id']}/time").json()
    assert mine.json()["id"] not in [e["id"] for e in listed]
    assert mine.json()["id"] in [
        e["id"]
        for e in admin.get(f"/api/tickets/{t['id']}/time", params={"include_voided": True}).json()
    ]


def test_time_validation(admin, make_ticket):
    t = make_ticket()
    wt = admin.get("/api/work-types").json()[0]["id"]
    url = f"/api/tickets/{t['id']}/time"
    assert admin.post(url, json={"work_type_id": wt, "minutes": 0}).status_code == 422
    assert admin.post(url, json={"work_type_id": wt, "minutes": 1441}).status_code == 422
    assert admin.post(url, json={"work_type_id": 999, "minutes": 5}).status_code == 409
    assert (
        admin.post(url, json={"work_type_id": wt, "minutes": 5, "user_id": 999}).status_code == 409
    )
    assert (
        admin.post("/api/tickets/999/time", json={"work_type_id": wt, "minutes": 5}).status_code
        == 404
    )
    assert admin.get("/api/tickets/999/time").status_code == 404
    assert admin.patch("/api/time-entries/999", json={"minutes": 5}).status_code == 404
    assert admin.post("/api/time-entries/999/void").status_code == 404
    e = admin.post(url, json={"work_type_id": wt, "minutes": 5}).json()
    assert (
        admin.patch(f"/api/time-entries/{e['id']}", json={"work_type_id": 999}).status_code == 409
    )
    assert (
        admin.patch(
            f"/api/time-entries/{e['id']}", json={"work_type_id": wt, "work_date": "2026-01-02"}
        ).json()["work_date"]
        == "2026-01-02"
    )


def test_time_writes_are_audited(admin, make_ticket):
    t = make_ticket()
    wt = admin.get("/api/work-types").json()[0]["id"]
    e = admin.post(f"/api/tickets/{t['id']}/time", json={"work_type_id": wt, "minutes": 5}).json()
    admin.patch(f"/api/time-entries/{e['id']}", json={"minutes": 6})
    admin.post(f"/api/time-entries/{e['id']}/void")
    actions = [
        a["action"]
        for a in admin.get("/api/audit", params={"action": "time_entry."}).json()["items"]
    ]
    assert actions == ["time_entry.void", "time_entry.update", "time_entry.create"]


# ---- dashboard ----
def test_dashboard_buckets(admin, login, make_ticket):
    tech = login("tech")
    mine = make_ticket(subject="mine", assignee_id=tech.user["id"])
    unassigned = make_ticket(subject="nobody")
    make_ticket(subject="theirs", assignee_id=admin.user["id"])
    d = tech.get("/api/dashboard").json()
    assert [t["id"] for t in d["my_open"]] == [mine["id"]]
    assert [t["id"] for t in d["unassigned"]] == [unassigned["id"]]
    assert d["counts"]["open"] == 3 and d["counts"]["mine"] == 1
    assert d["counts"]["needs_triage"] == 0


def test_dashboard_lists_breached_tickets_first(admin, owner, make_ticket, freeze):
    old = make_ticket(subject="old", priority_id=pri(admin, "High"))
    make_ticket(subject="fresh", priority_id=pri(admin, "Low"))
    set_created(owner, admin, old["id"], ct(2026, 9, 28, 9))
    freeze(ct(2026, 9, 29, 12))
    risk = admin.get("/api/dashboard").json()["sla_at_risk"]
    assert [t["subject"] for t in risk] == ["old"] and risk[0]["sla_state"] == "breached"
