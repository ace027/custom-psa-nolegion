"""Portal appointments: a contact sees only their own client-visible, scheduled appointments."""

from datetime import UTC, datetime, timedelta

import pytest

from tests.test_portal import (  # noqa: F401
    add_contact,
    link_emails,
    portal_on,
    sign_in,
    two_clients,
)


@pytest.fixture
def tech(make_user):
    u = make_user("tech", "tess@example.com")
    return u


def hours(h):
    return (datetime.now(UTC) + timedelta(hours=h)).isoformat()


def ticket_for(admin, org, contact, subject="Printer"):
    r = admin.post(
        "/api/v1/tickets",
        json={"organization_id": org, "contact_id": contact["id"], "subject": subject},
    )
    assert r.status_code == 201, r.text
    return r.json()


def book(admin, ticket, tech, start=2, end=3, **kw):
    r = admin.post(
        "/api/v1/appointments",
        json={
            "ticket_id": ticket["id"],
            "tech_id": tech["id"],
            "starts_at": hours(start),
            "ends_at": hours(end),
            **kw,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_contact_sees_own_ticket_appointments_only(admin, sign_in, two_clients, tech):  # noqa: F811
    a, b = two_clients
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    boss = add_contact(admin, a, "Boss", "boss@acme.com", all_tickets=True)
    bea = add_contact(admin, b, "Bea", "bea@beta.com")
    mine = book(admin, ticket_for(admin, a, pat, "Mine"), tech, notes="SECRET NOTE")
    book(admin, ticket_for(admin, a, boss, "Boss's"), tech, 5, 6)
    book(admin, ticket_for(admin, b, bea, "Beta"), tech, 7, 8)

    rows = sign_in("pat@acme.com").get("/api/v1/portal/appointments")
    assert rows.status_code == 200, rows.text
    assert [r["id"] for r in rows.json()] == [mine["id"]]
    row = rows.json()[0]
    assert row["ticket_subject"] == "Mine" and row["tech_first_name"] == "tech"
    assert "SECRET NOTE" not in rows.text and "notes" not in row
    assert "tess@example.com" not in rows.text and "cancel_reason" not in row

    all_rows = sign_in("boss@acme.com").get("/api/v1/portal/appointments").json()
    assert len(all_rows) == 2
    assert {r["ticket_subject"] for r in all_rows} == {"Mine", "Boss's"}


def test_hidden_cancelled_and_old_appointments(admin, sign_in, two_clients, tech):  # noqa: F811
    a, _ = two_clients
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    t = ticket_for(admin, a, pat)
    shown = book(admin, t, tech, 2, 3)
    book(admin, t, tech, 4, 5, client_visible=False)
    gone = book(admin, t, tech, 6, 7)
    assert (
        admin.post(f"/api/v1/appointments/{gone['id']}/cancel", json={"reason": "x"}).status_code
        == 200
    )
    recent = book(admin, t, tech, -24 * 29 - 2, -24 * 29 - 1)
    book(admin, t, tech, -24 * 31 - 2, -24 * 31 - 1)

    rows = sign_in("pat@acme.com").get("/api/v1/portal/appointments").json()
    assert [r["id"] for r in rows] == [recent["id"], shown["id"]]


def test_portal_access_is_required(admin, anon, two_clients, tech):  # noqa: F811
    assert anon.get("/api/v1/portal/appointments").status_code == 401


def test_portal_disabled_refuses(admin, sign_in, two_clients):  # noqa: F811
    a, _ = two_clients
    add_contact(admin, a, "Pat", "pat@acme.com")
    c = sign_in("pat@acme.com")
    assert admin.patch("/api/v1/settings", json={"portal_enabled": False}).status_code == 200
    assert c.get("/api/v1/portal/me").status_code == 403  # same refusal as the other portal routes
    assert c.get("/api/v1/portal/appointments").status_code == 403
