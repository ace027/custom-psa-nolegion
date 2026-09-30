import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import new_session


def count(admin):
    return admin.get("/api/audit", params={"limit": 1}).json()["total"]


def test_every_mutating_endpoint_writes_an_audit_row(admin, make_org):
    org = make_org("Acme")  # organization.create
    oid = org["id"]
    site = admin.post(f"/api/organizations/{oid}/sites", json={"name": "HQ"}).json()
    contact = admin.post(f"/api/organizations/{oid}/contacts", json={"name": "Pat"}).json()
    user = admin.post(
        "/api/users", json={"email": "t@example.com", "display_name": "T", "role": "tech"}
    ).json()
    mutations = [
        ("PATCH", f"/api/organizations/{oid}", {"notes": "x"}),
        ("POST", f"/api/organizations/{oid}/archive", None),
        ("POST", f"/api/organizations/{oid}/unarchive", None),
        ("POST", f"/api/organizations/{oid}/sites", {"name": "S2"}),
        ("PATCH", f"/api/sites/{site['id']}", {"city": "x"}),
        ("POST", f"/api/sites/{site['id']}/archive", None),
        ("POST", f"/api/sites/{site['id']}/unarchive", None),
        ("POST", f"/api/organizations/{oid}/contacts", {"name": "C2"}),
        ("PATCH", f"/api/contacts/{contact['id']}", {"title": "x"}),
        ("POST", f"/api/contacts/{contact['id']}/archive", None),
        ("POST", f"/api/contacts/{contact['id']}/unarchive", None),
        ("POST", "/api/users", {"email": "u2@example.com", "display_name": "U", "role": "tech"}),
        ("PATCH", f"/api/users/{user['id']}", {"display_name": "T2"}),
        ("POST", "/api/organizations", {"name": "Other"}),
        ("POST", "/api/auth/logout", None),
    ]
    for method, path, body in mutations:
        # re-login after logout so audit can still be read
        before = count(admin)
        r = admin.request(method, path, json=body)
        assert r.status_code < 400, (method, path, r.text)
        if path.endswith("/logout"):
            admin.post("/api/auth/dev-login", json={"email": admin.user["email"]})
        assert count(admin) > before, f"{method} {path} wrote no audit row"


def test_audit_is_append_only_for_the_runtime_role(admin, make_org):
    make_org()
    with new_session() as db:
        for stmt in (
            "UPDATE audit_log SET action = 'x'",
            "DELETE FROM audit_log",
            "TRUNCATE audit_log",
        ):
            with pytest.raises(DBAPIError):
                db.execute(text(stmt))
            db.rollback()


def test_secrets_are_redacted_in_snapshots():
    from datetime import UTC, datetime

    from app.audit import snapshot
    from app.models import Session

    s = Session(token_hash="abc", user_id=1, expires_at=datetime.now(UTC))
    assert snapshot(s)["token_hash"] == "[redacted]"


def test_audit_filters(admin, make_org):
    a, b = make_org("A"), make_org("B")
    r = admin.get("/api/audit", params={"organization_id": a["id"]}).json()
    assert r["total"] == 1 and r["items"][0]["organization_id"] == a["id"]
    r = admin.get("/api/audit", params={"actor_id": admin.user["id"], "action": "organization."})
    assert r.json()["total"] == 2
    assert b
