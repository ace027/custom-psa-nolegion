"""Rules engine: evaluation, every action from a real event, loop guard, idempotency, rate cap,
failure isolation and audit."""

import uuid

import pytest
from sqlalchemy import text

from app import automation, events
from app import db as dbmod
from app import ticket_services as tsvc
from app.deps import Ctx
from app.models import Ticket
from app.scope import Scope
from tests.test_events import pri
from tests.test_rmm_alerts import OTHER, alert, env, poll  # noqa: F401
from tests.test_webhooks import add_endpoint
from tests.vendorfakes import vendors  # noqa: F401


def queue(admin, name):
    return next(q["id"] for q in admin.get("/api/queues").json() if q["name"] == name)


def mkrule(admin, **kw):
    body = {
        "name": "Rule",
        "trigger": "ticket.created",
        "conditions": [],
        "actions": [],
        **kw,
    }
    r = admin.post("/api/automation/rules", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def runs(owner, rule_id=None):
    q = "SELECT rule_id, event_id, matched, trace FROM automation_runs"
    if rule_id:
        q += f" WHERE rule_id = {int(rule_id)}"
    return owner.execute(text(q + " ORDER BY id")).all()


def ticket_row(owner, tid):
    return owner.execute(
        text("SELECT assignee_id, queue_id, priority_id, status FROM tickets WHERE id=:i"),
        {"i": tid},
    ).one()


@pytest.fixture
def tech(login):
    return login("tech")


# ---- evaluate (pure) ----
FACTS = {
    "organization_id": 5,
    "queue_id": 2,
    "category_id": None,
    "priority_id": 3,
    "ticket_type_id": None,
    "status": "new",
    "source": "email",
    "assignee_id": None,
    "subject": "Printer is on FIRE",
    "alert_severity": "CRITICAL",
}


@pytest.mark.parametrize(
    "field,op,value,expected",
    [
        ("queue_id", "eq", 2, True),
        ("queue_id", "eq", 3, False),
        ("queue_id", "ne", 3, True),
        ("queue_id", "in", [1, 2], True),
        ("queue_id", "in", [1, 3], False),
        ("queue_id", "not_in", [1, 3], True),
        ("queue_id", "not_in", [2], False),
        ("assignee_id", "is_empty", None, True),
        ("assignee_id", "is_not_empty", None, False),
        ("organization_id", "is_not_empty", None, True),
        ("subject", "contains", "fire", True),
        ("subject", "contains", "water", False),
        ("subject", "eq", "Printer is on FIRE", True),
        ("status", "in", ["new", "open"], True),
        ("alert_severity", "eq", "CRITICAL", True),
        ("alert_severity", "ne", "CRITICAL", False),
        ("queue_id", "contains", "2", False),  # not allowed for the field: never matches
        ("nope", "eq", 1, False),
    ],
)
def test_evaluate_truth_table(field, op, value, expected):
    ok, trace = automation.evaluate([{"field": field, "op": op, "value": value}], FACTS)
    assert ok is expected
    assert trace[0]["matched"] is expected and trace[0]["actual"] == FACTS.get(field)


def test_evaluate_is_an_and_and_empty_always_matches():
    assert automation.evaluate([], FACTS) == (True, [])
    ok, trace = automation.evaluate(
        [
            {"field": "queue_id", "op": "eq", "value": 2},
            {"field": "status", "op": "eq", "value": "open"},
        ],
        FACTS,
    )
    assert ok is False and [t["matched"] for t in trace] == [True, False]


def test_constants():
    assert automation.RATE_CAP == 200
    assert automation.ACTIONS == (
        "assign",
        "set_queue",
        "set_priority",
        "escalate",
        "notify",
        "webhook",
        "create_ticket",
    )


# ---- actions from real events ----
def test_assign_set_queue_and_set_priority_in_position_order(admin, tech, owner, make_ticket):
    sec = queue(admin, "Security")
    high = pri(admin, "High")
    both = [{"field": "subject", "op": "contains", "value": "vpn"}]
    second = mkrule(
        admin, name="B", position=2, conditions=both,
        actions=[{"type": "set_priority", "priority_id": high}],
    )  # fmt: skip
    first = mkrule(
        admin, name="A", position=1, conditions=both,
        actions=[
            {"type": "assign", "user_id": tech.user["id"]},
            {"type": "set_queue", "queue_id": sec},
        ],
    )  # fmt: skip
    t = make_ticket(subject="VPN is down")
    row = ticket_row(owner, t["id"])
    assert (row.assignee_id, row.queue_id, row.priority_id) == (tech.user["id"], sec, high)
    r = runs(owner)
    assert [x.rule_id for x in r] == [first["id"], second["id"]]  # position order
    assert [a["status"] for a in r[0].trace["actions"]] == ["done", "done"]
    assert r[0].trace["conditions"][0] == {
        "field": "subject",
        "op": "contains",
        "value": "vpn",
        "actual": "VPN is down",
        "matched": True,
    }
    rules = {x["id"]: x for x in admin.get("/api/automation/rules").json()}
    assert rules[first["id"]]["fire_count"] == 1 and rules[first["id"]]["last_fired_at"]


def test_non_matching_rule_is_recorded_but_runs_nothing(admin, owner, make_ticket):
    rule = mkrule(
        admin,
        conditions=[{"field": "subject", "op": "contains", "value": "zzz"}],
        actions=[{"type": "set_priority", "priority_id": pri(admin, "Low")}],
    )
    t = make_ticket()
    [r] = runs(owner, rule["id"])
    assert r.matched is False and r.trace["actions"] == []
    assert ticket_row(owner, t["id"]).priority_id == t["priority_id"]
    assert admin.get("/api/automation/rules").json()[0]["fire_count"] == 0


def test_escalate_steps_up_writes_a_note_and_stops_at_the_top(admin, owner, make_ticket):
    mkrule(admin, name="Esc", trigger="ticket.created", actions=[{"type": "escalate"}])
    t = make_ticket()
    assert ticket_row(owner, t["id"]).priority_id == pri(admin, "High")  # Normal -> High
    note = owner.execute(text("SELECT body FROM ticket_notes")).scalar()
    assert note == "Escalated by rule Esc"
    urgent = make_ticket(priority_id=pri(admin, "Urgent"))
    last = runs(owner)[-1]
    assert last.trace["actions"][0]["status"] == "skipped"
    assert last.trace["actions"][0]["detail"] == "already most urgent"
    assert ticket_row(owner, urgent["id"]).priority_id == pri(admin, "Urgent")


def test_notify_emails_the_user_or_is_skipped(admin, tech, owner, mail_ready, make_ticket):
    rule = mkrule(admin, actions=[{"type": "notify", "user_id": tech.user["id"]}])
    t = make_ticket()
    mail = owner.execute(
        text("SELECT to_emails, subject FROM email_messages WHERE subject LIKE 'PSA:%'")
    ).all()
    assert len(mail) == 1 and mail[0].to_emails == [tech.user["email"]]
    assert "matched an automation rule" in mail[0].subject
    assert runs(owner, rule["id"])[0].trace["actions"][0]["status"] == "done"
    # preference off: skipped
    owner.execute(
        text("UPDATE users SET notify_assigned = false WHERE id = :i"), {"i": tech.user["id"]}
    )
    make_ticket(subject="again")
    assert runs(owner, rule["id"])[-1].trace["actions"][0]["status"] == "skipped"
    assert t["id"]


def test_notify_skipped_when_mail_is_not_configured(admin, tech, owner, make_ticket):
    rule = mkrule(admin, actions=[{"type": "notify", "user_id": tech.user["id"]}])
    make_ticket()
    assert runs(owner, rule["id"])[0].trace["actions"][0]["status"] == "skipped"


def test_webhook_action_sends_to_a_chosen_endpoint_only(admin, owner, make_ticket):
    chosen = add_endpoint(admin.user["id"], events=["ticket.assigned"], name="chosen")
    rule = mkrule(admin, actions=[{"type": "webhook", "endpoint_id": chosen}])
    make_ticket()
    rows = owner.execute(text("SELECT endpoint_id, event_type FROM webhook_deliveries")).all()
    assert [(r.endpoint_id, r.event_type) for r in rows] == [(chosen, "ticket.created")]
    assert runs(owner, rule["id"])[0].trace["actions"][0]["status"] == "done"


def test_webhook_action_to_an_already_subscribed_endpoint_is_skipped_not_doubled(
    admin, owner, make_ticket
):
    ep = add_endpoint(admin.user["id"])
    rule = mkrule(admin, actions=[{"type": "webhook", "endpoint_id": ep}])
    make_ticket()
    assert owner.execute(text("SELECT count(*) FROM webhook_deliveries")).scalar() == 1
    act = runs(owner, rule["id"])[0].trace["actions"][0]
    assert act["status"] == "skipped"


def test_create_ticket_links_it_and_skips_without_an_organization(admin, owner, make_ticket):
    rule = mkrule(
        admin,
        conditions=[{"field": "source", "op": "in", "value": ["ui", "email"]}],
        actions=[
            {"type": "create_ticket", "subject": "Follow up", "priority_id": pri(admin, "Low")}
        ],
    )
    t = make_ticket()
    rows = owner.execute(
        text("SELECT id, source, subject, organization_id, description FROM tickets ORDER BY id")
    ).all()
    assert [r.subject for r in rows] == ["Printer down", "Follow up"]
    new = rows[1]
    assert new.source == "rule" and new.organization_id == rows[0].organization_id
    assert new.description == f"Created by automation rule Rule from ticket #{t['number']}."
    link = owner.execute(
        text("SELECT kind, source_ticket_id, target_ticket_id FROM ticket_links")
    ).one()
    assert (link.kind, link.source_ticket_id, link.target_ticket_id) == (
        "related",
        rows[0].id,
        new.id,
    )
    assert runs(owner, rule["id"])[0].trace["actions"][0]["status"] == "done"
    # a ticket with no organization: skipped
    with dbmod.new_session() as db:
        dbmod.set_org_scope(db, "all")
        ctx = Ctx(db=db, user=None, scope=Scope.all())
        bare = tsvc.create_ticket(
            ctx, {"subject": "No org"}, source="email", requester_email="x@example.com"
        )
        db.commit()
        bare_id = bare.id
    last = [r for r in runs(owner, rule["id"])][-1]
    assert last.trace["actions"][0] == {
        "type": "create_ticket",
        "params": {"subject": "Follow up", "priority_id": pri(admin, "Low")},
        "status": "skipped",
        "detail": "the ticket has no organization",
    }
    assert (
        owner.execute(text("SELECT count(*) FROM tickets WHERE organization_id IS NULL")).scalar()
        == 1
    )
    assert bare_id


# ---- disabled, archived ----
def test_disabled_and_archived_rules_never_run(admin, owner, make_ticket):
    act = [{"type": "set_priority", "priority_id": pri(admin, "Low")}]
    off = mkrule(admin, name="off", enabled=False, actions=act)
    gone = mkrule(admin, name="gone", actions=act)
    assert admin.post(f"/api/automation/rules/{gone['id']}/archive").status_code == 200
    t = make_ticket()
    assert runs(owner) == []
    assert ticket_row(owner, t["id"]).priority_id == t["priority_id"]
    assert off["enabled"] is False


# ---- loop guard ----
def test_loop_guard_rules_do_not_trigger_rules_but_webhooks_fire(admin, tech, owner, make_ticket):
    add_endpoint(admin.user["id"], events=["ticket.assigned"])
    first = mkrule(
        admin,
        name="assigner",
        trigger="ticket.status_changed",
        actions=[{"type": "assign", "user_id": tech.user["id"]}],
    )
    second = mkrule(
        admin,
        name="on assigned",
        trigger="ticket.assigned",
        actions=[{"type": "set_priority", "priority_id": pri(admin, "Low")}],
    )
    t = make_ticket()
    r = admin.patch(f"/api/tickets/{t['id']}", json={"status": "waiting_on_customer"})
    assert r.status_code == 200, r.text
    assert events.automation_depth.get() == 0
    assert [r.rule_id for r in runs(owner)] == [first["id"]]  # the second never ran
    assert ticket_row(owner, t["id"]).assignee_id == tech.user["id"]
    assert ticket_row(owner, t["id"]).priority_id == t["priority_id"]
    hooks = owner.execute(
        text("SELECT payload FROM webhook_deliveries WHERE event_type='ticket.assigned'")
    ).all()
    assert len(hooks) == 1
    assert hooks[0].payload["changes"] == {"assignee_id": [None, tech.user["id"]]}
    # a human assigning afterwards does run the second rule
    admin.patch(f"/api/tickets/{t['id']}", json={"assignee_id": admin.user["id"]})
    assert [r.rule_id for r in runs(owner, second["id"])] == [second["id"]]


# ---- idempotency ----
def test_on_event_twice_with_the_same_event_runs_once(admin, owner, make_ticket):
    rule = mkrule(admin, trigger="ticket.status_changed", actions=[{"type": "escalate"}])
    t = make_ticket()
    event_id = uuid.uuid4()
    for _ in range(2):
        with dbmod.new_session() as db:
            dbmod.set_org_scope(db, "all")
            ctx = Ctx(db=db, user=None, scope=Scope.all())
            automation.on_event(
                ctx, "ticket.status_changed", event_id, db.get(Ticket, t["id"]), None, None
            )
            db.commit()
    assert len(runs(owner, rule["id"])) == 1
    assert owner.execute(text("SELECT count(*) FROM ticket_notes")).scalar() == 1
    assert admin.get("/api/automation/rules").json()[0]["fire_count"] == 1


# ---- rate cap ----
def test_rate_cap_disables_the_rule_once_and_audits(admin, owner, make_ticket):
    rule = mkrule(admin, actions=[{"type": "set_priority", "priority_id": pri(admin, "Low")}])
    owner.execute(
        text(
            "INSERT INTO automation_runs (rule_id, event_id, event_type, matched, trace) "
            "SELECT :r, gen_random_uuid(), 'ticket.created', true, '{}'::jsonb "
            "FROM generate_series(1, 200)"
        ),
        {"r": rule["id"]},
    )
    t = make_ticket()
    assert ticket_row(owner, t["id"]).priority_id == t["priority_id"]  # did not run
    row = owner.execute(
        text("SELECT enabled, disabled_reason FROM automation_rules WHERE id=:i"), {"i": rule["id"]}
    ).one()
    assert row.enabled is False and row.disabled_reason == "Fired more than 200 times in an hour"
    make_ticket(subject="two")
    n = owner.execute(
        text("SELECT count(*) FROM audit_log WHERE action='automation.rule_auto_disabled'")
    ).scalar()
    assert n == 1


# ---- failure isolation ----
def test_a_failing_action_keeps_the_ticket_change_and_is_traced(
    admin, tech, owner, make_ticket, monkeypatch
):
    sec = queue(admin, "Security")
    rule = mkrule(
        admin,
        actions=[
            {"type": "assign", "user_id": tech.user["id"]},
            {"type": "set_queue", "queue_id": sec},
            {"type": "set_priority", "priority_id": pri(admin, "Low")},
        ],
    )
    real = tsvc.update_ticket

    def flaky(ctx, ticket_id, data):
        if "queue_id" in data:
            raise RuntimeError("boom " + "x" * 400)
        return real(ctx, ticket_id, data)

    monkeypatch.setattr(tsvc, "update_ticket", flaky)
    t = make_ticket()
    row = ticket_row(owner, t["id"])
    assert row.assignee_id == tech.user["id"] and row.priority_id == pri(admin, "Low")
    assert row.queue_id != sec
    acts = runs(owner, rule["id"])[0].trace["actions"]
    assert [a["status"] for a in acts] == ["done", "failed", "done"]
    assert acts[1]["detail"].startswith("RuntimeError: boom") and len(acts[1]["detail"]) <= 200
    assert events.automation_depth.get() == 0


# ---- audit ----
def test_firing_is_audited(admin, owner, make_ticket):
    rule = mkrule(admin, actions=[{"type": "escalate"}])
    t = make_ticket()
    row = owner.execute(
        text(
            "SELECT detail, entity_type, entity_id FROM audit_log WHERE action='automation.rule_fired'"
        )
    ).one()
    assert (row.entity_type, row.entity_id) == ("automation_rules", rule["id"])
    assert row.detail["rule_id"] == rule["id"] and row.detail["ticket_id"] == t["id"]
    assert row.detail["actions"] == ["done"] and row.detail["event_id"]


# ---- alert events ----
def test_rmm_critical_alert_rule_escalates(env, owner, admin):  # noqa: F811
    rule = mkrule(
        admin,
        trigger="rmm_alert.opened",
        conditions=[{"field": "alert_severity", "op": "eq", "value": "CRITICAL"}],
        actions=[{"type": "escalate"}],
    )
    env.vendor.alerts = [alert("1", severity="CRITICAL")]
    poll(env.iid)
    [r] = runs(owner, rule["id"])
    assert r.matched and r.trace["conditions"][0]["actual"] == "CRITICAL"
    assert r.trace["actions"][0]["status"] in ("done", "skipped")
