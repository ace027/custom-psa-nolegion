import pytest
from sqlalchemy import text

from app import notifications, worker
from app.mail import ingest
from tests.mailfakes import MAILBOX, FakeMail, msg


@pytest.fixture
def outbox(owner_engine):
    def _rows():
        with owner_engine.connect() as c:
            return [
                dict(r._mapping)
                for r in c.execute(
                    text(
                        "SELECT to_emails, subject, body_text, send_status FROM email_messages "
                        "WHERE direction = 'out' AND subject LIKE 'PSA:%' ORDER BY id"
                    )
                )
            ]

    return _rows


@pytest.fixture
def tech(login):
    return login("tech")


def assign(admin, ticket, user):
    r = admin.patch(f"/api/tickets/{ticket['id']}", json={"assignee_id": user["id"]})
    assert r.status_code == 200, r.text


def make_due(owner_engine, ticket_id, minutes_from_now):
    with owner_engine.begin() as c:
        c.execute(
            text(
                "UPDATE tickets SET sla_resolution_due = now() + make_interval(mins => :m) "
                "WHERE id = :i"
            ),
            {"m": minutes_from_now, "i": ticket_id},
        )


# ---- assigned ----
def test_assigning_a_ticket_emails_the_new_assignee_only(
    admin, tech, mail_ready, outbox, make_ticket
):
    t = make_ticket(subject="VPN slow")
    assign(admin, t, tech.user)
    [n] = outbox()
    assert n["to_emails"] == [tech.user["email"]] and n["send_status"] == "pending"
    assert f"#{t['number']}" in n["subject"] and "[#" not in n["subject"]
    assert "VPN slow" in n["body_text"] and f"/tickets/{t['id']}" in n["body_text"]
    assert "Acme Corp" in n["body_text"]


def test_assigning_to_yourself_or_creating_a_ticket_for_yourself_sends_nothing(
    admin, mail_ready, outbox, make_ticket
):
    t = make_ticket()
    assign(admin, t, admin.user)
    make_ticket(assignee_id=admin.user["id"])
    assert outbox() == []


def test_creating_a_ticket_assigned_to_someone_else_notifies_them(
    admin, tech, mail_ready, outbox, make_ticket
):
    make_ticket(assignee_id=tech.user["id"])
    assert len(outbox()) == 1


def test_reassigning_back_and_forth_notifies_each_time(
    admin, tech, login, mail_ready, outbox, make_ticket
):
    other = login("tech", "tech2@example.com")
    t = make_ticket()
    assign(admin, t, tech.user)
    assign(admin, t, other.user)
    assign(admin, t, tech.user)
    assert [r["to_emails"][0] for r in outbox()] == [
        tech.user["email"],
        other.user["email"],
        tech.user["email"],
    ]


def test_editing_other_fields_does_not_renotify(admin, tech, mail_ready, outbox, make_ticket):
    t = make_ticket(assignee_id=tech.user["id"])
    admin.patch(f"/api/tickets/{t['id']}", json={"subject": "New subject"})
    assert len(outbox()) == 1


# ---- gates ----
def test_nothing_is_queued_when_mail_is_not_configured(admin, tech, outbox, make_ticket):
    make_ticket(assignee_id=tech.user["id"])
    assert outbox() == []


def test_the_global_switch_and_personal_preferences(admin, tech, mail_ready, outbox, make_ticket):
    assert admin.patch("/api/settings", json={"notify_staff": False}).status_code == 200
    make_ticket(assignee_id=tech.user["id"])
    assert outbox() == []
    admin.patch("/api/settings", json={"notify_staff": True})
    r = tech.patch("/api/auth/me/notifications", json={"notify_assigned": False})
    assert r.status_code == 200 and r.json()["notify_assigned"] is False
    assert r.json()["notify_sla"] is True
    make_ticket(assignee_id=tech.user["id"])
    assert outbox() == []
    assert tech.get("/api/auth/me").json()["notify_assigned"] is False
    row = admin.get("/api/audit", params={"action": "user.notification_prefs"}).json()["items"][0]
    assert row["actor_id"] == tech.user["id"] and row["after"]["notify_assigned"] is False


def test_preferences_are_only_your_own(admin, tech):
    tech.patch("/api/auth/me/notifications", json={"notify_sla": False})
    assert admin.get("/api/auth/me").json()["notify_sla"] is True


def test_inactive_users_are_not_emailed(admin, tech, mail_ready, outbox, make_ticket, owner_engine):
    t = make_ticket()
    with owner_engine.begin() as c:
        c.execute(text("UPDATE users SET is_active = false WHERE id = :i"), {"i": tech.user["id"]})
    admin.patch(f"/api/tickets/{t['id']}", json={"assignee_id": tech.user["id"]})
    assert outbox() == []


# ---- customer reply ----
def test_customer_reply_notifies_the_assignee(
    admin, tech, org_ctx, mail_ready, outbox, make_ticket
):
    t = make_ticket(contact_id=org_ctx["contact"], assignee_id=tech.user["id"])
    mail = FakeMail()
    mail.add(msg(subject=f"RE: [#{t['number']}] Printer down", body="Still broken! SECRET-TEXT"))
    assert ingest.poll_once(mail, MAILBOX) == {"appended": 1}
    rows = outbox()
    assert len(rows) == 2  # the assignment, then the reply
    reply = rows[1]
    assert reply["to_emails"] == [tech.user["email"]] and "new reply" in reply["subject"]
    assert "SECRET-TEXT" not in reply["body_text"]  # facts and a link, never the customer's words


def test_customer_reply_on_an_unassigned_ticket_notifies_nobody(
    admin, org_ctx, mail_ready, outbox, make_ticket
):
    t = make_ticket(contact_id=org_ctx["contact"])
    mail = FakeMail()
    mail.add(msg(subject=f"RE: [#{t['number']}] Printer down", body="Hello?"))
    ingest.poll_once(mail, MAILBOX)
    assert outbox() == []


def test_a_reply_to_a_notification_is_not_a_customer_reply(
    admin, tech, org_ctx, mail_ready, outbox, make_ticket
):
    t = make_ticket(contact_id=org_ctx["contact"], assignee_id=tech.user["id"])
    [n] = outbox()
    mail = FakeMail()
    mail.add(msg(sender=tech.user["email"], subject="RE: " + n["subject"], body="ok on it"))
    ingest.poll_once(mail, MAILBOX)
    notes = admin.get(f"/api/tickets/{t['id']}/notes").json()
    assert all(x["source"] != "email" for x in notes)


# ---- SLA ----
def scan():
    worker.notify_jobs()


def test_sla_at_risk_then_breached_each_notify_once(
    admin, tech, owner_engine, mail_ready, outbox, make_ticket
):
    t = make_ticket(assignee_id=tech.user["id"])
    assert len(outbox()) == 1
    scan()
    assert len(outbox()) == 1  # plenty of time left
    make_due(owner_engine, t["id"], 20)  # inside the at-risk window (target 1440 min, 20%)
    scan()
    scan()
    kinds = [r["subject"] for r in outbox()]
    assert len(kinds) == 2 and "at risk" in kinds[1]
    make_due(owner_engine, t["id"], -5)
    scan()
    scan()
    kinds = [r["subject"] for r in outbox()]
    assert len(kinds) == 3 and "breached" in kinds[2]


def test_sla_is_ignored_for_unassigned_paused_and_done_tickets(
    admin, tech, owner_engine, mail_ready, outbox, make_ticket
):
    unassigned = make_ticket()
    paused = make_ticket(assignee_id=tech.user["id"])
    done = make_ticket(assignee_id=tech.user["id"])
    before = len(outbox())
    admin.patch(f"/api/tickets/{paused['id']}", json={"status": "waiting_on_customer"})
    admin.patch(f"/api/tickets/{done['id']}", json={"status": "resolved"})
    for t in (unassigned, paused, done):
        make_due(owner_engine, t["id"], -60)
    scan()
    assert len(outbox()) == before


def test_sla_scan_does_nothing_without_a_configured_mailbox(
    admin, tech, owner_engine, outbox, make_ticket
):
    t = make_ticket(assignee_id=tech.user["id"])
    make_due(owner_engine, t["id"], -60)
    scan()
    assert outbox() == []


# ---- delivery ----
def test_notifications_are_delivered_by_the_normal_outbox(
    admin, tech, mail_ready, outbox, make_ticket
):
    make_ticket(assignee_id=tech.user["id"])
    mail = FakeMail()
    ingest.send_pending(mail, MAILBOX)
    [sent] = mail.sent
    assert sent["to"] == [tech.user["email"]] and sent["subject"].startswith("PSA: ticket #")
    assert outbox()[0]["send_status"] == "sent"


def test_compose_strips_newlines_from_the_subject_line():
    class Org:
        name = "Acme"

    class Prio:
        name = "Normal"

    class T:
        id, number, status = 1, 10001, "open"
        subject = "Line1\nBcc: evil@example.com"
        organization, priority, sla_resolution_due = Org(), Prio(), None

    subject, body = notifications.compose(T(), "assigned")
    assert "\n" not in subject and "Subject:  Line1 Bcc: evil@example.com" in body
