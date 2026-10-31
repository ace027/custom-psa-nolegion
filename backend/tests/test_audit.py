import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import new_session


def count(admin):
    return admin.get("/api/v1/audit", params={"limit": 1}).json()["total"]


def test_every_mutating_endpoint_writes_an_audit_row(admin, make_org):
    org = make_org("Acme")  # organization.create
    oid = org["id"]
    site = admin.post(f"/api/v1/organizations/{oid}/sites", json={"name": "HQ"}).json()
    contact = admin.post(f"/api/v1/organizations/{oid}/contacts", json={"name": "Pat"}).json()
    user = admin.post(
        "/api/v1/users", json={"email": "t@example.com", "display_name": "T", "role": "tech"}
    ).json()
    ticket = admin.post("/api/v1/tickets", json={"organization_id": oid, "subject": "T"}).json()
    wt = admin.get("/api/v1/work-types").json()[0]["id"]
    entry = admin.post(
        f"/api/v1/tickets/{ticket['id']}/time", json={"work_type_id": wt, "minutes": 5}
    ).json()
    queue = admin.post("/api/v1/queues", json={"name": "Qx"}).json()
    cat = admin.post("/api/v1/categories", json={"name": "Cx"}).json()
    prio = admin.post("/api/v1/priorities", json={"name": "Px", "rank": 5}).json()
    mutations = [
        ("PATCH", f"/api/v1/organizations/{oid}", {"notes": "x"}),
        ("POST", f"/api/v1/organizations/{oid}/archive", None),
        ("POST", f"/api/v1/organizations/{oid}/unarchive", None),
        ("POST", f"/api/v1/organizations/{oid}/sites", {"name": "S2"}),
        ("PATCH", f"/api/v1/sites/{site['id']}", {"city": "x"}),
        ("POST", f"/api/v1/sites/{site['id']}/archive", None),
        ("POST", f"/api/v1/sites/{site['id']}/unarchive", None),
        ("POST", f"/api/v1/organizations/{oid}/contacts", {"name": "C2"}),
        ("PATCH", f"/api/v1/contacts/{contact['id']}", {"title": "x"}),
        ("POST", f"/api/v1/contacts/{contact['id']}/archive", None),
        ("POST", f"/api/v1/contacts/{contact['id']}/unarchive", None),
        ("POST", "/api/v1/users", {"email": "u2@example.com", "display_name": "U", "role": "tech"}),
        ("PATCH", f"/api/v1/users/{user['id']}", {"display_name": "T2"}),
        ("POST", "/api/v1/organizations", {"name": "Other"}),
        ("POST", "/api/v1/tickets", {"organization_id": oid, "subject": "T"}),
        ("PATCH", f"/api/v1/tickets/{ticket['id']}", {"subject": "T2"}),
        ("POST", f"/api/v1/tickets/{ticket['id']}/notes", {"body": "n"}),
        ("POST", f"/api/v1/tickets/{ticket['id']}/time", {"work_type_id": wt, "minutes": 5}),
        ("PATCH", f"/api/v1/time-entries/{entry['id']}", {"minutes": 6}),
        ("POST", f"/api/v1/time-entries/{entry['id']}/void", None),
        ("PATCH", "/api/v1/settings", {"sla_at_risk_percent": 30}),
        ("POST", "/api/v1/queues", {"name": "Q9"}),
        ("PATCH", f"/api/v1/queues/{queue['id']}", {"name": "Q10"}),
        ("POST", f"/api/v1/queues/{queue['id']}/archive", None),
        ("POST", f"/api/v1/queues/{queue['id']}/unarchive", None),
        ("POST", "/api/v1/categories", {"name": "C9"}),
        ("PATCH", f"/api/v1/categories/{cat['id']}", {"name": "C10"}),
        ("POST", f"/api/v1/categories/{cat['id']}/archive", None),
        ("POST", f"/api/v1/categories/{cat['id']}/unarchive", None),
        ("POST", "/api/v1/work-types", {"name": "W9"}),
        ("PATCH", f"/api/v1/work-types/{wt}", {"name": "W10"}),
        ("POST", f"/api/v1/work-types/{wt}/archive", None),
        ("POST", f"/api/v1/work-types/{wt}/unarchive", None),
        ("POST", "/api/v1/priorities", {"name": "P9", "rank": 9}),
        ("PATCH", f"/api/v1/priorities/{prio['id']}", {"rank": 8}),
        ("POST", f"/api/v1/priorities/{prio['id']}/archive", None),
        ("POST", f"/api/v1/priorities/{prio['id']}/unarchive", None),
        ("POST", "/api/v1/auth/logout", None),
    ]
    for method, path, body in mutations:
        # re-login after logout so audit can still be read
        before = count(admin)
        r = admin.request(method, path, json=body)
        assert r.status_code < 400, (method, path, r.text)
        if path.endswith("/logout"):
            admin.post("/api/v1/auth/dev-login", json={"email": admin.user["email"]})
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
    r = admin.get("/api/v1/audit", params={"organization_id": a["id"]}).json()
    assert r["total"] == 1 and r["items"][0]["organization_id"] == a["id"]
    r = admin.get("/api/v1/audit", params={"actor_id": admin.user["id"], "action": "organization."})
    assert r.json()["total"] == 2
    assert b
