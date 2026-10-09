from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app import notices as nsvc
from app import worker
from app.db import new_session, set_org_scope
from tests.conftest import biz_today
from tests.mailfakes import MAILBOX
from tests.test_notices import notices, overdue, worker_sends  # noqa: F401
from tests.test_payments import final_invoice, pay


def statement(biller, org):
    r = biller.post(f"/api/organizations/{org}/statements")
    assert r.status_code == 201, r.text
    return r.json()


# ---- content ----
def test_statement_snapshot_lists_open_items_aging_credit_and_recent_payments(biller, client_org):
    today = biz_today()
    late = final_invoice(
        biller, client_org, 10000, invoice_date=today - timedelta(days=45), terms=30
    )
    current = final_invoice(biller, client_org, 2500, invoice_date=today, terms=30)
    paid = final_invoice(biller, client_org, 900, invoice_date=today, terms=30)
    pay(
        biller,
        client_org,
        4000,
        [{"invoice_id": late["id"], "amount_cents": 4000}],
        reference="1001",
    )
    pay(biller, client_org, 900, [{"invoice_id": paid["id"], "amount_cents": 900}])
    pay(biller, client_org, 700)  # unapplied credit
    s = statement(biller, client_org)
    assert (s["total_due_cents"], s["overdue_cents"], s["credit_cents"], s["invoice_count"]) == (
        8500,
        6000,
        700,
        2,
    )
    snap = s["snapshot"]
    assert snap["as_of"] == today.isoformat() and snap["client_name"] == "Acme Corp"
    by = {i["number"]: i for i in snap["invoices"]}
    assert set(by) == {late["number"], current["number"]}  # the paid invoice is not listed
    assert (
        by[late["number"]]["balance_cents"],
        by[late["number"]]["settled_cents"],
        by[late["number"]]["days_past_due"],
    ) == (6000, 4000, 15)
    assert snap["aging"] == {
        "current": 2500,
        "d1_30": 6000,
        "d31_60": 0,
        "d61_90": 0,
        "d90_plus": 0,
    }
    assert sorted(p["amount_cents"] for p in snap["payments"]) == [700, 900, 4000]
    assert (
        snap["payments_since"] == (today - timedelta(days=nsvc.STATEMENT_LOOKBACK_DAYS)).isoformat()
    )


def test_next_statement_lists_payments_since_the_previous_one(biller, client_org, monkeypatch):
    final_invoice(biller, client_org, 5000)
    pay(biller, client_org, 100)
    statement(biller, client_org)
    day2 = biz_today() + timedelta(days=10)
    monkeypatch.setattr(nsvc, "today", lambda ctx: day2)
    later = biller.post(f"/api/organizations/{client_org}/statements").json()["snapshot"]
    assert later["payments_since"] == biz_today().isoformat() and later["as_of"] == day2.isoformat()


def test_a_statement_is_a_frozen_snapshot(biller, client_org):
    inv = final_invoice(biller, client_org, 5000)
    s = statement(biller, client_org)
    pay(biller, client_org, 5000, [{"invoice_id": inv["id"], "amount_cents": 5000}])
    again = biller.get(f"/api/statements/{s['id']}").json()
    assert again["snapshot"] == s["snapshot"] and again["total_due_cents"] == 5000
    assert statement(biller, client_org)["total_due_cents"] == 0  # a new one sees the payment
    ids = [x["id"] for x in biller.get(f"/api/organizations/{client_org}/statements").json()]
    assert ids == sorted(ids, reverse=True) and s["id"] in ids


def test_statement_pdf(biller, client_org, company):
    inv = final_invoice(biller, client_org, 123456)
    pay(biller, client_org, 1000, reference="CHK-77")
    s = statement(biller, client_org)
    r = biller.get(f"/api/statements/{s['id']}/pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"] == f'attachment; filename="Statement-{s["as_of"]}.pdf"'
    for needle in (
        b"STATEMENT",
        b"Acme MSP LLC",
        b"Acme Corp",
        inv["number"].encode(),
        b"$1,234.56",
        b"CHK-77",
        b"$10.00",
    ):
        assert needle in r.content, needle
    assert biller.get("/api/statements/999/pdf").status_code == 404
    assert biller.get("/api/statements/999").status_code == 404
    assert biller.post("/api/organizations/999/statements").status_code == 404
    assert biller.get("/api/organizations/999/statements").json() == []


def test_statement_pdf_escapes_markup(admin, biller, make_org, company):
    org = make_org("<b>Evil & Co</b>")["id"]
    final_invoice(biller, org, 100)
    s = statement(biller, org)
    pdf = biller.get(f"/api/statements/{s['id']}/pdf").content
    assert b"(<) Tj (b) Tj (>) Tj" in pdf  # shown literally, never interpreted as markup


# ---- emailing a statement ----
def test_email_statement_prepare_then_send(admin, biller, client_org, mail_ready):
    final_invoice(biller, client_org, 5000)
    s = statement(biller, client_org)
    r = biller.post(f"/api/statements/{s['id']}/email", json={"send": False})
    assert r.status_code == 201
    n = r.json()
    assert (n["kind"], n["status"], n["manual"], n["statement_id"]) == (
        "statement",
        "pending",
        True,
        s["id"],
    )
    assert n["subject"] == f"Account statement from Acme MSP LLC as of {s['as_of']}"
    assert n["total_due_cents"] == 5000 and "Balance due: $50.00" in n["body_text"]
    assert biller.post(f"/api/billing-notices/{n['id']}/send").status_code == 200
    [msg] = worker_sends().sent
    assert msg["to"] == ["pat@acme.com"]
    [(name, _, data)] = msg["attachments"]
    assert name == f"Statement-{s['as_of']}.pdf" and data.startswith(b"%PDF")


def test_email_statement_with_send_true_queues_immediately(biller, client_org, mail_ready):
    final_invoice(biller, client_org, 5000)
    s = statement(biller, client_org)
    n = biller.post(f"/api/statements/{s['id']}/email", json={"send": True}).json()
    assert n["status"] == "sent" and n["email_status"] == "pending"
    assert len(worker_sends().sent) == 1
    assert biller.post("/api/statements/999/email", json={"send": False}).status_code == 404


def test_email_statement_send_is_refused_without_mail_config_or_a_recipient(
    admin, biller, make_org, client_org
):
    final_invoice(biller, client_org, 5000)
    s = statement(biller, client_org)
    r = biller.post(f"/api/statements/{s['id']}/email", json={"send": True})
    assert r.status_code == 409 and "not configured" in r.json()["detail"]
    bare = make_org("Bare")["id"]
    final_invoice(biller, bare, 100)
    n = biller.post(
        f"/api/statements/{statement(biller, bare)['id']}/email", json={"send": False}
    ).json()
    assert n["blocked_reason"] and n["to_emails"] == []


def test_a_stale_statement_notice_must_be_refreshed(biller, client_org, mail_ready):
    inv = final_invoice(biller, client_org, 5000)
    s = statement(biller, client_org)
    n = biller.post(f"/api/statements/{s['id']}/email", json={"send": False}).json()
    pay(biller, client_org, 5000, [{"invoice_id": inv["id"], "amount_cents": 5000}])
    assert biller.get(f"/api/billing-notices/{n['id']}").json()["stale"] is True
    assert biller.post(f"/api/billing-notices/{n['id']}/send").status_code == 409
    fresh = biller.post(f"/api/billing-notices/{n['id']}/refresh").json()
    assert (
        fresh["stale"] is False
        and fresh["total_due_cents"] == 0
        and fresh["statement_id"] != s["id"]
    )
    assert biller.post(f"/api/billing-notices/{n['id']}/send").status_code == 200


# ---- monthly batch ----
def test_monthly_batch_prepares_one_statement_per_client_with_a_balance(
    admin, biller, make_org, client_org
):
    owed = final_invoice(biller, client_org, 5000)
    other = make_org("Other Co")["id"]
    settled = final_invoice(biller, other, 100)
    pay(biller, other, 100, [{"invoice_id": settled["id"], "amount_cents": 100}])
    make_org("Credit Only")
    gone = make_org("Gone Co")["id"]
    final_invoice(biller, gone, 900)
    admin.post(f"/api/organizations/{gone}/archive")
    r = biller.post("/api/billing-notices/prepare-statements")
    assert r.status_code == 200 and r.json()["created"] == 1
    [n] = notices(biller, kind="statement")
    assert (
        n["organization_name"] == "Acme Corp" and n["manual"] is False and n["status"] == "pending"
    )
    assert n["total_due_cents"] == owed["total_cents"]
    assert (
        biller.post("/api/billing-notices/prepare-statements").json()["created"] == 0
    )  # idempotent
    biller.post(f"/api/billing-notices/{n['id']}/dismiss", json={"reason": "sending manually"})
    assert (
        biller.post("/api/billing-notices/prepare-statements").json()["created"] == 0
    )  # not again


def test_next_month_gets_a_new_batch(biller, client_org, monkeypatch):
    final_invoice(biller, client_org, 5000)
    assert biller.post("/api/billing-notices/prepare-statements").json()["created"] == 1
    later = biz_today().replace(day=1) + timedelta(days=35)
    monkeypatch.setattr(nsvc, "today", lambda ctx: later)
    assert biller.post("/api/billing-notices/prepare-statements").json()["created"] == 1


# ---- scheduled preparation (what the worker runs) ----
def test_scheduled_preparation_runs_once_a_day_and_once_a_month(admin, biller, client_org, clock):
    overdue(biller, client_org)
    clock(3)
    worker.billing_jobs()
    kinds = sorted(n["kind"] for n in notices(biller))
    assert kinds == ["reminder", "statement"]
    worker.billing_jobs()
    assert len(notices(biller)) == 2  # nothing new the same day
    s = admin.get("/api/settings").json()
    assert s["auto_prepare_reminders"] and s["auto_prepare_statements"]


def test_automatic_preparation_can_be_switched_off(admin, biller, client_org, clock):
    admin.patch(
        "/api/settings", json={"auto_prepare_reminders": False, "auto_prepare_statements": False}
    )
    overdue(biller, client_org)
    clock(3)
    worker.billing_jobs()
    assert notices(biller) == []
    assert (
        biller.post("/api/billing-notices/prepare-reminders").json()["created"] == 1
    )  # manual still works


def test_scheduled_preparation_never_sends_anything(biller, client_org, clock, mail_ready):
    overdue(biller, client_org)
    clock(3)
    worker.billing_jobs()
    assert all(n["status"] == "pending" for n in notices(biller))
    assert worker_sends().sent == []


def test_settings_validate_statement_templates_and_gap(admin):
    assert (
        admin.patch("/api/settings", json={"statement_subject": "Hello {nope}"}).status_code == 409
    )
    assert (
        admin.patch(
            "/api/settings", json={"statement_body": "{client} owes {total_due}"}
        ).status_code
        == 200
    )
    assert admin.patch("/api/settings", json={"reminder_min_gap_days": 91}).status_code == 422
    assert admin.get("/api/settings").json()["statement_body"] == "{client} owes {total_due}"


# ---- database guards: what we told a client is a record ----
def run_sql(sql: str, **params):
    with new_session() as db:
        set_org_scope(db, "all")
        try:
            db.execute(text(sql), params)
            db.commit()
        finally:
            db.rollback()


def refuses(sql: str, message: str, **params):
    with pytest.raises(DBAPIError, match=message):
        run_sql(sql, **params)


def test_statements_are_frozen_in_the_database(biller, client_org):
    final_invoice(biller, client_org, 100)
    s = statement(biller, client_org)
    refuses(
        "UPDATE statements SET as_of = as_of + 1 WHERE id = :i",
        "permission denied|frozen",
        i=s["id"],
    )
    with pytest.raises(DBAPIError):
        run_sql("DELETE FROM statements WHERE id = :i", i=s["id"])


def test_sent_and_dismissed_notices_cannot_be_changed_or_deleted(
    biller, client_org, clock, mail_ready
):
    for _ in range(2):
        overdue(biller, client_org)
    clock(2)
    biller.post("/api/billing-notices/prepare-reminders")
    n = notices(biller)[0]
    biller.post(f"/api/billing-notices/{n['id']}/send")
    refuses(
        "UPDATE billing_notices SET body_text = 'rewritten' WHERE id = :i",
        "cannot be changed",
        i=n["id"],
    )
    refuses(
        "UPDATE billing_notice_invoices SET balance_cents = 1 WHERE notice_id = :i",
        "cannot be changed",
        i=n["id"],
    )
    refuses(
        "DELETE FROM billing_notice_invoices WHERE notice_id = :i", "cannot be changed", i=n["id"]
    )
    with pytest.raises(DBAPIError):
        run_sql("DELETE FROM billing_notices WHERE id = :i", i=n["id"])


def test_outbound_attachments_are_immutable(biller, client_org, clock, mail_ready):
    overdue(biller, client_org)
    clock(2)
    biller.post("/api/billing-notices/prepare-reminders")
    biller.post(f"/api/billing-notices/{notices(biller)[0]['id']}/send")
    refuses("UPDATE outbound_attachments SET data = 'x'::bytea", "permission denied|immutable")
    with pytest.raises(DBAPIError):
        run_sql("DELETE FROM outbound_attachments")


def test_database_refuses_a_second_issue_of_the_same_stage(owner, biller, client_org, clock):
    overdue(biller, client_org)
    clock(2)
    biller.post("/api/billing-notices/prepare-reminders")
    row = owner.execute(
        text(
            "SELECT notice_id, invoice_id, organization_id, stage_id "
            "FROM billing_notice_invoices WHERE stage_id IS NOT NULL"
        )
    ).one()
    with pytest.raises(Exception, match="uq_notice_invoice_stage"):
        owner.execute(
            text(
                "INSERT INTO billing_notice_invoices (notice_id, invoice_id, "
                "organization_id, stage_id, balance_cents, days_past_due) "
                "VALUES (:n, :i, :o, :s, 1, 1)"
            ),
            {"n": row.notice_id, "i": row.invoice_id, "o": row.organization_id, "s": row.stage_id},
        )


def test_a_sent_notice_must_point_at_its_email(owner, biller, client_org, clock):
    overdue(biller, client_org)
    clock(2)
    biller.post("/api/billing-notices/prepare-reminders")
    with pytest.raises(Exception, match="ck_notices_sent_has_email"):
        owner.execute(text("UPDATE billing_notices SET status = 'sent'"))


def test_client_data_is_isolated_by_row_level_security(biller, client_org, clock):
    overdue(biller, client_org)
    clock(2)
    biller.post("/api/billing-notices/prepare-reminders")
    statement(biller, client_org)
    for table in ("billing_notices", "billing_notice_invoices", "statements"):
        with new_session() as db:
            assert db.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0  # no scope
            set_org_scope(db, str(client_org + 1000))
            assert db.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
            set_org_scope(db, str(client_org))
            assert db.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() >= 1


def test_mailbox_constant_is_what_the_fakes_use():
    assert MAILBOX == "support@msp.com"
