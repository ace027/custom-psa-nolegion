from datetime import timedelta

import pytest

from app import notices as nsvc
from app.mail import ingest
from tests.conftest import biz_today
from tests.mailfakes import MAILBOX, FakeMail
from tests.test_payments import final_invoice, pay


# ---- fixtures / helpers ----
def overdue(biller, org, cents=10000):
    """An invoice due TODAY (terms 0): it becomes N days overdue when the clock moves N days."""
    return final_invoice(biller, org, cents, invoice_date=biz_today(), terms=0)


def prepare(biller):
    r = biller.post("/api/billing-notices/prepare-reminders")
    assert r.status_code == 200, r.text
    return r.json()


def notices(client, **params):
    return client.get("/api/billing-notices", params=params).json()["items"]


def set_gap(admin, days):
    assert admin.patch("/api/settings", json={"reminder_min_gap_days": days}).status_code == 200


# ---- templates and stages ----
def test_default_schedule_is_1_15_30_60(biller):
    stages = biller.get("/api/billing/reminder-stages").json()
    assert [(s["name"], s["days_past_due"]) for s in stages] == [
        ("Friendly reminder", 1),
        ("Follow-up", 15),
        ("Second notice", 30),
        ("Final notice", 60),
    ]
    assert all(s["enabled"] for s in stages)
    assert "{invoice_list}" in stages[0]["body"] and "{company}" in stages[0]["subject"]


def test_stage_edit_validation(admin, biller, login):
    s = biller.get("/api/billing/reminder-stages").json()[0]
    ok = biller.patch(
        f"/api/billing/reminder-stages/{s['id']}",
        json={
            "subject": "Hi {client}",
            "body": "Owed: {total_due}\n{invoice_list}",
            "days_past_due": 3,
        },
    )
    assert ok.status_code == 200 and ok.json()["days_past_due"] == 3
    for bad in (
        {"subject": "Hi {clinet}"},
        {"body": "Dear {contact}"},
        {"body": "{client.__class__}{0}{invoice_list}"},
    ):
        r = biller.patch(f"/api/billing/reminder-stages/{s['id']}", json=bad)
        assert r.status_code == 409 and "Unknown placeholder" in r.json()["detail"], bad
    second = biller.get("/api/billing/reminder-stages").json()[1]
    assert (
        biller.patch(
            f"/api/billing/reminder-stages/{second['id']}", json={"days_past_due": 3}
        ).status_code
        == 409
    )  # already used by another stage
    assert biller.patch("/api/billing/reminder-stages/999", json={"name": "x"}).status_code == 404
    assert (
        biller.patch(
            f"/api/billing/reminder-stages/{s['id']}", json={"days_past_due": 999}
        ).status_code
        == 422
    )
    assert (
        login("tech")
        .patch(f"/api/billing/reminder-stages/{s['id']}", json={"enabled": False})
        .status_code
        == 403
    )
    assert any(
        a["action"] == "reminder_stage.update"
        for a in admin.get("/api/audit", params={"action": "reminder_stage."}).json()["items"]
    )


def test_render_substitutes_only_known_placeholders_and_never_evaluates():
    values = {"client": "Acme", "total_due": "$5.00"}
    assert nsvc.render("Hi {client}, owe {total_due}", values) == "Hi Acme, owe $5.00"
    assert (
        nsvc.render("{unknown} {client.__class__} {0}", values)
        == "{unknown} {client.__class__} {0}"
    )
    with pytest.raises(Exception, match="Unknown placeholder"):
        nsvc.validate_template("{nope}")
    nsvc.validate_template("{client} {invoice_list} {company}")


# ---- preparing reminders ----
def test_nothing_is_prepared_until_something_is_overdue(biller, client_org, clock):
    overdue(biller, client_org)
    assert prepare(biller) == {"created": 0, "notice_ids": []}  # due today: not overdue yet
    clock(1)
    assert prepare(biller)["created"] == 1


def test_first_reminder_is_prepared_pending_for_the_billing_contact(
    biller, client_org, clock, company
):
    inv = overdue(biller, client_org, 32475)
    clock(5)
    [n] = [notices(biller)[0]] if prepare(biller)["created"] == 1 else []
    assert (n["kind"], n["status"], n["manual"], n["stage_name"]) == (
        "reminder",
        "pending",
        False,
        "Friendly reminder",
    )
    assert n["to_emails"] == ["pat@acme.com"] and n["blocked_reason"] is None
    assert n["organization_name"] == "Acme Corp" and n["total_due_cents"] == 32475
    assert n["subject"] == "Friendly reminder: past-due invoice(s) from Acme MSP LLC"
    assert n["body_text"].startswith("Hello Pat,")
    assert inv["number"] in n["body_text"] and "5 days past due" in n["body_text"]
    assert "$324.75" in n["body_text"] and "Acme MSP LLC" in n["body_text"]
    [row] = n["invoices"]
    assert (row["number"], row["balance_cents"], row["days_past_due"], row["new_stage"]) == (
        inv["number"],
        32475,
        5,
        True,
    )
    assert n["stale"] is False


def test_preparing_twice_does_not_duplicate(biller, client_org, clock):
    overdue(biller, client_org)
    clock(3)
    assert prepare(biller)["created"] == 1
    assert prepare(biller)["created"] == 0
    assert len(notices(biller)) == 1


def test_a_very_late_invoice_gets_only_the_highest_stage_not_all_of_them(biller, client_org, clock):
    overdue(biller, client_org)
    clock(40)  # eligible for stages 1, 15 and 30
    prepare(biller)
    [n] = notices(biller)
    assert n["stage_name"] == "Second notice" and len(n["invoices"]) == 1


def test_stages_escalate_and_never_repeat_or_go_backwards(
    admin, biller, client_org, clock, mail_ready
):
    set_gap(admin, 0)
    overdue(biller, client_org)
    seen = []
    for day, expected in (
        (1, "Friendly reminder"),
        (16, "Follow-up"),
        (31, "Second notice"),
        (61, "Final notice"),
    ):
        clock(day)
        assert prepare(biller)["created"] == 1, day
        n = notices(biller, status="pending")[0]
        assert n["stage_name"] == expected
        assert biller.post(f"/api/billing-notices/{n['id']}/send").status_code == 200
        seen.append(expected)
        assert prepare(biller)["created"] == 0  # same day: nothing new
    clock(200)
    assert prepare(biller)["created"] == 0  # after the final stage there is nothing left to send
    assert len(seen) == 4


def test_minimum_gap_between_reminders_to_the_same_client(
    admin, biller, client_org, clock, mail_ready
):
    overdue(biller, client_org)
    clock(1)
    prepare(biller)
    biller.post(f"/api/billing-notices/{notices(biller)[0]['id']}/send")
    clock(16)  # stage 2 is due, but the client was contacted moments ago (gap = 7 days)
    assert prepare(biller)["created"] == 0
    set_gap(admin, 0)
    assert prepare(biller)["created"] == 1


def test_disabled_stages_are_skipped(biller, client_org, clock):
    first = biller.get("/api/billing/reminder-stages").json()[0]
    biller.patch(f"/api/billing/reminder-stages/{first['id']}", json={"enabled": False})
    overdue(biller, client_org)
    clock(5)
    assert prepare(biller)["created"] == 0  # stage 1 is off and 5 days < stage 2
    clock(16)
    prepare(biller)
    assert notices(biller)[0]["stage_name"] == "Follow-up"


def test_do_not_remind_paid_and_archived_clients_are_left_alone(
    admin, biller, make_org, clock, company
):
    orgs = {}
    for name in ("Flagged", "Paid Up", "Gone"):
        oid = make_org(name)["id"]
        orgs[name] = oid
        admin.post(
            f"/api/organizations/{oid}/contacts",
            json={"name": "A B", "email": f"{name[0].lower()}@x.com", "is_billing_contact": True},
        )
    overdue(biller, orgs["Flagged"])
    paid = overdue(biller, orgs["Paid Up"])
    overdue(biller, orgs["Gone"])
    pay(biller, orgs["Paid Up"], 10000, [{"invoice_id": paid["id"], "amount_cents": 10000}])
    biller.patch(f"/api/organizations/{orgs['Flagged']}/billing", json={"do_not_remind": True})
    admin.post(f"/api/organizations/{orgs['Gone']}/archive")
    clock(5)
    assert prepare(biller)["created"] == 0
    biller.patch(f"/api/organizations/{orgs['Flagged']}/billing", json={"do_not_remind": False})
    assert prepare(biller)["created"] == 1


def test_one_notice_per_client_lists_all_overdue_invoices(
    admin, biller, client_org, clock, mail_ready
):
    set_gap(admin, 0)
    a = overdue(biller, client_org, 1000)
    clock(1)
    prepare(biller)
    biller.post(f"/api/billing-notices/{notices(biller)[0]['id']}/send")  # A: stage 1 sent
    clock(3)
    b = final_invoice(
        biller, client_org, 2000, invoice_date=biz_today() - timedelta(days=1), terms=0
    )
    assert prepare(biller)["created"] == 1  # B is newly overdue; A is listed for context
    [n] = notices(biller, status="pending")
    by = {r["number"]: r for r in n["invoices"]}
    assert set(by) == {a["number"], b["number"]}
    assert by[b["number"]]["new_stage"] is True and by[a["number"]]["new_stage"] is False
    assert n["total_due_cents"] == 3000 and "$30.00" in n["body_text"]


# ---- recipients ----
def add_contact(admin, org, name, email, **flags):
    r = admin.post(
        f"/api/organizations/{org}/contacts", json={"name": name, "email": email, **flags}
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_recipients_billing_contacts_then_primary_and_never_a_guess(
    admin, biller, make_org, clock, company, mail_ready
):
    clock(3)
    none = make_org("NoContacts")["id"]
    add_contact(admin, none, "Someone", "someone@x.com")  # neither billing nor primary
    primary = make_org("PrimaryOnly")["id"]
    add_contact(admin, primary, "Prim Ary", "prim@x.com", is_primary=True)
    add_contact(admin, primary, "Other", "other@x.com")
    multi = make_org("MultiBilling")["id"]
    add_contact(admin, multi, "Bee One", "b1@x.com", is_billing_contact=True)
    add_contact(admin, multi, "Bee Two", "b2@x.com", is_billing_contact=True)
    archived = make_org("ArchivedBilling")["id"]
    gone = add_contact(admin, archived, "Gone", "gone@x.com", is_billing_contact=True)
    admin.post(f"/api/contacts/{gone['id']}/archive")
    add_contact(admin, archived, "Backup", "backup@x.com", is_primary=True)
    for oid in (none, primary, multi, archived):
        overdue(biller, oid)
    clock(3)
    assert prepare(biller)["created"] == 4
    by = {n["organization_name"]: n for n in notices(biller)}
    assert (
        by["NoContacts"]["to_emails"] == []
        and "No billing or primary" in by["NoContacts"]["blocked_reason"]
    )
    assert by["PrimaryOnly"]["to_emails"] == ["prim@x.com"] and by["PrimaryOnly"][
        "body_text"
    ].startswith("Hello Prim,")
    assert sorted(by["MultiBilling"]["to_emails"]) == ["b1@x.com", "b2@x.com"]
    assert by["MultiBilling"]["body_text"].startswith("Hello MultiBilling team,")
    assert by["ArchivedBilling"]["to_emails"] == ["backup@x.com"]
    blocked = by["NoContacts"]
    r = biller.post(f"/api/billing-notices/{blocked['id']}/send")
    assert r.status_code == 409 and "No billing or primary" in r.json()["detail"]


# ---- manual reminders ----
def test_manual_reminder_for_a_client(admin, biller, client_org, clock):
    a = overdue(biller, client_org, 1000)
    clock(4)
    r = biller.post(f"/api/organizations/{client_org}/reminders", json={})
    assert r.status_code == 201, r.text
    n = r.json()
    assert (
        n["manual"] is True
        and n["status"] == "pending"
        and n["invoices"][0]["number"] == a["number"]
    )
    assert all(row["new_stage"] is False for row in n["invoices"])  # manual never uses up a stage
    assert biller.post(f"/api/organizations/{client_org}/reminders", json={}).status_code == 409
    biller.post(f"/api/billing-notices/{n['id']}/dismiss", json={"reason": "changed my mind"})
    assert prepare(biller)["created"] == 1  # the automatic stage is still available


def test_manual_reminder_rules(biller, make_org, client_org, clock):
    assert biller.post(f"/api/organizations/{client_org}/reminders", json={}).status_code == 409
    inv = overdue(biller, client_org)
    not_due = biller.post(
        f"/api/organizations/{client_org}/reminders", json={"invoice_ids": [inv["id"]]}
    )
    assert not_due.status_code == 201  # explicitly chosen invoices may be reminded early
    other = make_org("Other")["id"]
    theirs = final_invoice(biller, other, 100)
    assert (
        biller.post(
            f"/api/organizations/{client_org}/reminders", json={"invoice_ids": [theirs["id"]]}
        ).status_code
        == 409
    )
    assert biller.post("/api/organizations/999/reminders", json={}).status_code == 404


# ---- reviewing and approving ----
def worker_sends(mail=None):
    mail = mail or FakeMail()
    ingest.send_pending(mail, MAILBOX)
    return mail


def test_approving_queues_an_email_with_the_invoice_pdf_and_the_worker_delivers_it(
    admin, biller, client_org, clock, mail_ready
):
    inv = overdue(biller, client_org, 12345)
    clock(2)
    prepare(biller)
    n = notices(biller)[0]
    sent = biller.post(f"/api/billing-notices/{n['id']}/send")
    assert sent.status_code == 200
    body = sent.json()
    assert (body["status"], body["email_status"], body["decided_at"] is not None) == (
        "sent",
        "pending",
        True,
    )
    mail = worker_sends()
    [msg] = mail.sent
    assert msg["to"] == ["pat@acme.com"] and msg["subject"] == n["subject"]
    assert inv["number"] in msg["body"]
    [(name, ctype, data)] = msg["attachments"]
    assert (name, ctype) == (f"{inv['number']}.pdf", "application/pdf") and data.startswith(b"%PDF")
    assert inv["number"].encode() in data
    assert notices(biller, status="sent")[0]["email_status"] == "sent"
    ev = admin.get("/api/audit", params={"action": "notice.send"}).json()["items"][0]
    assert ev["detail"]["to"] == ["pat@acme.com"] and ev["actor_id"] == biller.user["id"]
    assert biller.post(f"/api/billing-notices/{n['id']}/send").status_code == 409  # only once


def test_sending_is_refused_when_email_is_not_configured(biller, client_org, clock):
    overdue(biller, client_org)
    clock(2)
    prepare(biller)
    r = biller.post(f"/api/billing-notices/{notices(biller)[0]['id']}/send")
    assert r.status_code == 409 and "not configured" in r.json()["detail"]


def test_staff_can_edit_the_message_before_sending(biller, client_org, clock, mail_ready):
    overdue(biller, client_org)
    clock(2)
    prepare(biller)
    n = notices(biller)[0]
    edited = biller.patch(
        f"/api/billing-notices/{n['id']}",
        json={"subject": "Quick note about your invoice", "body_text": "Hi Pat, personal note.\n"},
    )
    assert edited.status_code == 200 and edited.json()["subject"] == "Quick note about your invoice"
    assert (
        biller.patch(f"/api/billing-notices/{n['id']}", json={"subject": "  "}).status_code == 409
    )
    assert (
        biller.patch(f"/api/billing-notices/{n['id']}", json={"body_text": ""}).status_code == 409
    )
    biller.post(f"/api/billing-notices/{n['id']}/send")
    [msg] = worker_sends().sent
    assert (
        msg["subject"] == "Quick note about your invoice"
        and msg["body"] == "Hi Pat, personal note.\n"
    )
    assert (
        biller.patch(f"/api/billing-notices/{n['id']}", json={"subject": "late"}).status_code == 409
    )


def test_a_payment_after_preparing_makes_the_notice_stale_until_refreshed(
    admin, biller, client_org, clock, mail_ready
):
    inv = overdue(biller, client_org, 10000)
    clock(2)
    prepare(biller)
    n = notices(biller)[0]
    pay(biller, client_org, 4000, [{"invoice_id": inv["id"], "amount_cents": 4000}])
    assert notices(biller)[0]["stale"] is True
    r = biller.post(f"/api/billing-notices/{n['id']}/send")
    assert r.status_code == 409 and "Refresh" in r.json()["detail"]
    fresh = biller.post(f"/api/billing-notices/{n['id']}/refresh").json()
    assert (
        fresh["stale"] is False
        and fresh["total_due_cents"] == 6000
        and "$60.00" in fresh["body_text"]
    )
    assert biller.post(f"/api/billing-notices/{n['id']}/send").status_code == 200


def test_refresh_expires_a_notice_when_everything_got_paid(biller, client_org, clock, mail_ready):
    inv = overdue(biller, client_org, 5000)
    clock(2)
    prepare(biller)
    n = notices(biller)[0]
    pay(biller, client_org, 5000, [{"invoice_id": inv["id"], "amount_cents": 5000}])
    assert biller.post(f"/api/billing-notices/{n['id']}/refresh").json()["status"] == "expired"
    assert biller.post(f"/api/billing-notices/{n['id']}/send").status_code == 409
    assert biller.post(f"/api/billing-notices/{n['id']}/refresh").status_code == 409
    assert (
        biller.post(
            f"/api/billing-notices/{n['id']}/dismiss", json={"reason": "already done"}
        ).status_code
        == 409
    )


def test_dismissing_needs_a_reason_and_the_stage_is_never_prepared_again(
    admin, biller, client_org, clock
):
    overdue(biller, client_org)
    clock(2)
    prepare(biller)
    n = notices(biller)[0]
    assert (
        biller.post(f"/api/billing-notices/{n['id']}/dismiss", json={"reason": "no"}).status_code
        == 422
    )
    d = biller.post(
        f"/api/billing-notices/{n['id']}/dismiss", json={"reason": "Negotiating a settlement"}
    )
    assert d.status_code == 200 and d.json()["status"] == "dismissed"
    assert d.json()["dismiss_reason"] == "Negotiating a settlement"
    assert prepare(biller)["created"] == 0
    assert (
        biller.post(
            f"/api/billing-notices/{n['id']}/dismiss", json={"reason": "again again"}
        ).status_code
        == 409
    )
    assert (
        biller.post("/api/billing-notices/999/dismiss", json={"reason": "not there"}).status_code
        == 404
    )
    ev = admin.get("/api/audit", params={"action": "notice.dismiss"}).json()["items"][0]
    assert ev["detail"]["reason"] == "Negotiating a settlement"


def test_bulk_send_reports_each_result_independently(
    admin, biller, make_org, client_org, clock, mail_ready
):
    nocontact = make_org("NoContact")["id"]
    overdue(biller, client_org)
    overdue(biller, nocontact)
    clock(2)
    assert prepare(biller)["created"] == 2
    ids = {n["organization_name"]: n["id"] for n in notices(biller)}
    r = biller.post(
        "/api/billing-notices/send", json={"ids": [ids["Acme Corp"], ids["NoContact"], 999]}
    )
    assert r.status_code == 200
    by = {x["id"]: x for x in r.json()}
    assert by[ids["Acme Corp"]]["ok"] is True
    assert (
        by[ids["NoContact"]]["ok"] is False and "contact" in by[ids["NoContact"]]["error"].lower()
    )
    assert by[999]["ok"] is False
    assert len(worker_sends().sent) == 1
    statuses = {n["organization_name"]: n["status"] for n in notices(biller)}
    assert statuses == {"Acme Corp": "sent", "NoContact": "pending"}
    assert biller.post("/api/billing-notices/send", json={"ids": []}).status_code == 422


def test_too_many_invoices_are_attached_as_a_statement_instead(
    admin, biller, client_org, clock, mail_ready
):
    for _ in range(nsvc.MAX_INVOICE_ATTACHMENTS + 1):
        overdue(biller, client_org, 100)
    clock(2)
    prepare(biller)
    n = notices(biller)[0]
    assert len(n["invoices"]) == 11
    biller.post(f"/api/billing-notices/{n['id']}/send")
    [msg] = worker_sends().sent
    assert [a[0] for a in msg["attachments"]] == [
        f"Statement-{biz_today() + timedelta(days=2)}.pdf"
    ]


def test_notice_lookup_and_listing_filters(biller, client_org, clock):
    overdue(biller, client_org)
    clock(2)
    prepare(biller)
    n = notices(biller)[0]
    assert biller.get(f"/api/billing-notices/{n['id']}").json()["id"] == n["id"]
    assert biller.get("/api/billing-notices/999").status_code == 404
    assert len(notices(biller, kind="reminder")) == 1 and notices(biller, kind="statement") == []
    assert len(notices(biller, organization_id=client_org)) == 1
    assert notices(biller, status="sent") == []
    assert biller.get("/api/billing-notices", params={"status": "bogus"}).status_code == 422
