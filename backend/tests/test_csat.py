"""Parity phase 1D: customer satisfaction (CSAT)."""

import re

import pytest
from sqlalchemy import text

from app.db import new_session, set_org_scope
from tests.test_portal import anon_client


@pytest.fixture
def surveys(owner):
    def _rows():
        return owner.execute(
            text(
                "SELECT to_emails, subject, body_text, auto_generated, ticket_id "
                "FROM email_messages WHERE direction='out' AND subject LIKE '%How did we do?' "
                "ORDER BY id"
            )
        ).fetchall()

    return _rows


def tokens_in(body):
    return re.findall(r"/csat#token=([\w-]+)&rating=(\d)", body)


def resolve(admin, t):
    r = admin.patch(f"/api/tickets/{t['id']}", json={"status": "resolved"})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def csat_on(admin):
    assert admin.patch("/api/settings", json={"csat_enabled": True}).status_code == 200


@pytest.fixture
def ticket(make_ticket, org_ctx):
    return make_ticket(contact_id=org_ctx["contact"], subject="VPN down")


def test_off_by_default_so_nothing_is_sent(admin, ticket, surveys):
    assert admin.get("/api/settings").json()["csat_enabled"] is False
    resolve(admin, ticket)
    assert surveys() == []
    assert admin.get(f"/api/tickets/{ticket['id']}/csat").json() is None


def test_resolving_sends_one_survey_with_five_links(admin, csat_on, ticket, surveys):
    resolve(admin, ticket)
    [m] = surveys()
    assert m.to_emails == ["pat@acme.com"] and m.auto_generated
    assert m.subject.startswith(f"[#{ticket['number']}]")
    links = tokens_in(m.body_text)
    assert [r for _, r in links] == ["5", "4", "3", "2", "1"]
    assert len({t for t, _ in links}) == 1  # same token, different rating
    assert "VPN down" in m.body_text and "Pat Customer" in m.body_text
    # pending in the ticket view, not yet answered
    s = admin.get(f"/api/tickets/{ticket['id']}/csat").json()
    assert s["sent_to"] == "pat@acme.com" and s["rating"] is None
    # reopening and resolving again never asks twice; closing directly never asks
    admin.patch(f"/api/tickets/{ticket['id']}", json={"status": "open"})
    resolve(admin, ticket)
    assert len(surveys()) == 1


def test_not_sent_without_a_known_client_or_recipient_or_when_closed_directly(
    admin, csat_on, make_ticket, surveys, owner
):
    plain = make_ticket()  # org but no contact and no requester address
    resolve(admin, plain)
    assert surveys() == []
    withc = make_ticket()
    admin.patch(f"/api/tickets/{withc['id']}", json={"status": "closed"})
    assert surveys() == []


def test_the_token_is_stored_hashed(admin, csat_on, ticket, surveys, owner):
    resolve(admin, ticket)
    token = tokens_in(surveys()[0].body_text)[0][0]
    stored = owner.execute(text("SELECT token_hash FROM csat_surveys")).scalar_one()
    assert token not in stored and len(stored) == 64


def test_answering_once_with_a_comment_then_the_link_is_dead(admin, csat_on, ticket, surveys):
    resolve(admin, ticket)
    token = tokens_in(surveys()[0].body_text)[0][0]
    c = anon_client()
    r = c.post("/api/csat/respond", json={"token": token, "rating": 4, "comment": " Quick fix "})
    assert r.status_code == 200 and r.json() == {"ticket_number": ticket["number"]}
    s = admin.get(f"/api/tickets/{ticket['id']}/csat").json()
    assert s["rating"] == 4 and s["comment"] == "Quick fix" and s["responded_at"]
    again = c.post("/api/csat/respond", json={"token": token, "rating": 1})
    assert again.status_code == 404
    assert admin.get(f"/api/tickets/{ticket['id']}/csat").json()["rating"] == 4


def test_bad_input_and_made_up_or_expired_tokens(admin, csat_on, ticket, surveys, owner):
    resolve(admin, ticket)
    token = tokens_in(surveys()[0].body_text)[0][0]
    c = anon_client()
    for bad in (0, 6, "x"):
        assert c.post("/api/csat/respond", json={"token": token, "rating": bad}).status_code == 422
    big = {"token": token, "rating": 3, "comment": "x" * 2001}
    assert c.post("/api/csat/respond", json=big).status_code == 422
    assert c.post("/api/csat/respond", json={"token": "n" * 40, "rating": 3}).status_code == 404
    owner.execute(text("UPDATE csat_surveys SET expires_at = now() - interval '1 minute'"))
    assert c.post("/api/csat/respond", json={"token": token, "rating": 3}).status_code == 404
    assert admin.get(f"/api/tickets/{ticket['id']}/csat").json()["rating"] is None


def test_summary_counts_and_average(admin, csat_on, make_ticket, org_ctx, surveys):
    ts = [make_ticket(contact_id=org_ctx["contact"], subject=f"T{i}") for i in range(3)]
    for t in ts:
        resolve(admin, t)
    rows = surveys()
    c = anon_client()
    for row, rating in zip(rows[:2], (5, 3), strict=True):
        token = tokens_in(row.body_text)[0][0]
        assert (
            c.post("/api/csat/respond", json={"token": token, "rating": rating}).status_code == 200
        )
    s = admin.get("/api/csat/summary").json()
    assert s["requested"] == 3 and s["responses"] == 2 and s["average"] == 4.0
    assert s["distribution"] == {"1": 0, "2": 0, "3": 1, "4": 0, "5": 1}
    assert admin.get("/api/csat/summary", params={"days": 0}).status_code == 422


def test_permissions_and_audit(admin, login, csat_on, ticket, surveys, owner):
    resolve(admin, ticket)
    token = tokens_in(surveys()[0].body_text)[0][0]
    anon_client().post("/api/csat/respond", json={"token": token, "rating": 2})
    ro = login("read_only")
    assert ro.get(f"/api/tickets/{ticket['id']}/csat").json()["rating"] == 2
    assert ro.get("/api/csat/summary").status_code == 200
    assert anon_client().get("/api/csat/summary").status_code == 401
    assert admin.get("/api/tickets/99999/csat").status_code == 404
    assert admin.patch("/api/settings", json={"csat_enabled": False}).status_code == 200
    assert login("tech").patch("/api/settings", json={"csat_enabled": True}).status_code == 403
    actions = {
        r[0] for r in owner.execute(text("SELECT action FROM audit_log WHERE action LIKE 'csat.%'"))
    }
    assert "csat.respond" in actions
    detail = owner.execute(
        text("SELECT after FROM audit_log WHERE action='csat.respond'")
    ).scalar_one()
    assert detail == {"rating": 2, "has_comment": False}


def test_survey_rows_are_scoped_and_only_answer_columns_can_change(
    admin, csat_on, ticket, surveys, org_ctx
):
    resolve(admin, ticket)
    with new_session() as db:
        assert db.execute(text("SELECT count(*) FROM csat_surveys")).scalar_one() == 0
        set_org_scope(db, str(org_ctx["org"]))
        assert db.execute(text("SELECT count(*) FROM csat_surveys")).scalar_one() == 1
        with pytest.raises(Exception, match="permission denied"):
            db.execute(text("UPDATE csat_surveys SET sent_to = 'x@y.com'"))
