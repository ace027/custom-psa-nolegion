"""Parity phase 1, slice B: holidays in SLA math, auto-acknowledgement, escalation."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from app import worker
from app.mail import ingest
from app.sla import Calendar, add_business_minutes, business_minutes_between
from tests.mailfakes import MAILBOX, FakeMail, msg

CT = ZoneInfo("America/Chicago")


def ct(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=CT).astimezone(UTC)


WEEK = frozenset({0, 1, 2, 3, 4})


# ---- holiday maths (pure) ----
def test_a_closed_day_is_skipped():
    cal = Calendar(CT, WEEK, 480, 1020, {date(2026, 9, 28): None})  # Monday closed
    assert add_business_minutes(ct(2026, 9, 25, 16, 30), 60, cal) == ct(2026, 9, 29, 8, 30)
    open_cal = Calendar(CT, WEEK, 480, 1020)
    assert add_business_minutes(ct(2026, 9, 25, 16, 30), 60, open_cal) == ct(2026, 9, 28, 8, 30)
    assert business_minutes_between(ct(2026, 9, 25, 16, 30), ct(2026, 9, 29, 8, 30), cal) == 60


def test_a_shortened_day_uses_its_own_hours():
    cal = Calendar(CT, WEEK, 480, 1020, {date(2026, 9, 28): (540, 720)})  # Mon 09:00-12:00
    assert add_business_minutes(ct(2026, 9, 25, 16, 30), 60, cal) == ct(2026, 9, 28, 9, 30)
    assert add_business_minutes(ct(2026, 9, 28, 11, 30), 60, cal) == ct(2026, 9, 29, 8, 30)


def test_exceptions_never_open_a_non_business_day():
    sat = date(2026, 9, 26)
    cal = Calendar(CT, WEEK, 480, 1020, {sat: (540, 720)})
    assert add_business_minutes(ct(2026, 9, 25, 16, 30), 60, cal) == ct(2026, 9, 28, 8, 30)


# ---- holiday API ----
def test_holiday_crud_validation_and_audit(admin):
    r = admin.post("/api/holidays", json={"on_date": "2026-12-25", "name": "Christmas"})
    assert r.status_code == 201, r.text
    hid = r.json()["id"]
    assert (
        admin.post("/api/holidays", json={"on_date": "2026-12-25", "name": "Dup"}).status_code
        == 409
    )
    half = {
        "on_date": "2026-12-24",
        "name": "Christmas Eve",
        "open_minute": 480,
        "close_minute": 720,
    }
    assert admin.post("/api/holidays", json=half).status_code == 201
    bad = {"on_date": "2026-12-31", "name": "NYE"}
    assert admin.post("/api/holidays", json={**bad, "open_minute": 480}).status_code == 422
    assert (
        admin.post(
            "/api/holidays", json={**bad, "open_minute": 700, "close_minute": 600}
        ).status_code
        == 422
    )
    assert admin.post("/api/holidays", json={**bad, "name": "  "}).status_code == 422
    assert [h["on_date"] for h in admin.get("/api/holidays", params={"year": 2026}).json()] == [
        "2026-12-24",
        "2026-12-25",
    ]
    assert admin.get("/api/holidays", params={"year": 2027}).json() == []
    ok = admin.put(f"/api/holidays/{hid}", json={"on_date": "2026-12-25", "name": "Xmas Day"})
    assert ok.status_code == 200 and ok.json()["name"] == "Xmas Day"
    assert admin.delete(f"/api/holidays/{hid}").status_code == 204
    assert admin.delete(f"/api/holidays/{hid}").status_code == 404
    actions = [
        a["action"] for a in admin.get("/api/audit", params={"action": "holiday."}).json()["items"]
    ]
    assert {"holiday.create", "holiday.update", "holiday.delete"} <= set(actions)


def test_holiday_permissions(login, admin):
    tech, ro = login("tech"), login("read_only")
    body = {"on_date": "2026-07-04", "name": "Independence Day"}
    assert tech.get("/api/holidays").status_code == 200
    assert tech.post("/api/holidays", json=body).status_code == 403
    assert ro.post("/api/holidays", json=body).status_code == 403
    hid = admin.post("/api/holidays", json=body).json()["id"]
    assert tech.put(f"/api/holidays/{hid}", json=body).status_code == 403
    assert tech.delete(f"/api/holidays/{hid}").status_code == 403


def test_new_tickets_use_the_holiday_calendar(admin, owner, make_ticket):
    before = make_ticket()
    owner.execute(
        text(
            "INSERT INTO holidays (on_date, name) "
            "SELECT d::date, 'Closed' FROM generate_series(current_date - 1, current_date + 10, "
            "interval '1 day') d"
        )
    )
    after = make_ticket()
    due = lambda t: datetime.fromisoformat(t["sla_resolution_due"])  # noqa: E731
    assert (due(after) - datetime.now(UTC)).days >= 9
    assert (due(before) - datetime.now(UTC)).days < 9  # existing ticket not rewritten


# ---- auto-acknowledgement ----
@pytest.fixture
def mail():
    return FakeMail()


@pytest.fixture
def acks(owner):
    def _rows():
        return owner.execute(
            text(
                "SELECT to_emails, subject, body_text, auto_generated, ticket_id "
                "FROM email_messages WHERE direction='out' AND auto_generated "
                "AND subject LIKE '[#%' ORDER BY id"
            )
        ).fetchall()

    return _rows


def enable_ack(admin, **kw):
    r = admin.patch("/api/settings", json={"auto_ack_enabled": True, **kw})
    assert r.status_code == 200, r.text


def test_ack_is_off_by_default(admin, org_ctx, mail, acks):
    assert admin.get("/api/settings").json()["auto_ack_enabled"] is False
    mail.add(msg())
    ingest.poll_once(mail, MAILBOX)
    assert acks() == []


def test_ack_for_a_known_contact_threads_and_is_marked_automatic(admin, org_ctx, mail, acks):
    enable_ack(admin)
    mail.add(msg())
    assert ingest.poll_once(mail, MAILBOX) == {"ticket_created": 1}
    [a] = acks()
    t = admin.get("/api/tickets").json()["items"][0]
    assert a.to_emails == ["pat@acme.com"] and a.ticket_id == t["id"] and a.auto_generated
    assert a.subject.startswith(f"[#{t['number']}]") and "Pat Customer" in a.body_text
    ingest.send_pending(mail, MAILBOX)
    sent = mail.sent[-1]
    assert sent["headers"]["X-Auto-Response-Suppress"] == "All"
    assert sent["headers"]["X-PSA-Auto-Reply"] == "ack"


def test_ack_is_not_sent_to_unknown_senders_automated_mail_or_replies(admin, org_ctx, mail, acks):
    enable_ack(admin)
    mail.add(msg(sender="stranger@nowhere.example"))
    mail.add(msg(headers={"Auto-Submitted": "auto-replied"}, subject="Out of office"))
    mail.add(msg(sender="noreply@acme.com"))
    ingest.poll_once(mail, MAILBOX)
    assert acks() == []
    mail.add(msg(subject="Second problem"))
    ingest.poll_once(mail, MAILBOX)
    [a] = acks()
    number = a.subject.split("]")[0][2:]
    mail.add(msg(subject=f"RE: [#{number}] Second problem", body="more info"))
    assert ingest.poll_once(mail, MAILBOX) == {"appended": 1}
    assert len(acks()) == 1  # a reply never triggers another acknowledgement


def test_ack_is_capped_per_sender_per_day(admin, org_ctx, mail, acks):
    enable_ack(admin)
    for i in range(5):
        mail.add(msg(subject=f"Problem {i}"))
    ingest.poll_once(mail, MAILBOX)
    assert len(admin.get("/api/tickets").json()["items"]) == 5
    assert len(acks()) == 3


def test_ack_template_is_validated_and_always_threads(admin, org_ctx, mail, acks):
    assert admin.patch("/api/settings", json={"auto_ack_body": "Hi {nope}"}).status_code == 409
    enable_ack(admin, auto_ack_subject="Thanks {contact_name}")
    mail.add(msg())
    ingest.poll_once(mail, MAILBOX)
    [a] = acks()
    assert a.subject.startswith("[#") and "Thanks Pat Customer" in a.subject


def test_escalation_settings_validation(admin):
    assert (
        admin.patch("/api/settings", json={"escalation_email": "not an email"}).status_code == 422
    )
    ok = admin.patch("/api/settings", json={"escalation_email": "boss@msp.example"})
    assert ok.json()["escalation_email"] == "boss@msp.example"
    cleared = admin.patch("/api/settings", json={"escalation_email": ""})
    assert cleared.json()["escalation_email"] is None


# ---- escalation ----
@pytest.fixture
def escalations(owner):
    def _rows():
        return owner.execute(
            text(
                "SELECT to_emails, subject, body_text FROM email_messages "
                "WHERE direction='out' AND subject LIKE 'PSA escalation:%' ORDER BY id"
            )
        ).fetchall()

    return _rows


def make_breached(owner, ticket_id):
    owner.execute(
        text("UPDATE tickets SET sla_resolution_due = now() - interval '5 minutes' WHERE id = :i"),
        {"i": ticket_id},
    )


def test_breach_escalates_once_to_the_configured_address(
    admin, owner, mail_ready, escalations, make_ticket
):
    t = make_ticket()
    make_breached(owner, t["id"])
    worker.notify_jobs()
    assert escalations() == []  # nothing configured, nothing sent
    admin.patch("/api/settings", json={"escalation_email": "boss@msp.example"})
    worker.notify_jobs()
    worker.notify_jobs()
    [e] = escalations()
    assert e.to_emails == ["boss@msp.example"] and f"#{t['number']}" in e.subject
    assert admin.get(f"/api/tickets/{t['id']}").json()["priority_name"] == "Normal"  # no bump


def test_escalation_ignores_healthy_and_finished_tickets(
    admin, owner, mail_ready, escalations, make_ticket
):
    admin.patch("/api/settings", json={"escalation_email": "boss@msp.example"})
    make_ticket()  # healthy
    done = make_ticket()
    make_breached(owner, done["id"])
    admin.patch(f"/api/tickets/{done['id']}", json={"status": "resolved"})
    worker.notify_jobs()
    assert escalations() == []


def test_optional_priority_bump_is_audited(admin, owner, mail_ready, escalations, make_ticket):
    admin.patch("/api/settings", json={"escalation_bump_priority": True})
    prios = sorted(admin.get("/api/priorities").json(), key=lambda p: p["rank"])
    normal = next(p for p in prios if p["name"] == "Normal")
    higher = [p for p in prios if p["rank"] < normal["rank"]][-1]
    t = make_ticket()
    make_breached(owner, t["id"])
    worker.notify_jobs()
    worker.notify_jobs()
    assert admin.get(f"/api/tickets/{t['id']}").json()["priority_id"] == higher["id"]
    assert escalations() == []  # no address configured: bump only
    actions = [
        a["action"] for a in admin.get("/api/audit", params={"action": "ticket."}).json()["items"]
    ]
    assert actions.count("ticket.update") >= 1
