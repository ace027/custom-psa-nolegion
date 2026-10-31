"""Rule routes: CRUD, validation, dry run, run history and permissions."""

import pytest
from sqlalchemy import text

from tests.test_automation import mkrule, queue
from tests.test_events import pri
from tests.test_webhooks import add_endpoint

URL = "/api/v1/automation/rules"


@pytest.fixture
def tech(login):
    return login("tech")


def good(admin, **kw):
    return {
        "name": "Route security",
        "trigger": "ticket.created",
        "conditions": [{"field": "queue_id", "op": "eq", "value": queue(admin, "Security")}],
        "actions": [{"type": "set_priority", "priority_id": pri(admin, "High")}],
        **kw,
    }


def count(owner, table):
    return owner.execute(text(f"SELECT count(*) FROM {table}")).scalar()


def test_crud_and_audit(admin, owner):
    r = admin.post(URL, json=good(admin))
    assert r.status_code == 201, r.text
    rule = r.json()
    assert rule["enabled"] is True and rule["fire_count"] == 0 and rule["archived_at"] is None
    assert rule["last_fired_at"] is None and rule["disabled_reason"] is None
    assert rule["position"] == 0 and rule["actions"] == good(admin)["actions"]

    r = admin.patch(
        f"{URL}/{rule['id']}", json={"name": "Renamed", "enabled": False, "position": 5}
    )
    assert r.status_code == 200, r.text
    assert (r.json()["name"], r.json()["enabled"], r.json()["position"]) == ("Renamed", False, 5)
    assert r.json()["conditions"] == rule["conditions"]  # untouched fields stay

    other = mkrule(admin, name="Other", position=1, actions=[{"type": "escalate"}])
    assert [x["id"] for x in admin.get(URL).json()] == [other["id"], rule["id"]]  # by position

    r = admin.post(f"{URL}/{rule['id']}/archive")
    assert r.status_code == 200 and r.json()["archived_at"] and r.json()["enabled"] is False
    assert [x["id"] for x in admin.get(URL).json()] == [other["id"]]
    both = admin.get(URL, params={"include_archived": True}).json()
    assert {x["id"] for x in both} == {rule["id"], other["id"]}
    assert admin.post(f"{URL}/{rule['id']}/archive").status_code == 409
    assert admin.patch(f"{URL}/{rule['id']}", json={"name": "x"}).status_code == 409

    rows = owner.execute(
        text(
            "SELECT action, before, after FROM audit_log WHERE entity_type='automation_rules' "
            "AND entity_id=:i ORDER BY id"
        ),
        {"i": rule["id"]},
    ).all()
    assert [r.action for r in rows] == [
        "automation.rule_created",
        "automation.rule_updated",
        "automation.rule_archived",
    ]
    assert rows[0].before is None and rows[0].after["name"] == "Route security"
    assert rows[1].before["name"] == "Route security" and rows[1].after["name"] == "Renamed"


def test_unknown_rule_is_404(admin):
    assert admin.patch(f"{URL}/999", json={"name": "x"}).status_code == 404
    assert admin.post(f"{URL}/999/archive").status_code == 404
    assert admin.get(f"{URL}/999/runs").status_code == 404


def test_reenabling_clears_the_disabled_reason(admin, owner):
    rule = mkrule(admin, actions=[{"type": "escalate"}])
    owner.execute(
        text("UPDATE automation_rules SET enabled=false, disabled_reason='too busy' WHERE id=:i"),
        {"i": rule["id"]},
    )
    listed = admin.get(URL).json()[0]
    assert listed["enabled"] is False and listed["disabled_reason"] == "too busy"
    r = admin.patch(f"{URL}/{rule['id']}", json={"enabled": True})
    assert r.json()["enabled"] is True and r.json()["disabled_reason"] is None


def bad_cases(admin, tech_id):
    sec, high = queue(admin, "Security"), pri(admin, "High")
    cond = lambda **kw: {"conditions": [{"field": "queue_id", "op": "eq", "value": sec, **kw}]}  # noqa: E731
    act = lambda a: {"actions": [a]}  # noqa: E731
    yield "unknown field", {"conditions": [{"field": "nope", "op": "eq", "value": 1}]}
    yield "op not allowed", cond(op="contains")
    yield "op not allowed 2", {"conditions": [{"field": "status", "op": "is_empty"}]}
    yield "wrong type", cond(value="abc")
    yield "bool is not an id", cond(value=True)
    yield "bad choice", {"conditions": [{"field": "status", "op": "eq", "value": "weird"}]}
    yield "in needs a list", cond(op="in", value=sec)
    yield "empty in", cond(op="in", value=[])
    yield "unknown queue in condition", cond(value=9999)
    yield (
        "contains on non-subject",
        {"conditions": [{"field": "source", "op": "contains", "value": "u"}]},
    )
    yield "contains empty", {"conditions": [{"field": "subject", "op": "contains", "value": ""}]}
    yield (
        "too many conditions",
        {"conditions": [{"field": "subject", "op": "eq", "value": "a"}] * 21},
    )
    yield "empty actions", {"actions": []}
    yield "unknown action", act({"type": "explode"})
    yield "extra param", act({"type": "escalate", "x": 1})
    yield "too many actions", {"actions": [{"type": "escalate"}] * 11}
    yield "assign nobody", act({"type": "assign", "user_id": 9999})
    yield "assign no id", act({"type": "assign"})
    yield "unknown queue", act({"type": "set_queue", "queue_id": 9999})
    yield "unknown priority", act({"type": "set_priority", "priority_id": 9999})
    yield "unknown endpoint", act({"type": "webhook", "endpoint_id": 9999})
    yield "create_ticket no subject", act({"type": "create_ticket", "subject": " "})
    yield "create_ticket long subject", act({"type": "create_ticket", "subject": "x" * 201})
    yield (
        "create_ticket bad queue",
        act({"type": "create_ticket", "subject": "a", "queue_id": 9999}),
    )
    yield "notify nobody", act({"type": "notify", "user_id": 9999})
    yield "bad trigger", {"trigger": "ticket.exploded"}
    yield "empty name", {"name": "  "}
    yield "long name", {"name": "n" * 101}
    yield "bad position", {"position": -1}
    yield (
        "alert severity on ticket trigger",
        {"conditions": [{"field": "alert_severity", "op": "eq", "value": "CRITICAL"}]},
    )
    yield (
        "bad severity",
        {
            "trigger": "rmm_alert.opened",
            "conditions": [{"field": "alert_severity", "op": "eq", "value": "SCARY"}],
        },
    )
    assert high


def test_every_validation_is_409(admin, make_user):
    ids = []
    for label, patch in bad_cases(admin, None):
        r = admin.post(URL, json=good(admin, **patch))
        ids.append((label, r.status_code))
    assert [x for x in ids if x[1] != 409] == []
    assert admin.get(URL).json() == []


def test_inactive_user_cannot_be_assigned_or_notified(admin, make_user):
    gone = make_user("tech", "gone@example.com", active=False)
    for kind in ("assign", "notify"):
        r = admin.post(URL, json=good(admin, actions=[{"type": kind, "user_id": gone["id"]}]))
        assert r.status_code == 409, kind
    other_admin = make_user("admin", "other-admin@example.com")
    assert (
        admin.post(
            URL, json=good(admin, actions=[{"type": "assign", "user_id": other_admin["id"]}])
        ).status_code
        == 201
    )


def test_alert_severity_on_rmm_triggers_is_fine(admin):
    r = admin.post(
        URL,
        json=good(
            admin,
            trigger="rmm_alert.opened",
            conditions=[{"field": "alert_severity", "op": "in", "value": ["MAJOR", "CRITICAL"]}],
        ),
    )
    assert r.status_code == 201, r.text
    # changing the trigger of a rule that has the condition is rejected as well
    r = admin.patch(f"{URL}/{r.json()['id']}", json={"trigger": "ticket.created"})
    assert r.status_code == 409


def test_webhook_action_accepts_an_existing_endpoint(admin):
    ep = add_endpoint(admin.user["id"])
    r = admin.post(URL, json=good(admin, actions=[{"type": "webhook", "endpoint_id": ep}]))
    assert r.status_code == 201, r.text


def test_422_on_malformed_bodies(admin):
    assert admin.post(URL, json={"name": "x"}).status_code == 422
    assert admin.post(URL, json=good(admin, conditions="nope")).status_code == 422


# ---- dry run ----
def writes(owner):
    return {
        t: count(owner, t)
        for t in ("automation_runs", "audit_log", "tickets", "ticket_notes", "webhook_deliveries")
    }


def test_dry_run_saved_and_unsaved_write_nothing(admin, owner, make_ticket):
    t = make_ticket(subject="VPN down")
    saved = mkrule(
        admin,
        conditions=[
            {"field": "subject", "op": "contains", "value": "vpn"},
            {"field": "status", "op": "eq", "value": "open"},
        ],
        actions=[{"type": "escalate"}],
    )
    before = writes(owner)
    r = admin.post(
        "/api/v1/automation/rules/test", json={"rule_id": saved["id"], "ticket_id": t["id"]}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["matched"] is False and body["actions"] == []  # status is 'new'
    assert body["conditions"] == [
        {
            "field": "subject",
            "op": "contains",
            "value": "vpn",
            "actual": "VPN down",
            "matched": True,
        },
        {"field": "status", "op": "eq", "value": "open", "actual": "new", "matched": False},
    ]
    unsaved = {
        "name": "Try",
        "trigger": "ticket.created",
        "conditions": [{"field": "status", "op": "eq", "value": "new"}],
        "actions": [
            {"type": "escalate"},
            {"type": "set_queue", "queue_id": queue(admin, "Security")},
            {"type": "assign", "user_id": admin.user["id"]},
        ],
    }
    r = admin.post("/api/v1/automation/rules/test", json={"rule": unsaved, "ticket_id": t["id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["matched"] is True and body["conditions"][0]["actual"] == "new"
    assert [(a["type"], a["status"]) for a in body["actions"]] == [
        ("escalate", "would_run"),
        ("set_queue", "would_run"),
        ("assign", "would_run"),
    ]
    assert body["actions"][0]["detail"] == "Raise priority to High"
    assert body["actions"][1]["detail"] == "Move to queue Security"
    assert body["actions"][2]["detail"] == "Assign to admin user"
    assert writes(owner) == before
    assert admin.get(f"/api/v1/tickets/{t['id']}").json()["priority_id"] == t["priority_id"]


def test_dry_run_on_the_most_urgent_ticket_would_skip(admin, make_ticket):
    t = make_ticket(priority_id=pri(admin, "Urgent"))
    r = admin.post(
        "/api/v1/automation/rules/test",
        json={
            "rule": good(admin, conditions=[], actions=[{"type": "escalate"}]),
            "ticket_id": t["id"],
        },
    )
    assert r.json()["actions"][0]["status"] == "would_skip"
    assert r.json()["actions"][0]["detail"] == "already most urgent"


def test_dry_run_errors(admin, make_ticket):
    t = make_ticket()
    post = lambda body: admin.post("/api/v1/automation/rules/test", json=body)  # noqa: E731
    rule = good(admin)
    assert post({"ticket_id": t["id"]}).status_code == 409  # neither
    assert post({"rule_id": 1, "rule": rule, "ticket_id": t["id"]}).status_code == 409  # both
    assert post({"rule_id": 999, "ticket_id": t["id"]}).status_code == 404
    assert post({"rule": rule, "ticket_id": 99999}).status_code == 404
    assert post({"rule": {**rule, "actions": []}, "ticket_id": t["id"]}).status_code == 409
    assert post({"rule": rule}).status_code == 422


# ---- runs ----
def test_runs_trace_after_a_real_event(admin, owner, make_ticket):
    rule = mkrule(
        admin,
        actions=[{"type": "escalate"}, {"type": "set_priority", "priority_id": pri(admin, "Low")}],
    )
    assert admin.get(f"{URL}/{rule['id']}/runs").json() == []
    for n in range(3):
        make_ticket(subject=f"T{n}")
    runs = admin.get(f"{URL}/{rule['id']}/runs").json()
    assert len(runs) == 3 and runs[0]["id"] > runs[-1]["id"]  # newest first
    first = runs[0]
    assert first["matched"] is True and first["event_type"] == "ticket.created"
    assert first["ticket_id"] and first["event_id"] and first["created_at"]
    assert first["trace"]["conditions"] == []
    assert [(a["type"], a["status"]) for a in first["trace"]["actions"]] == [
        ("escalate", "done"),
        ("set_priority", "done"),
    ]
    assert first["trace"]["actions"][1]["params"] == {"priority_id": pri(admin, "Low")}
    assert len(admin.get(f"{URL}/{rule['id']}/runs", params={"limit": 2}).json()) == 2
    assert admin.get(f"{URL}/{rule['id']}/runs", params={"limit": 0}).status_code == 422
    assert admin.get(f"{URL}/{rule['id']}/runs", params={"limit": 201}).status_code == 422


# ---- permissions ----
def test_tech_and_anonymous_are_refused_everywhere(admin, tech, anon, make_ticket):
    rule = mkrule(admin, actions=[{"type": "escalate"}])
    calls = [
        ("get", URL, None),
        ("post", URL, good(admin)),
        ("patch", f"{URL}/{rule['id']}", {"name": "x"}),
        ("post", f"{URL}/{rule['id']}/archive", None),
        ("post", f"{URL}/test", {"rule_id": rule["id"], "ticket_id": 1}),
        ("get", f"{URL}/{rule['id']}/runs", None),
    ]
    for method, url, body in calls:
        kw = {"json": body} if body is not None else {}
        assert getattr(tech, method)(url, **kw).status_code == 403, (method, url)
        assert getattr(anon, method)(url, **kw).status_code == 401, (method, url)
    assert admin.get(URL).json()[0]["name"] == "Rule"
