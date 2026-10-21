"""Automation and API schema guards (migration 0028): staff-internal tables without RLS, runtime
grants without DELETE, CHECKs, uniqueness and the 'rule' ticket source."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

COLUMNS = {
    "api_keys": {
        "id", "name", "prefix", "key_hash", "user_id", "permissions", "expires_at",
        "revoked_at", "revoked_by_id", "last_used_at", "created_at",
    },
    "webhook_endpoints": {
        "id", "name", "kind", "url", "secret", "events", "enabled", "consecutive_failures",
        "last_success_at", "last_failure_at", "created_by_id", "created_at", "updated_at",
    },
    "webhook_deliveries": {
        "id", "endpoint_id", "event_id", "event_type", "payload", "status", "attempts",
        "next_attempt_at", "last_status_code", "last_error", "delivered_at", "created_at",
    },
    "automation_rules": {
        "id", "name", "enabled", "trigger", "conditions", "actions", "position", "archived_at",
        "disabled_reason", "fire_count", "last_fired_at", "created_by_id", "created_at",
        "updated_at",
    },
    "automation_runs": {
        "id", "rule_id", "event_id", "event_type", "ticket_id", "matched", "dry_run", "trace",
        "created_at",
    },
}  # fmt: skip


def one(conn, sql, **params):
    return conn.execute(text(sql), params).scalar_one()


def add_endpoint(conn, user, **extra):
    cols = {
        "name": "Hook",
        "kind": "generic",
        "url": "https://example.test/h",
        "secret": "enc",
        "events": ["ticket.created"],
        "created_by_id": user,
        **extra,
    }
    names = ", ".join(cols)
    values = ", ".join(f":{c}" for c in cols)
    return one(
        conn, f"INSERT INTO webhook_endpoints ({names}) VALUES ({values}) RETURNING id", **cols
    )


def add_delivery(conn, endpoint, event_id=None, **extra):
    cols = {
        "endpoint_id": endpoint,
        "event_id": event_id or str(uuid.uuid4()),
        "event_type": "ticket.created",
        "payload": "{}",
        **extra,
    }
    names = ", ".join(cols)
    values = ", ".join(f":{c}" for c in cols)
    conn.execute(text(f"INSERT INTO webhook_deliveries ({names}) VALUES ({values})"), cols)


def add_rule(conn, user):
    return one(
        conn,
        "INSERT INTO automation_rules (name, trigger, created_by_id) "
        "VALUES ('R', 'ticket.created', :u) RETURNING id",
        u=user,
    )


def add_run(conn, rule, event_id, dry_run):
    conn.execute(
        text(
            "INSERT INTO automation_runs (rule_id, event_id, event_type, matched, dry_run) "
            "VALUES (:r, :e, 'ticket.created', true, :d)"
        ),
        {"r": rule, "e": event_id, "d": dry_run},
    )


@pytest.fixture
def staff_user(owner):
    return one(
        owner,
        "INSERT INTO users (email, display_name, role) "
        "VALUES ('auto@example.test', 'Auto', 'admin') RETURNING id",
    )


@pytest.mark.parametrize("table", COLUMNS)
def test_columns(owner, table):
    rows = owner.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
        {"t": table},
    )
    assert {r[0] for r in rows} == COLUMNS[table]


@pytest.mark.parametrize("table", COLUMNS)
def test_no_rls_and_grants(owner, table):
    assert one(owner, "SELECT relrowsecurity FROM pg_class WHERE relname = :t", t=table) is False
    for p in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        has = one(owner, "SELECT has_table_privilege('psa_app', :t, :p)", t=table, p=p)
        assert has == (p != "DELETE"), (table, p)


def test_endpoint_and_delivery_checks(owner, staff_user):
    with pytest.raises(IntegrityError, match="ck_webhook_endpoints_kind"):
        add_endpoint(owner, staff_user, kind="slack")
    with pytest.raises(IntegrityError, match="ck_webhook_endpoints_consecutive_failures"):
        add_endpoint(owner, staff_user, consecutive_failures=-1)
    ep = add_endpoint(owner, staff_user, kind="teams")
    with pytest.raises(IntegrityError, match="ck_webhook_deliveries_status"):
        add_delivery(owner, ep, status="weird")
    with pytest.raises(IntegrityError, match="ck_webhook_deliveries_attempts"):
        add_delivery(owner, ep, attempts=-1)


def test_duplicate_delivery_rejected(owner, staff_user):
    ep = add_endpoint(owner, staff_user)
    event = str(uuid.uuid4())
    add_delivery(owner, ep, event)
    with pytest.raises(IntegrityError, match="uq_webhook_deliveries_event"):
        add_delivery(owner, ep, event)
    add_delivery(owner, add_endpoint(owner, staff_user, name="Other"), event)


def test_run_uniqueness_ignores_dry_runs(owner, staff_user):
    rule, event = add_rule(owner, staff_user), str(uuid.uuid4())
    add_run(owner, rule, event, False)
    with pytest.raises(IntegrityError, match="uq_automation_runs_event"):
        add_run(owner, rule, event, False)
    add_run(owner, rule, event, True)
    add_run(owner, rule, event, True)


def test_ticket_source_rule_and_breach_column(owner, make_org_with_ticket):
    _, ticket = make_org_with_ticket("Org A")
    row = owner.execute(
        text("SELECT sla_breached_event_at FROM tickets WHERE id = :t"), {"t": ticket["id"]}
    ).scalar_one()
    assert row is None
    owner.execute(text("UPDATE tickets SET source = 'rule' WHERE id = :t"), {"t": ticket["id"]})
    with pytest.raises(IntegrityError, match="ck_tickets_source"):
        owner.execute(
            text("UPDATE tickets SET source = 'bogus' WHERE id = :t"), {"t": ticket["id"]}
        )
