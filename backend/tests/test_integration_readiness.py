"""Phase 12 integration-readiness fields: uuids, rmm_client_id, sources, author and entry types."""

import uuid

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from alembic import command
from app import db as dbmod
from app import seed
from app import ticket_services as tsvc
from app.auth import oidc
from app.db import new_session
from app.deps import Ctx
from app.main import app
from app.scope import Scope
from tests.conftest import RouteRecorder
from tests.test_asset_sync import setup_ninja
from tests.vendorfakes import dev, run_sync, vendors  # noqa: F401


def _sql(owner_engine, sql, **params):
    with owner_engine.begin() as c:
        res = c.execute(text(sql), params)
        return res.all() if res.returns_rows else []


def _org(owner_engine, name):
    return _sql(owner_engine, "INSERT INTO organizations (name) VALUES (:n) RETURNING id", n=name)[
        0
    ][0]


# ---- uuids ----
def test_uuids_present_unique_and_stable(admin, make_org):
    org = make_org("Acme Corp")
    site = admin.post(f"/api/v1/organizations/{org['id']}/sites", json={"name": "HQ"}).json()
    contact = admin.post(
        f"/api/v1/organizations/{org['id']}/contacts", json={"name": "Pat", "email": "p@acme.com"}
    ).json()
    other = make_org("Other Co")
    ids = {str(uuid.UUID(x["uuid"])) for x in (org, site, contact, other)}
    assert len(ids) == 4
    assert admin.get(f"/api/v1/organizations/{org['id']}").json()["uuid"] == org["uuid"]
    assert admin.get(f"/api/v1/organizations/{org['id']}").json()["uuid"] == org["uuid"]
    listed = admin.get(f"/api/v1/organizations/{org['id']}/sites").json()
    assert [s["uuid"] for s in listed] == [site["uuid"]]
    listed = admin.get(f"/api/v1/organizations/{org['id']}/contacts").json()
    assert [c["uuid"] for c in listed] == [contact["uuid"]]


def test_uuid_is_not_client_writable(admin, make_org):
    org = make_org("Acme Corp")
    forged = str(uuid.uuid4())
    admin.patch(f"/api/v1/organizations/{org['id']}", json={"uuid": forged, "notes": "x"})
    assert admin.get(f"/api/v1/organizations/{org['id']}").json()["uuid"] == org["uuid"]


# ---- rmm_client_id ----
def test_rmm_client_id_set_cleared_duplicate_and_nulls(admin, make_org):
    a, b, c = make_org("A Co"), make_org("B Co"), make_org("C Co")
    assert a["rmm_client_id"] is None and b["rmm_client_id"] is None  # many NULLs are fine
    rid = str(uuid.uuid4())
    r = admin.patch(f"/api/v1/organizations/{a['id']}", json={"rmm_client_id": rid})
    assert r.status_code == 200 and r.json()["rmm_client_id"] == rid
    r = admin.patch(f"/api/v1/organizations/{b['id']}", json={"rmm_client_id": rid})
    assert r.status_code == 409
    assert r.json()["detail"] == "rmm_client_id already linked to another client"
    r = admin.patch(f"/api/v1/organizations/{a['id']}", json={"rmm_client_id": None})
    assert r.status_code == 200 and r.json()["rmm_client_id"] is None
    assert (
        admin.patch(f"/api/v1/organizations/{b['id']}", json={"rmm_client_id": rid}).status_code
        == 200
    )
    assert admin.patch(f"/api/v1/organizations/{c['id']}", json={"name": "C2"}).status_code == 200


def test_rmm_client_id_needs_org_write(login, make_org):
    org = make_org("A Co")
    reader = login("read_only", "ro@example.com")
    r = reader.patch(
        f"/api/v1/organizations/{org['id']}", json={"rmm_client_id": str(uuid.uuid4())}
    )
    assert r.status_code == 403


# ---- assets ----
def test_asset_source_defaults_check_and_partial_unique(owner_engine):
    org = _org(owner_engine, "Acme")
    ins = (
        "INSERT INTO assets (organization_id, kind, name, source, external_id) "
        "VALUES (:o, 'other', :n, :s, :e)"
    )
    _sql(
        owner_engine,
        "INSERT INTO assets (organization_id, kind, name) VALUES (:o,'other','m')",
        o=org,
    )
    row = _sql(owner_engine, "SELECT source, external_id FROM assets")[0]
    assert tuple(row) == ("manual", None)
    with pytest.raises(IntegrityError):
        _sql(owner_engine, ins, o=org, n="x", s="other", e=None)
    _sql(owner_engine, ins, o=org, n="a", s="rmm", e="X")
    with pytest.raises(IntegrityError):
        _sql(owner_engine, ins, o=org, n="b", s="rmm", e="X")
    _sql(owner_engine, ins, o=org, n="c", s="import", e="X")  # same id under another source
    _sql(owner_engine, ins, o=org, n="d", s="rmm", e=None)  # NULLs never collide
    _sql(owner_engine, ins, o=org, n="e", s="rmm", e=None)


def test_sync_created_asset_is_rmm_and_read_only(admin, make_org, vendors):  # noqa: F811
    org, i, _ = setup_ninja(admin, make_org, vendors, [dev("1", "PC-1", "SER-0000001")])
    run_sync(i["id"])
    got = admin.get(f"/api/v1/organizations/{org['id']}/assets").json()
    assert [(a["source"], a["external_id"]) for a in got] == [("rmm", None)]
    detail = admin.get(f"/api/v1/assets/{got[0]['id']}").json()
    assert detail["source"] == "rmm" and "external_id" in detail


# ---- tickets ----
def test_ticket_source_manual_for_staff_and_api_for_key(admin, org_ctx):
    body = {"organization_id": org_ctx["org"], "subject": "By hand"}
    assert admin.post("/api/v1/tickets", json=body).json()["source"] == "manual"
    made = admin.post(
        "/api/v1/api-keys", json={"name": "n8n", "permissions": ["ticket:read", "ticket:write"]}
    ).json()
    key = TestClient(RouteRecorder(app), headers={"Authorization": f"Bearer {made['token']}"})
    r = key.post("/api/v1/tickets", json={**body, "subject": "By key"})
    assert r.status_code == 201 and r.json()["source"] == "api"


def test_external_ref_duplicate_is_409_with_ticket_id(admin, org_ctx):
    body = {"organization_id": org_ctx["org"], "subject": "Alert", "external_ref": "  RMM-1  "}
    first = admin.post("/api/v1/tickets", json=body)
    assert first.status_code == 201 and first.json()["external_ref"] == "RMM-1"
    dup = admin.post("/api/v1/tickets", json=body)
    assert dup.status_code == 409
    assert dup.json()["detail"] == {
        "message": "external_ref already used",
        "ticket_id": first.json()["id"],
    }
    blank = {**body, "external_ref": "   "}
    a, b = admin.post("/api/v1/tickets", json=blank), admin.post("/api/v1/tickets", json=blank)
    assert a.status_code == b.status_code == 201 and a.json()["external_ref"] is None
    assert (
        admin.post("/api/v1/tickets", json={**body, "external_ref": "x" * 201}).status_code == 422
    )


def test_same_external_ref_under_another_source_is_allowed(admin, org_ctx, owner_engine):
    made = admin.post(
        "/api/v1/tickets",
        json={"organization_id": org_ctx["org"], "subject": "A", "external_ref": "R"},
    ).json()
    other = admin.post("/api/v1/tickets", json={"organization_id": org_ctx["org"], "subject": "B"})
    tid = other.json()["id"]
    _sql(owner_engine, "UPDATE tickets SET source='rmm', external_ref='R' WHERE id=:t", t=tid)
    with pytest.raises(IntegrityError):
        _sql(owner_engine, "UPDATE tickets SET source='manual' WHERE id=:t", t=tid)
    assert made["external_ref"] == "R"


def test_ticket_source_check_rejects_ui(owner_engine, make_ticket):
    make_ticket()
    with pytest.raises(IntegrityError):
        _sql(owner_engine, "UPDATE tickets SET source='ui'")


# ---- notes ----
def test_note_author_type_human_system_and_check(admin, make_ticket, owner_engine):
    t = make_ticket()
    n = admin.post(f"/api/v1/tickets/{t['id']}/notes", json={"body": "hi"}).json()
    assert n["author_type"] == "human"
    with new_session() as db:
        dbmod.set_org_scope(db, "all")
        ctx = Ctx(db=db, user=None, scope=Scope.all())
        ticket = db.get(tsvc.Ticket, t["id"])
        tsvc.system_note(ctx, ticket, "Escalated")
        db.commit()
    notes = admin.get(f"/api/v1/tickets/{t['id']}/notes").json()
    assert [x["author_type"] for x in notes] == ["human", "system"]
    with pytest.raises(IntegrityError):
        _sql(owner_engine, "UPDATE ticket_notes SET author_type='bot'")


# ---- time ----
def test_automation_time_is_forced_non_billable(admin, make_ticket, wt):
    t = make_ticket()
    wid = wt["Remote"]
    url = f"/api/v1/tickets/{t['id']}/time"
    r = admin.post(url, json={"work_type_id": wid, "minutes": 30, "entry_type": "automation"})
    assert r.status_code == 201
    assert (r.json()["entry_type"], r.json()["billable"], r.json()["minutes_billable"]) == (
        "automation",
        False,
        0,
    )
    r = admin.post(
        url,
        json={"work_type_id": wid, "minutes": 30, "entry_type": "automation", "billable": True},
    )
    assert r.status_code == 422 and "never billable" in r.text
    eid = admin.get(url).json()[0]["id"]
    assert admin.patch(f"/api/v1/time-entries/{eid}", json={"billable": True}).status_code == 422
    plain = admin.post(url, json={"work_type_id": wid, "minutes": 15}).json()
    assert plain["entry_type"] == "labour" and plain["billable"] is True


def test_database_rejects_billable_automation_time(admin, make_ticket, owner_engine):
    t = make_ticket()
    wid = _sql(owner_engine, "SELECT id FROM work_types LIMIT 1")[0][0]
    uid = admin.user["id"]
    ins = (
        "INSERT INTO time_entries (ticket_id, organization_id, user_id, work_type_id, work_date,"
        " minutes_actual, minutes_billable, billable, entry_type) "
        "SELECT :t, organization_id, :u, :w, current_date, 10, 0, :b, :e FROM tickets WHERE id=:t"
    )
    _sql(owner_engine, ins, t=t["id"], u=uid, w=wid, b=False, e="automation")
    with pytest.raises(IntegrityError):
        _sql(owner_engine, ins, t=t["id"], u=uid, w=wid, b=True, e="automation")
    with pytest.raises(IntegrityError):
        _sql(owner_engine, ins, t=t["id"], u=uid, w=wid, b=False, e="robot")


# ---- users ----
def test_entra_tenant_id_stored_on_login(make_user, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "entra_tenant_id", "tenant-1")
    make_user("tech", "tech@example.com")
    claims = {"tid": "tenant-1", "oid": "oid-1", "email": "tech@example.com"}
    with new_session() as db:
        user = oidc.resolve_user_from_claims(db, claims)
        assert user.entra_tenant_id == "tenant-1"
        db.commit()
        uid = user.id
    with new_session() as db:
        assert db.get(oidc.User, uid).entra_tenant_id == "tenant-1"


def test_user_out_exposes_entra_tenant_id(admin):
    assert admin.get("/api/v1/auth/me").json()["entra_tenant_id"] is None


# ---- seeded rehearsal ----
def test_seeded_downgrade_to_0032_and_back(owner_engine):
    seed.run()
    tables = ("organizations", "sites", "contacts", "tickets")
    count = lambda: {  # noqa: E731
        t: _sql(owner_engine, f"SELECT count(*) FROM {t}")[0][0] for t in tables
    }
    before = count()
    manual = _sql(owner_engine, "SELECT count(*) FROM tickets WHERE source = 'manual'")[0][0]
    assert manual > 0
    cfg = Config("alembic.ini")
    command.downgrade(cfg, "0032")
    assert count() == before
    assert _sql(owner_engine, "SELECT count(*) FROM tickets WHERE source = 'ui'")[0][0] == manual
    command.upgrade(cfg, "head")
    assert count() == before
    assert _sql(owner_engine, "SELECT count(*) FROM tickets WHERE source = 'ui'")[0][0] == 0
    for t in ("organizations", "sites", "contacts"):
        uuids = [r[0] for r in _sql(owner_engine, f"SELECT uuid FROM {t}")]
        assert None not in uuids and len(set(uuids)) == len(uuids) == before[t]


def test_downgrade_rewrites_rule_conditions(owner_engine, admin):
    rule = admin.post(
        "/api/v1/automation/rules",
        json={
            "name": "r",
            "trigger": "ticket.created",
            "conditions": [{"field": "source", "op": "in", "value": ["manual", "email"]}],
            "actions": [{"type": "escalate"}],
        },
    )
    assert rule.status_code == 201, rule.text
    cfg = Config("alembic.ini")
    command.downgrade(cfg, "0032")
    cond = _sql(owner_engine, "SELECT conditions::text FROM automation_rules")[0][0]
    assert '"ui"' in cond and '"manual"' not in cond
    command.upgrade(cfg, "head")
    cond = _sql(owner_engine, "SELECT conditions::text FROM automation_rules")[0][0]
    assert '"manual"' in cond and '"ui"' not in cond
