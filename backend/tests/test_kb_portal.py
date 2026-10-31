"""Portal knowledge base: published, client-facing articles only; everything else is a 404."""

import pytest

from tests.test_portal import (  # noqa: F401
    add_contact,
    anon_client,
    link_emails,
    portal_on,
    sign_in,
    two_clients,
)


def make(admin, title, body="Some helpful text about passwords.", **kw):
    payload = {"title": title, "body": body, "visibility": "client", "status": "published", **kw}
    r = admin.post("/api/v1/kb/articles", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def portal(admin, sign_in, two_clients):
    add_contact(admin, two_clients[0], "Pat", "pat@acme.com")
    return sign_in("pat@acme.com")


def test_contact_sees_only_published_client_articles(admin, portal):
    ok = make(admin, "Reset your password")
    internal = make(admin, "Internal runbook", visibility="internal")
    draft = make(admin, "Draft", status="draft")
    archived = make(admin, "Old", status="archived")
    r = portal.get("/api/v1/portal/kb")
    assert r.status_code == 200
    assert [a["id"] for a in r.json()] == [ok["id"]]
    assert set(r.json()[0]) == {"id", "title", "tags", "updated_at", "snippet"}
    d = portal.get(f"/api/v1/portal/kb/{ok['id']}")
    assert d.status_code == 200 and d.json()["body"] == ok["body"]
    assert set(d.json()) == {"id", "title", "body", "tags", "updated_at"}
    for hidden in (internal, draft, archived):
        assert portal.get(f"/api/v1/portal/kb/{hidden['id']}").status_code == 404
    assert portal.get("/api/v1/portal/kb/99999").status_code == 404


def test_portal_search(admin, portal):
    pw = make(admin, "Reset your password")
    make(admin, "Printer setup", "Install the driver")
    make(admin, "Hidden password notes", visibility="internal")
    assert [a["id"] for a in portal.get("/api/v1/portal/kb", params={"q": "password"}).json()] == [
        pw["id"]
    ]
    assert portal.get("/api/v1/portal/kb", params={"q": "the"}).json() == []
    assert portal.get("/api/v1/portal/kb", params={"q": "x"}).status_code == 422


def test_article_changes_disappear_from_portal(admin, portal):
    a = make(admin, "Reset your password")
    admin.patch(f"/api/v1/kb/articles/{a['id']}", json={"status": "archived"})
    assert portal.get("/api/v1/portal/kb").json() == []
    assert portal.get(f"/api/v1/portal/kb/{a['id']}").status_code == 404


def test_unauthenticated_is_401(admin, portal_on):
    a = make(admin, "Reset your password")
    c = anon_client()
    assert c.get("/api/v1/portal/kb").status_code == 401
    assert c.get(f"/api/v1/portal/kb/{a['id']}").status_code == 401


def test_staff_session_cannot_use_portal_kb(admin, portal_on):
    assert admin.get("/api/v1/portal/kb").status_code == 401
