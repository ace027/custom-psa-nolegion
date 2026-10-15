"""Client appointment emails (REQ-05): debounced queue on change, worker turns due rows into mail."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app import client_notices, worker
from app.db import new_session, set_org_scope

MON = datetime(2030, 1, 7, tzinfo=UTC)  # Chicago is UTC-6: 15:00Z is 9:00 AM CST


def at(hour: int, day: int = 0) -> str:
    return (MON + timedelta(days=day, hours=hour)).isoformat()


def later(minutes: int = 5) -> datetime:
    return datetime.now(UTC) + timedelta(minutes=minutes)


def send(minutes: int = 5) -> int:
    with new_session() as db:
        return client_notices.send_due(db, later(minutes))


@pytest.fixture
def tech(login):
    return login("tech", "tech1@example.com")


@pytest.fixture
def tech2(login):
    return login("tech", "tech2@example.com")


@pytest.fixture
def on(owner):
    owner.execute(text("UPDATE settings SET appointment_emails_enabled = true"))


@pytest.fixture
def ticket(make_ticket, org_ctx):
    return make_ticket(contact_id=org_ctx["contact"])


def book(admin, ticket_id, tech, start=None, end=None, **kw):
    r = admin.post(
        "/api/appointments",
        json={
            "ticket_id": ticket_id,
            "tech_id": tech.user["id"],
            "starts_at": start or at(15),
            "ends_at": end or at(16),
            **kw,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def patch(admin, appt, **body):
    r = admin.patch(f"/api/appointments/{appt}", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def cancel(admin, appt, reason=None):
    r = admin.post(f"/api/appointments/{appt}/cancel", json={"reason": reason})
    assert r.status_code == 200, r.text
    return r.json()


def notices(owner, appt=None):
    q = "SELECT * FROM appointment_notices"
    if appt:
        q += f" WHERE appointment_id = {int(appt)}"
    return owner.execute(text(q + " ORDER BY id")).all()


def mails(owner):
    return owner.execute(
        text("SELECT * FROM email_messages WHERE direction = 'out' ORDER BY id")
    ).all()


# ---- queue ------------------------------------------------------------------------------------
def test_queue_setting_off_queues_nothing(admin, owner, ticket, tech):
    book(admin, ticket["id"], tech)
    assert notices(owner) == []


def test_queue_hidden_or_muted_queues_nothing(admin, owner, on, make_ticket, org_ctx, tech):
    t = make_ticket(contact_id=org_ctx["contact"])
    book(admin, t["id"], tech, client_visible=False)
    book(admin, t["id"], tech, notify_client=False)
    assert notices(owner) == []


def test_queue_creates_one_debounced_pending_row(admin, owner, on, ticket, tech):
    a = book(admin, ticket["id"], tech)
    assert a["notify_client"] is True
    assert a["client_notice"]["state"] == "pending"
    first = notices(owner)[0]
    patch(admin, a["id"], starts_at=at(17), ends_at=at(18))
    rows = notices(owner)
    assert len(rows) == 1 and rows[0].state == "pending"
    assert rows[0].starts_at == MON + timedelta(hours=17)
    assert rows[0].send_after >= first.send_after
    assert rows[0].send_after - datetime.now(UTC) > timedelta(minutes=1)


def test_queue_reassign_or_notes_only_queues_nothing(admin, owner, on, ticket, tech, tech2):
    a = book(admin, ticket["id"], tech)
    assert send() == 1
    patch(admin, a["id"], tech_id=tech2.user["id"])
    patch(admin, a["id"], notes="bring a ladder")
    assert [n.state for n in notices(owner)] == ["sent"]


def test_queue_turning_notify_on_queues(admin, owner, on, ticket, tech):
    a = book(admin, ticket["id"], tech, notify_client=False)
    assert notices(owner) == []
    out = patch(admin, a["id"], notify_client=True)
    assert out["notify_client"] is True and out["client_notice"]["state"] == "pending"
    assert len(notices(owner)) == 1


def test_queue_turning_visible_on_queues(admin, owner, on, ticket, tech):
    a = book(admin, ticket["id"], tech, client_visible=False)
    patch(admin, a["id"], client_visible=True)
    assert len(notices(owner)) == 1


# ---- sending ----------------------------------------------------------------------------------
def test_not_due_yet_is_left_alone(admin, owner, on, ticket, tech):
    book(admin, ticket["id"], tech)
    assert send(0) == 0
    assert notices(owner)[0].state == "pending"


def test_book_then_move_sends_one_booked_email_with_final_time(admin, owner, on, ticket, tech):
    a = book(admin, ticket["id"], tech)
    patch(admin, a["id"], starts_at=at(17), ends_at=at(18))
    assert send() == 1
    (m,) = mails(owner)
    assert m.to_emails == ["pat@acme.com"] and m.send_status == "pending"
    assert m.ticket_id == ticket["id"]
    assert m.subject == f"[Ticket #{ticket['number']}] Appointment booked: Printer down"
    assert "11:00 AM - 12:00 PM CST" in m.body_text
    assert "9:00 AM" not in m.body_text
    n = notices(owner)[0]
    assert (n.state, n.kind, n.email_message_id) == ("sent", "booked", m.id)
    assert n.sent_at is not None


def test_time_shown_in_business_timezone(admin, owner, on, ticket, tech):
    book(admin, ticket["id"], tech)
    send()
    body = mails(owner)[0].body_text
    assert "Monday, January 7, 2030, 9:00 AM - 10:00 AM CST" in body
    assert "Technician: tech" in body
    assert f"#{ticket['number']}" in body and "Printer down" in body


def test_book_then_cancel_before_send_sends_nothing(admin, owner, on, ticket, tech):
    a = book(admin, ticket["id"], tech)
    cancel(admin, a["id"])
    assert send() == 0
    assert mails(owner) == []
    n = notices(owner)[0]
    assert (n.state, n.reason) == ("skipped", "cancelled before any email")


def test_booked_then_moved_sends_old_and_new_times(admin, owner, on, ticket, tech):
    a = book(admin, ticket["id"], tech)
    send()
    patch(admin, a["id"], starts_at=at(17), ends_at=at(18))
    assert send() == 1
    m = mails(owner)[1]
    assert m.subject.startswith(f"[Ticket #{ticket['number']}] Appointment moved:")
    assert "New time: Monday, January 7, 2030, 11:00 AM - 12:00 PM CST" in m.body_text
    assert "Previous time: Monday, January 7, 2030, 9:00 AM - 10:00 AM CST" in m.body_text
    assert [n.kind for n in notices(owner)] == ["booked", "moved"]


def test_move_back_to_the_sent_time_is_skipped(admin, owner, on, ticket, tech):
    a = book(admin, ticket["id"], tech)
    send()
    patch(admin, a["id"], starts_at=at(17), ends_at=at(18))
    patch(admin, a["id"], starts_at=at(15), ends_at=at(16))
    assert send() == 0
    n = notices(owner)[1]
    assert (n.state, n.reason) == ("skipped", "no client-visible change")


def test_cancel_after_a_sent_notice_sends_cancelled(admin, owner, on, ticket, tech):
    a = book(admin, ticket["id"], tech)
    send()
    cancel(admin, a["id"], reason="secret reason")
    assert send() == 1
    m = mails(owner)[1]
    assert m.subject.startswith(f"[Ticket #{ticket['number']}] Appointment cancelled:")
    assert "cancelled" in m.body_text
    assert notices(owner)[1].kind == "cancelled"


def test_body_never_contains_notes_or_cancel_reason(admin, owner, on, ticket, tech):
    a = book(admin, ticket["id"], tech, notes="gate code 4321")
    send()
    patch(admin, a["id"], notes="internal grumble", starts_at=at(17), ends_at=at(18))
    send()
    cancel(admin, a["id"], reason="secret reason")
    send()
    assert len(mails(owner)) == 3
    for m in mails(owner):
        assert "4321" not in m.body_text and "grumble" not in m.body_text
        assert "secret reason" not in m.body_text and "secret reason" not in m.subject


def test_requester_email_fallback(admin, owner, on, make_ticket, tech):
    t = make_ticket()
    owner.execute(
        text("UPDATE tickets SET requester_email = 'walkin@example.org' WHERE id = :i"),
        {"i": t["id"]},
    )
    book(admin, t["id"], tech)
    assert send() == 1
    assert mails(owner)[0].to_emails == ["walkin@example.org"]


def test_contact_without_email_falls_back_to_requester(admin, owner, on, ticket, tech):
    owner.execute(text("UPDATE contacts SET email = NULL"))
    owner.execute(
        text("UPDATE tickets SET requester_email = 'walkin@example.org' WHERE id = :i"),
        {"i": ticket["id"]},
    )
    book(admin, ticket["id"], tech)
    assert send() == 1
    assert mails(owner)[0].to_emails == ["walkin@example.org"]


def test_no_recipient_is_skipped(admin, owner, on, make_ticket, tech):
    book(admin, make_ticket()["id"], tech)
    assert send() == 0
    assert mails(owner) == []
    n = notices(owner)[0]
    assert (n.state, n.reason) == ("skipped", "no recipient")


def test_setting_turned_off_before_send_is_skipped(admin, owner, on, ticket, tech):
    book(admin, ticket["id"], tech)
    owner.execute(text("UPDATE settings SET appointment_emails_enabled = false"))
    assert send() == 0
    assert mails(owner) == []
    assert notices(owner)[0].state == "skipped"


def test_muted_after_queueing_is_skipped(admin, owner, on, ticket, tech):
    a = book(admin, ticket["id"], tech)
    patch(admin, a["id"], notify_client=False)
    assert send() == 0
    assert notices(owner)[0].state == "skipped"


def test_portal_link_only_when_enabled_and_contact_has_access(admin, owner, on, ticket, tech):
    def body_for(start_hour):
        a = book(admin, ticket["id"], tech, at(start_hour), at(start_hour + 1))
        send()
        return mails(owner)[-1].body_text, a

    body, _ = body_for(15)
    assert "/portal" not in body
    owner.execute(text("UPDATE settings SET portal_enabled = true"))
    body, _ = body_for(17)
    assert "/portal" not in body  # contact has no portal access
    owner.execute(text("UPDATE contacts SET portal_access = true"))
    body, _ = body_for(19)
    assert "http://localhost:8000/portal" in body
    owner.execute(text("UPDATE settings SET portal_enabled = false"))
    body, _ = body_for(21)
    assert "/portal" not in body


def test_appointment_deleted_cascades_notices(admin, owner, on, ticket, tech):
    a = book(admin, ticket["id"], tech)
    owner.execute(text("DELETE FROM appointments WHERE id = :i"), {"i": a["id"]})
    assert notices(owner) == []
    assert send() == 0


def test_two_workers_do_not_double_send(admin, owner, on, ticket, tech):
    book(admin, ticket["id"], tech)
    with new_session() as first, new_session() as second:
        set_org_scope(first, "all")
        locked = first.execute(text("SELECT id FROM appointment_notices FOR UPDATE")).all()
        assert len(locked) == 1
        assert client_notices.send_due(second, later()) == 0  # skip-locked: nothing to claim
        first.rollback()
    assert send() == 1
    assert len(mails(owner)) == 1


# ---- responses --------------------------------------------------------------------------------
def test_responses_include_client_notice(admin, owner, on, ticket, tech):
    a = book(admin, ticket["id"], tech)
    assert a["client_notice"]["state"] == "pending"
    assert a["client_notice"]["kind"] is None
    got = admin.get(f"/api/appointments/{a['id']}").json()
    assert got["client_notice"]["state"] == "pending"
    send()
    listed = admin.get("/api/appointments", params={"ticket_id": ticket["id"]}).json()
    assert listed[0]["client_notice"]["state"] == "sent"
    assert listed[0]["client_notice"]["kind"] == "booked"
    assert listed[0]["client_notice"]["sent_at"] is not None
    moved = patch(admin, a["id"], starts_at=at(17), ends_at=at(18))
    assert moved["client_notice"]["state"] == "pending"  # a pending row wins over the sent one
    out = cancel(admin, a["id"])
    assert out["client_notice"]["state"] == "pending"


def test_response_without_any_notice_is_null(admin, ticket, tech):
    a = book(admin, ticket["id"], tech)
    assert a["client_notice"] is None


# ---- worker and isolation ---------------------------------------------------------------------
def test_worker_cycle_sends_due_notices(admin, owner, on, ticket, tech):
    book(admin, ticket["id"], tech)
    owner.execute(text("UPDATE appointment_notices SET send_after = now() - interval '1 minute'"))
    worker.client_notice_jobs()
    assert len(mails(owner)) == 1
    assert notices(owner)[0].state == "sent"


def test_worker_job_survives_a_failure(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(client_notices, "send_due", boom)
    worker.client_notice_jobs()  # logs, does not raise


def test_notices_are_isolated_by_org(admin, owner, on, make_org, ticket, tech):
    other = make_org("Other Co")["id"]
    a = book(admin, ticket["id"], tech)
    org = owner.execute(
        text("SELECT organization_id FROM appointments WHERE id = :i"), {"i": a["id"]}
    ).scalar_one()
    with new_session() as db:
        set_org_scope(db, str(other))
        assert client_notices.latest_for(db, [a["id"]]) == {}
        n = db.execute(text("SELECT count(*) FROM appointment_notices")).scalar_one()
        assert n == 0
    with new_session() as db:
        set_org_scope(db, str(org))
        assert a["id"] in client_notices.latest_for(db, [a["id"]])


# ---- cancellation after hide / mute -----------------------------------------------------------
def test_emailed_then_hidden_then_cancelled_sends_cancelled(admin, owner, on, ticket, tech):
    a = book(admin, ticket["id"], tech)
    assert send() == 1
    patch(admin, a["id"], client_visible=False)
    cancel(admin, a["id"])
    assert send() == 1
    assert [n.kind for n in notices(owner)] == ["booked", "cancelled"]
    assert "Appointment cancelled" in mails(owner)[1].subject


def test_emailed_then_muted_then_cancelled_sends_cancelled(admin, owner, on, ticket, tech):
    a = book(admin, ticket["id"], tech)
    assert send() == 1
    patch(admin, a["id"], notify_client=False)
    cancel(admin, a["id"])
    assert send() == 1
    assert [n.kind for n in notices(owner)] == ["booked", "cancelled"]


def test_cancelled_after_hide_still_needs_master_setting(admin, owner, on, ticket, tech):
    a = book(admin, ticket["id"], tech)
    send()
    patch(admin, a["id"], client_visible=False)
    owner.execute(text("UPDATE settings SET appointment_emails_enabled = false"))
    cancel(admin, a["id"])
    assert send() == 0
    assert len(mails(owner)) == 1


def test_never_emailed_hidden_cancelled_sends_nothing(admin, owner, on, ticket, tech):
    a = book(admin, ticket["id"], tech, client_visible=False)
    cancel(admin, a["id"])
    assert send() == 0
    assert notices(owner) == [] and mails(owner) == []


def test_emailed_then_hidden_then_moved_sends_nothing(admin, owner, on, ticket, tech):
    a = book(admin, ticket["id"], tech)
    assert send() == 1
    patch(admin, a["id"], client_visible=False)
    patch(admin, a["id"], starts_at=at(17), ends_at=at(18))
    assert send() == 0
    assert len(mails(owner)) == 1
    assert [n.state for n in notices(owner)] == ["sent"]


# ---- hardening --------------------------------------------------------------------------------
def test_row_failure_reason_does_not_leak_exception_text(
    admin, owner, on, ticket, tech, monkeypatch
):
    book(admin, ticket["id"], tech)

    def boom(*a, **k):
        raise RuntimeError("secret connection string host=db password=hunter2")

    monkeypatch.setattr(client_notices, "_process", boom)
    assert send() == 0
    n = notices(owner)[0]
    assert n.state == "skipped"
    assert n.reason == "error: internal (RuntimeError); see worker log"
    assert "hunter2" not in n.reason


def test_crlf_subject_renders_on_one_line(admin, owner, on, make_ticket, org_ctx, tech):
    t = make_ticket(contact_id=org_ctx["contact"])
    owner.execute(
        text("UPDATE tickets SET subject = :s WHERE id = :i"),
        {"s": "Printer\r\nBcc: evil@example.org\n  down", "i": t["id"]},
    )
    book(admin, t["id"], tech)
    assert send() == 1
    m = mails(owner)[0]
    assert "\r" not in m.subject and "\n" not in m.subject
    assert m.subject.endswith("Printer Bcc: evil@example.org down")
    assert (
        f"Ticket: #{t['number']} - Printer Bcc: evil@example.org down" in m.body_text.splitlines()
    )
