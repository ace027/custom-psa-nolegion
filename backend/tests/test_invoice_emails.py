from tests.test_notices import notices, worker_sends
from tests.test_payments import final_invoice, pay


def email(biller, inv):
    return biller.post(f"/api/invoices/{inv['id']}/email")


def test_prepare_invoice_email_shows_recipients_and_amount_and_sends_nothing(
    biller, client_org, mail_ready
):
    inv = final_invoice(biller, client_org, 12345)
    r = email(biller, inv)
    assert r.status_code == 201, r.text
    n = r.json()
    assert (n["kind"], n["status"], n["to_emails"], n["stale"]) == (
        "invoice",
        "pending",
        ["pat@acme.com"],
        False,
    )
    assert inv["number"] in n["subject"] and "$123.45" in n["body_text"]
    assert [i["invoice_id"] for i in n["invoices"]] == [inv["id"]]
    assert worker_sends().sent == []  # nothing goes out until approved


def test_approving_delivers_the_invoice_pdf(biller, client_org, mail_ready):
    inv = final_invoice(biller, client_org, 5000)
    n = email(biller, inv).json()
    assert biller.post(f"/api/billing-notices/{n['id']}/send").status_code == 200
    [msg] = worker_sends().sent
    [(name, ctype, data)] = msg["attachments"]
    assert (name, ctype) == (f"{inv['number']}.pdf", "application/pdf")
    assert data.startswith(b"%PDF") and inv["number"].encode() in data


def test_only_finalized_invoices_can_be_emailed(biller, client_org):
    draft = biller.post(
        "/api/invoices", json={"organization_id": client_org, "include_unbilled": False}
    ).json()
    assert email(biller, draft).status_code == 409
    inv = final_invoice(biller, client_org, 100)
    biller.post(f"/api/invoices/{inv['id']}/void", json={"reason": "mistake"})
    assert email(biller, inv).status_code == 409


def test_one_pending_email_per_invoice(biller, client_org):
    inv = final_invoice(biller, client_org, 100)
    assert email(biller, inv).status_code == 201
    assert email(biller, inv).status_code == 409
    other = final_invoice(biller, client_org, 200)
    assert email(biller, other).status_code == 201


def test_it_can_be_prepared_again_after_the_first_was_sent(biller, client_org, mail_ready):
    inv = final_invoice(biller, client_org, 100)
    n = email(biller, inv).json()
    biller.post(f"/api/billing-notices/{n['id']}/send")
    assert email(biller, inv).status_code == 201


def test_blocked_without_a_recipient(admin, biller, make_org, company, mail_ready):
    org = make_org("No Email Inc")["id"]
    n = email(biller, final_invoice(biller, org, 100)).json()
    assert n["blocked_reason"] and n["to_emails"] == []
    assert biller.post(f"/api/billing-notices/{n['id']}/send").status_code == 409


def test_a_payment_does_not_make_an_invoice_email_stale(biller, client_org):
    inv = final_invoice(biller, client_org, 1000)
    n = email(biller, inv).json()
    pay(biller, client_org, 400, [{"invoice_id": inv["id"], "amount_cents": 400}])
    assert biller.get(f"/api/billing-notices/{n['id']}").json()["stale"] is False


def test_voiding_the_invoice_blocks_sending_and_refresh_closes_the_notice(
    biller, client_org, mail_ready
):
    inv = final_invoice(biller, client_org, 100)
    n = email(biller, inv).json()
    biller.post(f"/api/invoices/{inv['id']}/void", json={"reason": "mistake"})
    assert biller.post(f"/api/billing-notices/{n['id']}/send").status_code == 409
    r = biller.post(f"/api/billing-notices/{n['id']}/refresh")
    assert r.status_code == 200 and r.json()["status"] == "expired"


def test_auto_prepare_on_finalize_is_off_by_default_and_never_sends(
    admin, biller, client_org, mail_ready
):
    final_invoice(biller, client_org, 100)
    assert notices(biller, kind="invoice") == []
    assert (
        admin.patch("/api/settings", json={"auto_prepare_invoice_emails": True}).status_code == 200
    )
    inv = final_invoice(biller, client_org, 200)
    [n] = notices(biller, kind="invoice")
    assert n["invoices"][0]["invoice_id"] == inv["id"] and n["status"] == "pending"
    assert worker_sends().sent == []


def test_auto_prepare_covers_every_finalized_invoice(admin, biller, client_org):
    admin.patch("/api/settings", json={"auto_prepare_invoice_emails": True})
    a = final_invoice(biller, client_org, 100)
    b = final_invoice(biller, client_org, 200)
    ids = {n["invoices"][0]["invoice_id"] for n in notices(biller, kind="invoice")}
    assert ids == {a["id"], b["id"]}


def test_invoice_email_template_is_validated_and_used(admin, biller, client_org):
    r = admin.patch("/api/settings", json={"invoice_email_subject": "Bill {nope}"})
    assert r.status_code == 409 and "nope" in r.text
    ok = admin.patch(
        "/api/settings",
        json={"invoice_email_subject": "{client}: {invoice_number} ({invoice_total})"},
    )
    assert ok.status_code == 200
    inv = final_invoice(biller, client_org, 999)
    assert email(biller, inv).json()["subject"] == f"Acme Corp: {inv['number']} ($9.99)"
    # the invoice-only placeholders are not available to statement templates
    bad = admin.patch("/api/settings", json={"statement_subject": "{invoice_number}"})
    assert bad.status_code == 409


def test_invoice_email_writes_audit_rows(admin, biller, client_org, mail_ready):
    n = email(biller, final_invoice(biller, client_org, 100)).json()
    biller.post(f"/api/billing-notices/{n['id']}/send")
    create = admin.get("/api/audit", params={"action": "notice.create"}).json()["items"][0]
    assert create["detail"]["kind"] == "invoice"
    assert admin.get("/api/audit", params={"action": "notice.send"}).json()["total"] == 1
