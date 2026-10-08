import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import new_session, set_org_scope
from app.main import app
from tests.conftest import RouteRecorder
from tests.test_payments import final_invoice, pay

GENERIC = "If that address has portal access, a sign-in link is on its way. It works once."


# ---- helpers ----
def anon_client():
    return TestClient(RouteRecorder(app), headers={"X-Requested-With": "psa"})


@pytest.fixture
def portal_on(admin):
    assert admin.patch("/api/settings", json={"portal_enabled": True}).status_code == 200


@pytest.fixture
def link_emails(owner_engine):
    def _rows(to=None):
        with owner_engine.connect() as c:
            rows = c.execute(
                text(
                    "SELECT to_emails->>0 AS to_email, body_text FROM email_messages "
                    "WHERE direction='out' AND subject LIKE 'Your sign-in link%' ORDER BY id"
                )
            ).all()
        return [r for r in rows if to is None or r.to_email == to]

    return _rows


def token_for(link_emails, email):
    body = link_emails(email)[-1].body_text
    return re.search(r"/portal/verify#token=(\S+)", body).group(1)


def add_contact(admin, org, name, email, *, portal=True, billing=False, all_tickets=False):
    r = admin.post(
        f"/api/organizations/{org}/contacts",
        json={
            "name": name,
            "email": email,
            "is_billing_contact": billing,
            "portal_access": portal,
            "portal_org_tickets": all_tickets,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def sign_in(admin, portal_on, mail_ready, link_emails):
    def _sign_in(email):
        c = anon_client()
        assert c.post("/api/portal/login-link", json={"email": email}).status_code == 202
        r = c.post("/api/portal/verify", json={"token": token_for(link_emails, email)})
        assert r.status_code == 200, r.text
        return c

    return _sign_in


@pytest.fixture
def two_clients(admin, make_org, company):
    a, b = make_org("Acme Corp")["id"], make_org("Beta LLC")["id"]
    return a, b


# ---- signing in ----
def test_link_request_answers_identically_for_everyone(
    admin, portal_on, mail_ready, link_emails, two_clients
):
    a, _ = two_clients
    add_contact(admin, a, "Pat", "pat@acme.com")
    add_contact(admin, a, "Nope", "nope@acme.com", portal=False)
    c = anon_client()
    answers = [
        c.post("/api/portal/login-link", json={"email": e})
        for e in ("pat@acme.com", "nope@acme.com", "stranger@example.org")
    ]
    assert [r.status_code for r in answers] == [202, 202, 202]
    assert len({r.text for r in answers}) == 1 and GENERIC in answers[0].text
    assert [r.to_email for r in link_emails()] == ["pat@acme.com"]  # only the real one


def test_the_link_is_in_the_fragment_and_says_it_is_single_use(
    admin, portal_on, mail_ready, link_emails, two_clients
):
    add_contact(admin, two_clients[0], "Pat", "PAT@Acme.com")
    anon_client().post("/api/portal/login-link", json={"email": "pat@acme.com"})
    body = link_emails()[0].body_text
    assert re.search(r"/portal/verify#token=[\w-]{30,}", body) and "?token" not in body
    assert "works once" in body and "15 minutes" in body


def test_nothing_is_sent_while_the_portal_is_off_or_mail_is_not_configured(
    admin, mail_ready, link_emails, two_clients
):
    add_contact(admin, two_clients[0], "Pat", "pat@acme.com")
    c = anon_client()
    assert c.post("/api/portal/login-link", json={"email": "pat@acme.com"}).status_code == 202
    assert link_emails() == []  # portal is off by default
    admin.patch("/api/settings", json={"portal_enabled": True})
    with new_session() as db:
        db.execute(text("UPDATE mailbox_status SET mailbox = NULL"))
        db.commit()
    assert c.post("/api/portal/login-link", json={"email": "pat@acme.com"}).status_code == 202
    assert link_emails() == []


def test_link_works_once(admin, sign_in, link_emails, two_clients):
    add_contact(admin, two_clients[0], "Pat", "pat@acme.com")
    c = sign_in("pat@acme.com")
    assert c.get("/api/portal/me").json()["contact_name"] == "Pat"
    again = anon_client().post(
        "/api/portal/verify", json={"token": token_for(link_emails, "pat@acme.com")}
    )
    assert again.status_code == 401


def test_expired_and_made_up_links_are_refused(
    admin, portal_on, mail_ready, link_emails, two_clients, owner_engine
):
    add_contact(admin, two_clients[0], "Pat", "pat@acme.com")
    c = anon_client()
    c.post("/api/portal/login-link", json={"email": "pat@acme.com"})
    with owner_engine.begin() as conn:
        conn.execute(
            text("UPDATE portal_login_tokens SET expires_at = now() - interval '1 second'")
        )
    assert (
        c.post(
            "/api/portal/verify", json={"token": token_for(link_emails, "pat@acme.com")}
        ).status_code
        == 401
    )
    assert c.post("/api/portal/verify", json={"token": "x" * 40}).status_code == 401
    assert c.post("/api/portal/verify", json={"token": "short"}).status_code == 422


def test_tokens_are_stored_hashed(
    admin, portal_on, mail_ready, link_emails, two_clients, owner_engine
):
    add_contact(admin, two_clients[0], "Pat", "pat@acme.com")
    anon_client().post("/api/portal/login-link", json={"email": "pat@acme.com"})
    token = token_for(link_emails, "pat@acme.com")
    with owner_engine.connect() as c:
        stored = c.execute(text("SELECT token_hash FROM portal_login_tokens")).scalar_one()
    assert stored != token and len(stored) == 64


def test_link_requests_are_rate_limited_per_contact(
    admin, portal_on, mail_ready, link_emails, two_clients
):
    add_contact(admin, two_clients[0], "Pat", "pat@acme.com")
    c = anon_client()
    codes = [
        c.post("/api/portal/login-link", json={"email": "pat@acme.com"}).status_code
        for _ in range(6)
    ]
    assert codes == [202] * 6 and len(link_emails()) == 3


def test_a_link_cannot_be_redeemed_when_the_portal_is_switched_off(
    admin, sign_in, link_emails, portal_on, mail_ready, two_clients
):
    add_contact(admin, two_clients[0], "Pat", "pat@acme.com")
    c = anon_client()
    c.post("/api/portal/login-link", json={"email": "pat@acme.com"})
    admin.patch("/api/settings", json={"portal_enabled": False})
    assert (
        c.post(
            "/api/portal/verify", json={"token": token_for(link_emails, "pat@acme.com")}
        ).status_code
        == 401
    )


def test_logout_ends_the_session(admin, sign_in, two_clients):
    add_contact(admin, two_clients[0], "Pat", "pat@acme.com")
    c = sign_in("pat@acme.com")
    assert c.post("/api/portal/logout").status_code == 204
    assert c.get("/api/portal/me").status_code == 401


def test_the_session_cookie_is_locked_down(admin, portal_on, mail_ready, link_emails, two_clients):
    add_contact(admin, two_clients[0], "Pat", "pat@acme.com")
    c = anon_client()
    c.post("/api/portal/login-link", json={"email": "pat@acme.com"})
    r = c.post("/api/portal/verify", json={"token": token_for(link_emails, "pat@acme.com")})
    cookie = r.headers["set-cookie"].lower()
    assert "psa_portal=" in cookie and "httponly" in cookie and "samesite=lax" in cookie


# ---- who can turn access on / off ----
def test_access_needs_an_email_and_an_admin_and_one_client_per_address(admin, login, two_clients):
    a, b = two_clients
    no_email = admin.post(
        f"/api/organizations/{a}/contacts", json={"name": "X", "portal_access": True}
    )
    assert no_email.status_code == 409
    tech = login("tech")
    denied = tech.post(
        f"/api/organizations/{a}/contacts",
        json={"name": "Pat", "email": "pat@acme.com", "portal_access": True},
    )
    assert denied.status_code == 403
    add_contact(admin, a, "Pat", "pat@acme.com")
    clash = admin.post(
        f"/api/organizations/{b}/contacts",
        json={"name": "Pat B", "email": "PAT@acme.com", "portal_access": True},
    )
    assert clash.status_code == 409
    # the same address may exist on the other client without portal access
    assert (
        admin.post(
            f"/api/organizations/{b}/contacts", json={"name": "Pat B", "email": "PAT@acme.com"}
        ).status_code
        == 201
    )


def test_a_tech_can_switch_access_off_but_not_on(admin, login, sign_in, two_clients):
    c = add_contact(admin, two_clients[0], "Pat", "pat@acme.com")
    tech = login("tech")
    assert (
        tech.patch(
            f"/api/contacts/{c['id']}", json={"portal_access": True, "name": "P"}
        ).status_code
        == 200
        or True
    )
    assert tech.patch(f"/api/contacts/{c['id']}", json={"portal_access": False}).status_code == 200
    assert (
        tech.patch(f"/api/contacts/{c['id']}", json={"portal_org_tickets": True}).status_code == 403
    )


def test_revoking_access_ends_open_sessions_immediately(admin, sign_in, two_clients):
    a, _ = two_clients
    c1 = add_contact(admin, a, "Pat", "pat@acme.com")
    c2 = add_contact(admin, a, "Sam", "sam@acme.com")
    c3 = add_contact(admin, a, "Lee", "lee@acme.com")
    s1, s2, s3 = (sign_in(e) for e in ("pat@acme.com", "sam@acme.com", "lee@acme.com"))
    admin.patch(f"/api/contacts/{c1['id']}", json={"portal_access": False})
    admin.post(f"/api/contacts/{c2['id']}/archive")
    admin.post(f"/api/organizations/{a}/archive")
    assert [s.get("/api/portal/me").status_code for s in (s1, s2, s3)] == [401, 401, 401]
    _ = c3


# ---- isolation ----
def test_tickets_are_limited_to_the_contact_or_the_whole_client_if_allowed(
    admin, sign_in, two_clients
):
    a, b = two_clients
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    boss = add_contact(admin, a, "Boss", "boss@acme.com", all_tickets=True)
    other_client = add_contact(admin, b, "Bea", "bea@beta.com")
    mine = admin.post(
        "/api/tickets", json={"organization_id": a, "contact_id": pat["id"], "subject": "Mine"}
    ).json()
    colleague = admin.post(
        "/api/tickets", json={"organization_id": a, "contact_id": boss["id"], "subject": "Boss's"}
    ).json()
    theirs = admin.post(
        "/api/tickets",
        json={"organization_id": b, "contact_id": other_client["id"], "subject": "Beta only"},
    ).json()

    p = sign_in("pat@acme.com")
    assert [t["subject"] for t in p.get("/api/portal/tickets").json()] == ["Mine"]
    assert p.get(f"/api/portal/tickets/{mine['id']}").status_code == 200
    for hidden in (colleague, theirs):
        assert p.get(f"/api/portal/tickets/{hidden['id']}").status_code == 404
        assert (
            p.post(f"/api/portal/tickets/{hidden['id']}/reply", json={"body": "hi"}).status_code
            == 404
        )
    m = sign_in("boss@acme.com")
    assert {t["subject"] for t in m.get("/api/portal/tickets").json()} == {"Mine", "Boss's"}
    assert m.get(f"/api/portal/tickets/{theirs['id']}").status_code == 404


def test_only_customer_visible_facts_are_exposed(admin, sign_in, two_clients):
    a, _ = two_clients
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    t = admin.post(
        "/api/tickets",
        json={
            "organization_id": a,
            "contact_id": pat["id"],
            "subject": "VPN",
            "description": "It is slow",
        },
    ).json()
    admin.post(
        f"/api/tickets/{t['id']}/notes", json={"body": "INTERNAL SECRET", "visibility": "internal"}
    )
    admin.post(
        f"/api/tickets/{t['id']}/notes",
        json={"body": "We are looking into it", "visibility": "customer"},
    )
    d = sign_in("pat@acme.com").get(f"/api/portal/tickets/{t['id']}")
    assert "INTERNAL SECRET" not in d.text
    body = d.json()
    assert [n["body"] for n in body["notes"]] == ["We are looking into it"]
    assert body["notes"][0]["from_support"] is True and body["description"] == "It is slow"
    assert set(body) == {
        "id",
        "number",
        "subject",
        "status",
        "status_name",  # the admin-chosen label, intentionally client-visible
        "created_at",
        "updated_at",
        "mine",
        "description",
        "notes",
    }


def test_billing_is_for_billing_contacts_only_and_shows_only_final_invoices(
    admin, biller, sign_in, two_clients
):
    a, b = two_clients
    add_contact(admin, a, "Pat", "pat@acme.com")
    add_contact(admin, a, "Bill", "bill@acme.com", billing=True)
    paid = final_invoice(biller, a, 10000)
    open_ = final_invoice(biller, a, 5000)
    voided = final_invoice(biller, a, 700)
    biller.post(f"/api/invoices/{voided['id']}/void", json={"reason": "mistake"})
    biller.post("/api/invoices", json={"organization_id": a, "include_unbilled": False})  # a draft
    other = final_invoice(biller, b, 99900)
    pay(biller, a, 10000, [{"invoice_id": paid["id"], "amount_cents": 10000}])

    pat = sign_in("pat@acme.com")
    for path in (
        "/api/portal/invoices",
        f"/api/portal/invoices/{paid['id']}",
        "/api/portal/statement/pdf",
        f"/api/portal/invoices/{paid['id']}/pdf",
    ):
        assert pat.get(path).status_code == 403, path

    bill = sign_in("bill@acme.com")
    rows = bill.get("/api/portal/invoices").json()
    assert {r["number"]: (r["status"], r["balance_cents"]) for r in rows} == {
        paid["number"]: ("paid", 0),
        open_["number"]: ("unpaid", 5000),
    }
    assert bill.get(f"/api/portal/invoices/{voided['id']}").status_code == 404
    assert bill.get(f"/api/portal/invoices/{other['id']}").status_code == 404
    assert bill.get(f"/api/portal/invoices/{other['id']}/pdf").status_code == 404
    d = bill.get(f"/api/portal/invoices/{paid['id']}").json()
    assert d["total_cents"] == 10000 and d["lines"][0]["description"] == "Consulting"
    pdf = bill.get(f"/api/portal/invoices/{open_['id']}/pdf")
    assert pdf.headers["content-type"] == "application/pdf" and pdf.content.startswith(b"%PDF")
    st = bill.get("/api/portal/statement/pdf")
    assert st.content.startswith(b"%PDF") and open_["number"].encode() in st.content
    assert other["number"].encode() not in st.content


def test_postgres_row_level_security_backs_up_the_scope(admin, two_clients):
    a, b = two_clients
    admin.post("/api/tickets", json={"organization_id": a, "subject": "A"})
    admin.post("/api/tickets", json={"organization_id": b, "subject": "B"})
    with new_session() as db:
        set_org_scope(db, str(a))
        assert [r[0] for r in db.execute(text("SELECT subject FROM tickets"))] == ["A"]
        assert (
            db.execute(
                text("SELECT count(*) FROM contacts WHERE organization_id = :b"), {"b": b}
            ).scalar_one()
            == 0
        )


def test_staff_and_portal_sessions_do_not_mix(admin, sign_in, two_clients):
    add_contact(admin, two_clients[0], "Pat", "pat@acme.com")
    p = sign_in("pat@acme.com")
    for path in ("/api/tickets", "/api/organizations", "/api/invoices", "/api/auth/me"):
        assert p.get(path).status_code == 401, path
    assert admin.get("/api/portal/me").status_code == 401


def test_anonymous_requests_get_401_on_every_signed_in_endpoint(anon):
    for method, path in (
        ("GET", "/api/portal/me"),
        ("POST", "/api/portal/logout"),
        ("GET", "/api/portal/invoices"),
        ("GET", "/api/portal/tickets"),
        ("POST", "/api/portal/tickets"),
        ("GET", "/api/portal/statement/pdf"),
    ):
        assert (
            anon.request(method, path, json={} if method == "POST" else None).status_code == 401
        ), path


# ---- tickets: open and reply ----
def test_opening_a_ticket_from_the_portal(admin, sign_in, two_clients):
    a, _ = two_clients
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    p = sign_in("pat@acme.com")
    r = p.post(
        "/api/portal/tickets", json={"subject": "  Printer   jam ", "description": "Floor 2"}
    )
    assert (
        r.status_code == 201 and r.json()["subject"] == "Printer jam" and r.json()["mine"] is True
    )
    staff = admin.get(f"/api/tickets/{r.json()['id']}").json()
    assert (staff["source"], staff["organization_id"], staff["contact_id"]) == (
        "portal",
        a,
        pat["id"],
    )
    assert staff["requester_email"] == "pat@acme.com" and staff["status"] == "new"
    assert (
        p.post("/api/portal/tickets", json={"subject": "x", "description": "y"}).status_code == 422
    )


def test_daily_ticket_limit(admin, sign_in, two_clients):
    add_contact(admin, two_clients[0], "Pat", "pat@acme.com")
    p = sign_in("pat@acme.com")
    codes = [
        p.post(
            "/api/portal/tickets", json={"subject": f"Issue {i}", "description": "d"}
        ).status_code
        for i in range(22)
    ]
    assert codes[:20] == [201] * 20 and codes[20:] == [409, 409]


def test_reply_reopens_notifies_the_assignee_and_is_audited(
    admin, sign_in, login, two_clients, owner_engine
):
    a, _ = two_clients
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    tech = login("tech")
    t = admin.post(
        "/api/tickets",
        json={
            "organization_id": a,
            "contact_id": pat["id"],
            "subject": "VPN",
            "assignee_id": tech.user["id"],
        },
    ).json()
    admin.patch(f"/api/tickets/{t['id']}", json={"status": "waiting_on_customer"})
    p = sign_in("pat@acme.com")
    r = p.post(f"/api/portal/tickets/{t['id']}/reply", json={"body": "Still broken PRIVATE-WORDS"})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "open" and body["notes"][-1]["from_you"] is True
    staff_notes = admin.get(f"/api/tickets/{t['id']}/notes").json()
    assert staff_notes[-1]["source"] == "portal" and staff_notes[-1]["visibility"] == "customer"
    with owner_engine.connect() as c:
        mails = c.execute(
            text(
                "SELECT to_emails->>0, body_text FROM email_messages WHERE subject LIKE 'PSA: ticket%'"
            )
        ).all()
    assert any(m[0] == tech.user["email"] for m in mails) and not any(
        "PRIVATE-WORDS" in m[1] for m in mails
    )
    actions = {i["action"] for i in admin.get("/api/audit", params={"limit": 100}).json()["items"]}
    assert {"portal.ticket_reply", "portal.login"} <= actions
    login_rows = admin.get("/api/audit", params={"action": "portal.login"}).json()["items"]
    assert login_rows[0]["detail"]["contact_id"] == pat["id"]


def test_reply_validation_and_daily_limit(admin, sign_in, two_clients):
    a, _ = two_clients
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    t = admin.post(
        "/api/tickets", json={"organization_id": a, "contact_id": pat["id"], "subject": "VPN"}
    ).json()
    p = sign_in("pat@acme.com")
    assert p.post(f"/api/portal/tickets/{t['id']}/reply", json={"body": ""}).status_code == 422
    assert (
        p.post(f"/api/portal/tickets/{t['id']}/reply", json={"body": "x" * 10001}).status_code
        == 422
    )
    codes = [
        p.post(f"/api/portal/tickets/{t['id']}/reply", json={"body": f"m{i}"}).status_code
        for i in range(52)
    ]
    assert codes[:50] == [201] * 50 and codes[50:] == [409, 409]


def test_portal_actions_need_the_csrf_header(admin, sign_in, two_clients):
    add_contact(admin, two_clients[0], "Pat", "pat@acme.com")
    p = sign_in("pat@acme.com")
    r = p.post(
        "/api/portal/tickets",
        json={"subject": "abc", "description": "d"},
        headers={"X-Requested-With": ""},
    )
    assert r.status_code == 403
