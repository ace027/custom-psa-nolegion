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


def test_audit_entries_are_readable(admin, make_org):
    org = make_org("Readable Co")
    admin.patch(f"/api/v1/organizations/{org['id']}", json={"notes": "hello"})
    items = admin.get("/api/v1/audit", params={"organization_id": org["id"]}).json()["items"]
    upd = next(i for i in items if i["action"] == "organization.update")
    assert upd["actor_name"] == "admin user"
    assert upd["organization_name"] == "Readable Co"
    assert upd["summary"] == f"admin user updated client #{org['id']} for Readable Co"
    ch = {c["field"]: c for c in upd["changes"]}
    assert ch["notes"]["label"] == "notes" and ch["notes"]["after"] == "hello"
    assert all(i["summary"] for i in items)


def test_audit_masks_secret_like_keys(admin, owner):
    owner.execute(
        text(
            "INSERT INTO audit_log (actor_type, actor_id, action, entity_type, entity_id, before, after) "
            "VALUES ('user', 999999, 'thing.update', 'things', 1, "
            '\'{"api_token": "old"}\', \'{"api_token": "new"}\')'
        )
    )
    row = admin.get("/api/v1/audit", params={"entity_type": "things"}).json()["items"][0]
    assert row["actor_name"] is None and row["summary"].startswith("User #999999 updated thing #1")
    assert row["changes"] == [
        {"field": "api_token", "label": "api token", "before": "(changed)", "after": "(changed)"}
    ]


def test_audit_date_filter(admin, owner):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(admin.get("/api/v1/settings").json()["timezone"])
    old = datetime.now(tz) - timedelta(days=3)
    owner.execute(
        text(
            "INSERT INTO audit_log (actor_type, action, occurred_at) "
            "VALUES ('system', 'old.create', :t)"
        ),
        {"t": old},
    )
    day = old.date()

    def total(**p):
        return admin.get("/api/v1/audit", params={"action": "old.", **p}).json()["total"]

    assert total() == 1
    assert total(date_from=day.isoformat(), date_to=day.isoformat()) == 1
    assert total(date_from=(day + timedelta(days=1)).isoformat()) == 0
    assert total(date_to=(day - timedelta(days=1)).isoformat()) == 0
    r = admin.get("/api/v1/audit", params={"date_from": "2026-02-02", "date_to": "2026-02-01"})
    assert r.status_code == 422 and "date_to is before date_from" in r.text


def test_audit_entity_types_and_permissions(admin, make_org, login):
    make_org()
    types = admin.get("/api/v1/audit/entity-types").json()
    assert {"value": "organizations", "label": "client"} in types
    assert [t["label"] for t in types] == sorted(t["label"] for t in types)
    for role in ("tech", "read_only"):
        c = login(role)
        assert c.get("/api/v1/audit").status_code == 403
        assert c.get("/api/v1/audit/entity-types").status_code == 403
