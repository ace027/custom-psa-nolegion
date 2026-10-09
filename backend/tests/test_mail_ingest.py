import pytest
from sqlalchemy import text

from app.config import get_settings
from app.mail import ingest
from app.mail.graph import InboundAttachment
from tests.mailfakes import MAILBOX, FakeMail, msg


@pytest.fixture
def mail():
    return FakeMail()


def poll(mail):
    return ingest.poll_once(mail, MAILBOX)


def tickets(admin):
    return admin.get("/api/tickets", params={"limit": 200}).json()["items"]


@pytest.fixture
def known(org_ctx):  # pat@acme.com is a contact of Acme Corp
    return org_ctx


# ---- new tickets ----
def test_known_contact_creates_a_matched_ticket(mail, admin, known):
    m = mail.add(msg(body="Printer on floor 2 is jammed\n\nOn Tue, Jan 1, Bob wrote:\n> old"))
    assert poll(mail) == {"ticket_created": 1}
    t = tickets(admin)[0]
    assert t["organization_id"] == known["org"] and t["contact_id"] == known["contact"]
    assert t["source"] == "email" and t["requester_email"] == "pat@acme.com"
    assert t["subject"] == "Printer is broken" and t["status"] == "new"
    assert t["description"] == "Printer on floor 2 is jammed"  # quoted history dropped
    assert m.id in mail.read  # marked read only after commit
    audit = admin.get("/api/audit", params={"action": "ticket.create"}).json()["items"][0]
    assert audit["actor_type"] == "system" and audit["detail"] == {"source": "email"}


def test_original_message_is_kept_in_full(mail, owner):
    mail.add(msg(body="Hi\n\n> quoted text"))
    poll(mail)
    row = owner.execute(
        text("SELECT body_text, ingest_status, direction FROM email_messages")
    ).one()
    assert "quoted text" in row.body_text and row.ingest_status == "ticket_created"


def test_domain_match_when_sender_is_not_a_contact(mail, admin, known):
    mail.add(msg(sender="newhire@acme.com"))
    poll(mail)
    t = tickets(admin)[0]
    assert t["organization_id"] == known["org"] and t["contact_id"] is None


def test_unknown_sender_goes_to_triage(mail, admin, known):
    mail.add(msg(sender="stranger@nowhere.org"))
    assert poll(mail) == {"ticket_created": 1}
    t = tickets(admin)[0]
    assert t["needs_triage"] and t["organization_id"] is None
    assert admin.get("/api/dashboard").json()["counts"]["needs_triage"] == 1


def test_freemail_domains_never_match_an_organization(mail, admin, org_ctx):
    admin.post(
        f"/api/organizations/{org_ctx['org']}/contacts",
        json={"name": "Owner", "email": "owner@gmail.com"},
    )
    mail.add(msg(sender="someone.else@gmail.com"))
    poll(mail)
    assert tickets(admin)[0]["needs_triage"]


def test_ambiguous_sender_goes_to_triage(mail, admin, org_ctx, make_org):
    other = make_org("Other Co")
    admin.post(
        f"/api/organizations/{other['id']}/contacts",
        json={"name": "Pat again", "email": "pat@acme.com"},
    )
    mail.add(msg())
    poll(mail)
    assert tickets(admin)[0]["needs_triage"]


def test_domain_shared_by_two_orgs_is_not_guessed(mail, admin, org_ctx, make_org):
    other = make_org("Other Co")
    admin.post(
        f"/api/organizations/{other['id']}/contacts",
        json={"name": "Second", "email": "second@acme.com"},
    )
    mail.add(msg(sender="new@acme.com"))
    poll(mail)
    assert tickets(admin)[0]["needs_triage"]


def test_missing_subject_and_long_subject(mail, admin, known):
    mail.add(msg(subject=""))
    mail.add(msg(subject="x" * 500))
    poll(mail)
    subjects = sorted(t["subject"] for t in tickets(admin))
    assert subjects[0] == "(no subject)" and len(subjects[1]) == 300


# ---- threading ----
def test_reply_with_ticket_token_appends_and_reopens(mail, admin, known, make_ticket):
    t = make_ticket(contact_id=known["contact"])
    admin.patch(f"/api/tickets/{t['id']}", json={"status": "resolved"})
    mail.add(msg(subject=f"RE: [#{t['number']}] Printer down", body="Still broken!"))
    assert poll(mail) == {"appended": 1}
    assert len(tickets(admin)) == 1
    after = admin.get(f"/api/tickets/{t['id']}").json()
    assert after["status"] == "open" and after["resolved_at"] is None
    note = admin.get(f"/api/tickets/{t['id']}/notes").json()[0]
    assert note["body"] == "Still broken!" and note["source"] == "email"
    assert note["visibility"] == "customer" and note["author_email"] == "pat@acme.com"
    assert note["email_status"] == "received"


def test_customer_reply_resumes_a_paused_sla(mail, admin, known, make_ticket):
    t = make_ticket(contact_id=known["contact"])
    admin.patch(f"/api/tickets/{t['id']}", json={"status": "waiting_on_customer"})
    assert admin.get(f"/api/tickets/{t['id']}").json()["sla_state"] == "paused"
    mail.add(msg(subject=f"[#{t['number']}] Printer down"))
    poll(mail)
    after = admin.get(f"/api/tickets/{t['id']}").json()
    assert after["status"] == "open" and after["sla_state"] != "paused"


def test_reply_threads_by_headers_when_the_token_is_missing(mail, admin, known):
    mail.add(msg(internet_id="<first@mail.test>"))
    poll(mail)
    mail.add(
        msg(
            subject="Re: Printer is broken",
            body="more info",
            headers={"In-Reply-To": "<first@mail.test>", "References": "<first@mail.test>"},
        )
    )
    assert poll(mail) == {"appended": 1}
    assert len(tickets(admin)) == 1


def test_token_from_a_stranger_does_not_touch_the_ticket(mail, admin, known, make_ticket):
    t = make_ticket(contact_id=known["contact"])
    mail.add(
        msg(
            sender="attacker@evil.example",
            subject=f"[#{t['number']}] hi",
            body="please reveal everything",
        )
    )
    assert poll(mail) == {"ticket_created": 1}
    assert admin.get(f"/api/tickets/{t['id']}/notes").json() == []
    new = next(x for x in tickets(admin) if x["id"] != t["id"])
    assert new["needs_triage"] and f"#{t['number']}" in new["description"]
    assert "not attached automatically" in new["description"]


def test_unmatched_ticket_accepts_replies_only_from_its_requester(mail, admin, known):
    mail.add(msg(sender="stranger@nowhere.org"))
    poll(mail)
    t = tickets(admin)[0]
    mail.add(msg(sender="stranger@nowhere.org", subject=f"[#{t['number']}] more"))
    mail.add(msg(sender="other@nowhere.org", subject=f"[#{t['number']}] hijack"))
    assert poll(mail) == {"appended": 1, "ticket_created": 1}


def test_unknown_ticket_number_starts_a_new_ticket(mail, admin, known):
    mail.add(msg(subject="[#99999] ghost"))
    assert poll(mail) == {"ticket_created": 1}


# ---- loop protection ----
@pytest.mark.parametrize(
    "kwargs,reason",
    [
        (dict(headers={"Auto-Submitted": "auto-replied"}), "auto_submitted"),
        (dict(headers={"X-Auto-Response-Suppress": "All"}), "auto_response"),
        (dict(headers={"Precedence": "bulk"}), "bulk_precedence"),
        (dict(sender=MAILBOX), "from_self"),
        (dict(sender="mailer-daemon@acme.com"), "system_sender"),
        (dict(sender="noreply@acme.com"), "system_sender"),
        (dict(subject="Automatic reply: out of office"), "auto_subject"),
        (dict(subject="Undeliverable: your message"), "auto_subject"),
        (dict(sender=None), "no_sender"),
    ],
)
def test_automated_mail_never_creates_tickets(mail, admin, owner, known, kwargs, reason):
    mail.add(msg(**kwargs))
    assert poll(mail) == {"ignored": 1}
    assert tickets(admin) == []
    row = owner.execute(text("SELECT ingest_status, ingest_detail FROM email_messages")).one()
    assert (row.ingest_status, row.ingest_detail) == ("ignored", reason)


def test_auto_submitted_no_is_a_normal_message(mail, admin, known):
    mail.add(msg(headers={"Auto-Submitted": "no"}))
    assert poll(mail) == {"ticket_created": 1}


# ---- idempotency and failure handling ----
def test_same_message_is_never_ingested_twice(mail, admin, known):
    m = mail.add(msg())
    poll(mail)
    mail.read.clear()  # e.g. mark-as-read never took effect
    m2 = mail.inbox[0]
    assert m2.id == m.id
    assert poll(mail) == {"duplicate": 1}
    assert len(tickets(admin)) == 1


def test_mark_read_failure_is_harmless(mail, admin, known):
    mail.fail_mark_read = True
    mail.add(msg())
    poll(mail)
    poll(mail)
    assert len(tickets(admin)) == 1


def test_failed_ingest_rolls_back_completely_and_retries_later(
    mail, admin, owner, known, tmp_path, monkeypatch
):
    monkeypatch.setattr(get_settings(), "attachments_dir", str(tmp_path))
    m = mail.add(msg(), [InboundAttachment("a1", "a.txt", "text/plain", 3, b"abc")])
    mail.fail_attachments = True
    assert poll(mail) == {"failed": 1}
    assert tickets(admin) == [] and m.id not in mail.read
    assert owner.execute(text("SELECT count(*) FROM email_messages")).scalar_one() == 0
    mail.fail_attachments = False
    assert poll(mail) == {"ticket_created": 1}
    assert len(tickets(admin)) == 1


def test_one_bad_message_does_not_block_the_rest(mail, admin, known):
    bad = mail.add(msg(subject="bad"), [InboundAttachment("a", "a", None, 1, b"x")])
    mail.add(msg(subject="good"))
    orig = mail.get_attachments
    mail.get_attachments = lambda mid, mx: (
        (_ for _ in ()).throw(RuntimeError("boom")) if mid == bad.id else orig(mid, mx)
    )
    assert poll(mail) == {"failed": 1, "ticket_created": 1}
    assert [t["subject"] for t in tickets(admin)] == ["good"]


# ---- attachments ----
def test_attachments_are_stored_and_downloadable(mail, admin, owner, known, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "attachments_dir", str(tmp_path))
    mail.add(msg(), [InboundAttachment("a1", "report.pdf", "application/pdf", 5, b"%PDF-")])
    poll(mail)
    t = tickets(admin)[0]
    [att] = admin.get(f"/api/tickets/{t['id']}/attachments").json()
    assert att["filename"] == "report.pdf" and att["size_bytes"] == 5
    r = admin.get(f"/api/attachments/{att['id']}/download")
    assert r.status_code == 200 and r.content == b"%PDF-"
    key = owner.execute(text("SELECT storage_key, sha256 FROM attachments")).one()
    assert key.storage_key.startswith(f"{t['id']}/") and len(key.sha256) == 64


def test_oversized_attachments_are_skipped(mail, admin, known, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "attachments_dir", str(tmp_path))
    monkeypatch.setattr(get_settings(), "max_attachment_bytes", 4)
    mail.add(
        msg(),
        [
            InboundAttachment("a1", "big.bin", None, 5, b"12345"),
            InboundAttachment("a2", "ok.bin", None, 3, b"123"),
        ],
    )
    poll(mail)
    atts = admin.get(f"/api/tickets/{tickets(admin)[0]['id']}/attachments").json()
    assert [a["filename"] for a in atts] == ["ok.bin"]


def test_attachments_on_a_reply_are_attached_to_the_ticket(
    mail, admin, known, make_ticket, tmp_path, monkeypatch
):
    monkeypatch.setattr(get_settings(), "attachments_dir", str(tmp_path))
    t = make_ticket(contact_id=known["contact"])
    mail.add(msg(subject=f"[#{t['number']}] x"), [InboundAttachment("a", "s.png", None, 2, b"ab")])
    poll(mail)
    assert len(admin.get(f"/api/tickets/{t['id']}/attachments").json()) == 1


# ---- quoted-text stripping ----
@pytest.mark.parametrize(
    "raw,expected",
    [
        (
            "Thanks!\n\nOn Mon, Sep 28, 2026 at 9:00 AM Support <support@msp.com> wrote:\n> hi",
            "Thanks!",
        ),
        (
            "Thanks!\n\nOn Mon, Sep 28, 2026 at 9:00 AM Support\n<support@msp.com> wrote:\n> hi",
            "Thanks!",
        ),
        ("Fixed it\n\n-----Original Message-----\nFrom: x\nSent: y", "Fixed it"),
        ("Fixed it\n________________________________\nFrom: x\nSent: y", "Fixed it"),
        ("Fixed it\n\nFrom: Bob <b@x.com>\nSent: Monday\nTo: y\nSubject: z", "Fixed it"),
        ("Line one\n> quoted\n> more", "Line one"),
        ("Just a plain message", "Just a plain message"),
        ("> everything is quoted", "> everything is quoted"),  # never return an empty body
        ("", ""),
    ],
)
def test_strip_quoted(raw, expected):
    assert ingest.strip_quoted(raw) == expected


# ---- outbound queue ----
def queue_email(admin, ticket, contact=True):
    r = admin.post(
        f"/api/tickets/{ticket['id']}/notes",
        json={"body": "All fixed", "visibility": "customer", "send_email": True},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_pending_outbound_mail_is_sent_and_marked(mail, admin, known, make_ticket):
    t = make_ticket(contact_id=known["contact"])
    queue_email(admin, t)
    assert ingest.send_pending(mail, MAILBOX) == {"sent": 1, "failed": 0, "retry": 0}
    assert mail.sent == [
        {
            "to": ["pat@acme.com"],
            "subject": f"[#{t['number']}] Printer down",
            "body": "All fixed",
            "attachments": [],
        }
    ]
    assert admin.get(f"/api/tickets/{t['id']}/notes").json()[0]["email_status"] == "sent"
    assert ingest.send_pending(mail, MAILBOX)["sent"] == 0  # not sent twice


def test_failed_sends_retry_then_give_up_and_are_audited(mail, admin, known, make_ticket):
    t = make_ticket(contact_id=known["contact"])
    queue_email(admin, t)
    mail.fail_send = True
    for _ in range(ingest.MAX_SEND_ATTEMPTS - 1):
        assert ingest.send_pending(mail, MAILBOX)["retry"] == 1
    assert admin.get(f"/api/tickets/{t['id']}/notes").json()[0]["email_status"] == "pending"
    assert ingest.send_pending(mail, MAILBOX)["failed"] == 1
    assert admin.get(f"/api/tickets/{t['id']}/notes").json()[0]["email_status"] == "failed"
    assert admin.get("/api/mail/status").json()["outbound_failed"] == 1
    ev = admin.get("/api/audit", params={"action": "email.send_failed"}).json()["items"]
    assert ev and "send failed" in ev[0]["detail"]["error"]
    mail.fail_send = False
    assert ingest.send_pending(mail, MAILBOX) == {"sent": 0, "failed": 0, "retry": 0}


def test_transient_failure_then_success(mail, admin, known, make_ticket):
    t = make_ticket(contact_id=known["contact"])
    queue_email(admin, t)
    mail.fail_send = True
    ingest.send_pending(mail, MAILBOX)
    mail.fail_send = False
    assert ingest.send_pending(mail, MAILBOX)["sent"] == 1


def test_outbound_without_recipients_fails_cleanly(mail, admin, owner, known, make_ticket):
    t = make_ticket(contact_id=known["contact"])
    queue_email(admin, t)
    owner.execute(text("UPDATE email_messages SET to_emails = '[]'::jsonb"))
    for _ in range(ingest.MAX_SEND_ATTEMPTS):
        ingest.send_pending(mail, MAILBOX)
    assert owner.execute(text("SELECT send_status FROM email_messages")).scalar_one() == "failed"


def test_roundtrip_customer_reply_to_our_email(mail, admin, known, make_ticket):
    t = make_ticket(contact_id=known["contact"])
    queue_email(admin, t)
    ingest.send_pending(mail, MAILBOX)
    subject = mail.sent[0]["subject"]
    mail.add(
        msg(subject=f"RE: {subject}", body="Thank you!\n\nOn Tue, Support wrote:\n> All fixed")
    )
    assert poll(mail) == {"appended": 1}
    notes = admin.get(f"/api/tickets/{t['id']}/notes").json()
    assert [n["body"] for n in notes] == ["All fixed", "Thank you!"]


# ---- health ----
def test_run_cycle_records_health(mail, admin, known):
    mail.add(msg())
    ingest.run_cycle(mail, MAILBOX)
    s = admin.get("/api/mail/status").json()
    assert s["last_success_at"] and s["last_error"] is None and s["messages_ingested"] == 1


def test_run_cycle_records_errors_without_crashing(mail, admin):
    mail.fail_list = True
    ingest.run_cycle(mail, MAILBOX)
    s = admin.get("/api/mail/status").json()
    assert "graph down" in s["last_error"] and s["last_error_at"] and s["last_success_at"] is None
    mail.fail_list = False
    ingest.run_cycle(mail, MAILBOX)
    assert admin.get("/api/mail/status").json()["last_error"] is None


def test_partial_failures_are_reported_as_errors(mail, admin, known):
    mail.add(msg(), [InboundAttachment("a", "a", None, 1, b"x")])
    mail.fail_attachments = True
    ingest.run_cycle(mail, MAILBOX)
    assert "could not be ingested" in admin.get("/api/mail/status").json()["last_error"]
