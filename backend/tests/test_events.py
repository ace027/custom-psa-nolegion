"""Service events land in the webhook outbox with facts only (never ticket text)."""

import json

import pytest
from sqlalchemy import text

from app import db as dbmod
from app import events, worker
from app import ticket_services as tsvc
from app.deps import Ctx
from app.events import EVENT_TYPES
from app.models import EmailMessage, Ticket
from app.scope import Scope
from tests.test_rmm_alerts import OTHER, alert, env, poll  # noqa: F401
from tests.test_webhooks import add_endpoint
from tests.vendorfakes import vendors  # noqa: F401

SECRET_TEXT = "the customer's private words"


@pytest.fixture
def ep(admin):
    return add_endpoint(admin.user["id"])


def sent(owner, event_type=None):
    q = "SELECT event_type, event_id, payload, status FROM webhook_deliveries"
    params = {}
    if event_type:
        q += " WHERE event_type = :t"
        params["t"] = event_type
    return owner.execute(text(q + " ORDER BY id"), params).all()


def types(owner):
    return [r.event_type for r in sent(owner)]


def keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from keys(v)


def pri(admin, name):
    return next(p["id"] for p in admin.get("/api/v1/priorities").json() if p["name"] == name)


def test_event_types_and_rule_triggers():
    assert len(EVENT_TYPES) == 8 and events.RULE_TRIGGERS == EVENT_TYPES
    assert events.automation_depth.get() == 0 and events.RULE_HOOK == []


def test_create_emits_created_with_facts_only(admin, owner, ep, make_ticket):
    t = make_ticket(subject="VPN down", description=SECRET_TEXT)
    [d] = sent(owner)
    p = d.payload
    assert d.event_type == "ticket.created" and p["type"] == "ticket.created"
    assert p["version"] == 1 and p["id"] == str(d.event_id) and p["occurred_at"]
    assert p["ticket"] == {
        "id": t["id"],
        "number": t["number"],
        "subject": "VPN down",
        "status": "new",
        "priority": "Normal",
        "organization": "Acme Corp",
        "assignee": None,
        "source": "manual",
        "url": f"http://localhost:8000/tickets/{t['id']}",
    }
    assert "alert" not in p
    assert not {"description", "body"} & set(keys(p))
    assert SECRET_TEXT not in json.dumps(p)


def test_create_with_assignee_emits_created_then_assigned(admin, owner, ep, make_ticket):
    t = make_ticket(assignee_id=admin.user["id"])
    assert types(owner) == ["ticket.created", "ticket.assigned"]
    p = sent(owner)[1].payload
    assert p["changes"] == {"assignee_id": [None, admin.user["id"]]}
    assert p["ticket"]["assignee"] == "admin user" and p["ticket"]["id"] == t["id"]


def test_update_emits_assigned_status_and_priority_with_changes(admin, owner, ep, make_ticket):
    t = make_ticket()
    owner.execute(text("DELETE FROM webhook_deliveries"))
    high = pri(admin, "High")
    r = admin.patch(
        f"/api/v1/tickets/{t['id']}",
        json={"assignee_id": admin.user["id"], "priority_id": high},
    )
    assert r.status_code == 200, r.text
    got = {d.event_type: d.payload["changes"] for d in sent(owner)}
    # picking up a new ticket also opens it
    assert got == {
        "ticket.assigned": {"assignee_id": [None, admin.user["id"]]},
        "ticket.status_changed": {"status": ["new", "open"]},
        "ticket.priority_changed": {"priority_id": [t["priority_id"], high]},
    }
    owner.execute(text("DELETE FROM webhook_deliveries"))
    admin.patch(f"/api/v1/tickets/{t['id']}", json={"status": "waiting_on_customer"})
    [d] = sent(owner)
    assert d.event_type == "ticket.status_changed"
    assert d.payload["changes"] == {"status": ["open", "waiting_on_customer"]}
    assert d.payload["ticket"]["status"] == "waiting_on_customer"


def test_no_event_when_nothing_relevant_changed(admin, owner, ep, make_ticket):
    t = make_ticket()
    owner.execute(text("DELETE FROM webhook_deliveries"))
    admin.patch(f"/api/v1/tickets/{t['id']}", json={"subject": "New subject"})
    admin.patch(f"/api/v1/tickets/{t['id']}", json={"priority_id": t["priority_id"]})
    assert sent(owner) == []


def test_bulk_update_emits_per_ticket(admin, owner, ep, make_ticket):
    ids = [make_ticket(subject=f"T{i}")["id"] for i in range(3)]
    owner.execute(text("DELETE FROM webhook_deliveries"))
    r = admin.post(
        "/api/v1/tickets/bulk",
        json={"ticket_ids": ids, "changes": {"priority_id": pri(admin, "Urgent")}},
    )
    assert r.json()["updated"] == 3
    rows = sent(owner, "ticket.priority_changed")
    assert sorted(d.payload["ticket"]["id"] for d in rows) == sorted(ids)
    assert len({d.event_id for d in rows}) == 3


def test_customer_reply_event(admin, owner, ep, make_ticket):
    t = make_ticket()
    owner.execute(text("DELETE FROM webhook_deliveries"))
    with dbmod.new_session() as db:
        dbmod.set_org_scope(db, "all")
        ctx = Ctx(db=db, user=None, scope=Scope.all())
        ticket = db.get(Ticket, t["id"])
        mail = EmailMessage(
            direction="in", ticket_id=ticket.id, organization_id=ticket.organization_id
        )
        db.add(mail)
        db.flush()
        tsvc.customer_reply(ctx, ticket, SECRET_TEXT, "c@example.com", mail)
        db.commit()
    [d] = sent(owner)
    assert d.event_type == "ticket.customer_reply" and d.payload["changes"] == {}
    assert SECRET_TEXT not in json.dumps(d.payload) and "c@example.com" not in json.dumps(d.payload)


def test_sla_breach_event_once_for_assigned_and_unassigned(admin, owner, ep, make_ticket):
    a = make_ticket(subject="assigned", assignee_id=admin.user["id"])
    u = make_ticket(subject="unassigned")
    fine = make_ticket(subject="fine")
    owner.execute(text("DELETE FROM webhook_deliveries"))
    for t in (a, u):
        owner.execute(
            text("UPDATE tickets SET sla_resolution_due = now() - interval '1 hour' WHERE id=:i"),
            {"i": t["id"]},
        )
    before = owner.execute(text("SELECT updated_at FROM tickets WHERE id=:i"), {"i": a["id"]})
    before = before.scalar()
    worker.notify_jobs()
    worker.notify_jobs()
    rows = sent(owner, "ticket.sla_breached")
    assert sorted(d.payload["ticket"]["id"] for d in rows) == sorted([a["id"], u["id"]])
    assert fine["id"] not in [d.payload["ticket"]["id"] for d in rows]
    stamped = owner.execute(
        text("SELECT id, sla_breached_event_at, updated_at FROM tickets WHERE id=:i"),
        {"i": a["id"]},
    ).one()
    assert stamped.sla_breached_event_at is not None and stamped.updated_at == before


def test_resolved_tickets_do_not_breach(admin, owner, ep, make_ticket):
    t = make_ticket()
    admin.patch(f"/api/v1/tickets/{t['id']}", json={"status": "resolved"})
    owner.execute(text("UPDATE tickets SET sla_resolution_due = now() - interval '1 hour'"))
    owner.execute(text("DELETE FROM webhook_deliveries"))
    worker.notify_jobs()
    assert sent(owner) == []


def test_rmm_alert_opened_after_created_then_cleared(env, owner, admin):  # noqa: F811
    add_endpoint(admin.user["id"])
    env.vendor.alerts = [alert("1", severity="CRITICAL")]
    poll(env.iid)
    assert types(owner) == ["ticket.created", "rmm_alert.opened"]
    opened = sent(owner, "rmm_alert.opened")[0].payload
    assert opened["alert"]["severity"] == "CRITICAL" and opened["alert"]["state"] == "open"
    assert opened["ticket"]["source"] == "rmm" and "[RMM]" in opened["ticket"]["subject"]
    assert not {"description", "body"} & set(keys(opened))
    env.vendor.alerts = [OTHER()]
    poll(env.iid)
    poll(env.iid)
    assert types(owner)[2:] == ["ticket.status_changed", "rmm_alert.cleared"]
    cleared = sent(owner, "rmm_alert.cleared")[0].payload
    assert cleared["alert"]["state"] == "cleared" and cleared["alert"]["resolution"] == "resolved"
    assert cleared["ticket"]["status"] == "resolved"
    status = sent(owner, "ticket.status_changed")[0].payload
    assert status["changes"] == {"status": ["new", "resolved"]}


def test_endpoint_only_gets_subscribed_events(admin, owner, make_ticket):
    add_endpoint(admin.user["id"], events=["ticket.assigned"])
    t = make_ticket()
    assert sent(owner) == []
    admin.patch(f"/api/v1/tickets/{t['id']}", json={"assignee_id": admin.user["id"]})
    assert types(owner) == ["ticket.assigned"]


def test_disabled_endpoint_gets_nothing(admin, owner, make_ticket):
    add_endpoint(admin.user["id"], enabled=False)
    make_ticket()
    assert sent(owner) == []


def test_rule_hook_runs_only_at_depth_zero(admin, owner, ep, make_ticket, monkeypatch):
    calls = []
    monkeypatch.setattr(events, "RULE_HOOK", [lambda *a: calls.append(a[1])])
    make_ticket()
    assert calls == ["ticket.created"]
    token = events.automation_depth.set(1)
    try:
        with dbmod.new_session() as db:
            dbmod.set_org_scope(db, "all")
            ctx = Ctx(db=db, user=None, scope=Scope.all())
            events.emit(ctx, "ticket.created", db.query(Ticket).first())
            db.commit()
    finally:
        events.automation_depth.reset(token)
    assert calls == ["ticket.created"]  # not called at depth 1
    assert types(owner) == ["ticket.created", "ticket.created"]  # webhooks still fire


def test_a_queue_failure_never_breaks_the_ticket(admin, owner, ep, make_ticket, monkeypatch):
    from app import webhooks

    def boom(*a, **kw):
        raise RuntimeError("outbox down")

    monkeypatch.setattr(webhooks, "enqueue", boom)
    t = make_ticket()
    assert admin.get(f"/api/v1/tickets/{t['id']}").status_code == 200
    assert sent(owner) == []
