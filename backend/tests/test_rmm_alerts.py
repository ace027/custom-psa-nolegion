"""The alert poller: one ticket per open condition, repeats bump a counter, clears resolve or note."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app import db as dbmod
from app import rmm_alerts
from app import ticket_services as tsvc
from app.deps import Ctx
from app.integrations.base import VendorError
from app.models import Integration
from app.scope import Scope
from tests.test_asset_sync import setup_ninja
from tests.vendorfakes import alert, dev, run_sync, vendors  # noqa: F401


def poll(iid, now=None, adapter=None):
    with dbmod.new_session() as db:
        dbmod.set_org_scope(db, "all")
        ctx = Ctx(db=db, user=None, scope=Scope.all())
        res = rmm_alerts.poll(ctx, db.get(Integration, iid), adapter=adapter, now=now)
        db.commit()
        return res


def configure(admin, iid, **cfg):
    r = admin.patch(f"/api/integrations/{iid}", json={"config": {"alerts_enabled": True, **cfg}})
    assert r.status_code == 200, r.text


@pytest.fixture
def env(admin, make_org, vendors):  # noqa: F811
    org, i, v = setup_ninja(
        admin,
        make_org,
        vendors,
        [dev("1", "PC-1", "SER-ONE-0001"), dev("2", "PC-2", "SER-TWO-0002")],
    )
    run_sync(i["id"])
    configure(admin, i["id"])
    return type("Env", (), {"org": org, "iid": i["id"], "vendor": v})


def tickets(owner):
    return owner.execute(
        text("SELECT id, number, source, asset_id, status, priority_id FROM tickets ORDER BY id")
    ).all()


def alert_rows(owner):
    return owner.execute(
        text(
            "SELECT state, occurrences, external_id, resolution, ticket_id "
            "FROM rmm_alerts ORDER BY id"
        )
    ).all()


def notes(owner):
    return [r[0] for r in owner.execute(text("SELECT body FROM ticket_notes ORDER BY id"))]


def prio(owner, name):
    return owner.execute(text("SELECT id FROM priorities WHERE name = :n"), {"n": name}).scalar()


def test_first_poll_creates_one_linked_ticket_by_severity(env, owner):
    env.vendor.alerts = [
        alert("1", "disk", severity="CRITICAL"),
        alert("2", "cpu", severity="MAJOR"),
    ]
    res = poll(env.iid)
    assert res.created == 2 and res.error is None
    rows = tickets(owner)
    assert len(rows) == 2 and all(r.source == "rmm" and r.asset_id for r in rows)
    assert {r.priority_id for r in rows} == {prio(owner, "Urgent"), prio(owner, "High")}
    assert owner.execute(text("SELECT subject FROM tickets ORDER BY id")).scalars().first() == (
        "[RMM] PC-1: Disk low"
    )


def test_moderate_alert_gets_the_default_priority(env, owner):
    env.vendor.alerts = [alert("1", severity="MODERATE")]
    poll(env.iid)
    assert tickets(owner)[0].priority_id == prio(owner, "Normal")


def test_identical_second_poll_creates_nothing(env, owner):
    env.vendor.alerts = [alert("1")]
    poll(env.iid)
    res = poll(env.iid)
    assert (res.created, res.repeated) == (0, 0)
    assert len(tickets(owner)) == 1 and alert_rows(owner)[0].occurrences == 1


def test_new_uid_for_same_condition_bumps_occurrences(env, owner):
    env.vendor.alerts = [alert("1", uid="u1")]
    poll(env.iid)
    env.vendor.alerts = [alert("1", uid="u2")]
    res = poll(env.iid)
    assert res.repeated == 1 and res.created == 0
    (row,) = alert_rows(owner)
    assert row.occurrences == 2 and row.external_id == "u2" and len(tickets(owner)) == 1


def test_two_conditions_on_one_device_make_two_tickets(env, owner):
    env.vendor.alerts = [alert("1", "disk"), alert("1", "cpu")]
    assert poll(env.iid).created == 2
    assert len(tickets(owner)) == 2


def test_duplicate_condition_in_one_response_keeps_the_newest(env, owner):
    old, new = alert("1", uid="old"), alert("1", uid="new")
    old.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    new.created_at = datetime(2026, 2, 1, tzinfo=UTC)
    env.vendor.alerts = [new, old]
    assert poll(env.iid).created == 1
    assert alert_rows(owner)[0].external_id == "new"


def test_below_minimum_severity_is_skipped_and_never_stored(env, owner):
    env.vendor.alerts = [alert("1", severity="MINOR")]
    res = poll(env.iid)
    assert res.skipped_severity == 1 and res.created == 0
    assert alert_rows(owner) == [] and tickets(owner) == []


def test_unmapped_device_is_skipped(env, owner):
    env.vendor.alerts = [alert("999")]
    res = poll(env.iid)
    assert res.skipped_unmapped == 1 and tickets(owner) == [] and alert_rows(owner) == []


def test_a_single_priority_serves_critical_and_major(env, owner):
    owner.execute(text("UPDATE priorities SET archived_at = now() WHERE name <> 'Normal'"))
    env.vendor.alerts = [alert("1", "a", severity="CRITICAL"), alert("2", "b", severity="MAJOR")]
    poll(env.iid)
    assert {r.priority_id for r in tickets(owner)} == {prio(owner, "Normal")}


def test_clear_with_untouched_ticket_resolves_with_a_note(env, owner):
    env.vendor.alerts = [alert("1")]
    poll(env.iid)
    env.vendor.alerts = []
    res = poll(env.iid)
    assert (res.cleared, res.resolved) == (1, 1)
    assert tickets(owner)[0].status == "resolved"
    assert "resolved automatically" in notes(owner)[0]
    row = alert_rows(owner)[0]
    assert (row.state, row.resolution) == ("cleared", "resolved")


def test_clear_after_a_technician_note_leaves_the_ticket_open(env, owner, admin):
    env.vendor.alerts = [alert("1")]
    poll(env.iid)
    tid = tickets(owner)[0].id
    assert admin.post(f"/api/tickets/{tid}/notes", json={"body": "looking"}).status_code == 201
    env.vendor.alerts = []
    res = poll(env.iid)
    assert (res.noted, res.resolved) == (1, 0)
    assert tickets(owner)[0].status != "resolved"
    assert "a technician has worked this ticket" in notes(owner)[-1]
    assert alert_rows(owner)[0].resolution == "noted"


def test_clear_after_assignment_leaves_the_ticket_open(env, owner, admin):
    env.vendor.alerts = [alert("1")]
    poll(env.iid)
    tid = tickets(owner)[0].id
    admin.patch(f"/api/tickets/{tid}", json={"assignee_id": admin.user["id"]})
    env.vendor.alerts = []
    assert poll(env.iid).noted == 1
    assert tickets(owner)[0].status == "open"


def test_note_only_rule_never_resolves(env, owner, admin):
    configure(admin, env.iid, alert_clear_rule="note_only")
    env.vendor.alerts = [alert("1")]
    poll(env.iid)
    env.vendor.alerts = []
    assert poll(env.iid).noted == 1
    assert tickets(owner)[0].status == "new" and "ticket left open" in notes(owner)[0]


def test_always_resolve_rule_resolves_a_worked_ticket(env, owner, admin):
    configure(admin, env.iid, alert_clear_rule="always_resolve")
    env.vendor.alerts = [alert("1")]
    poll(env.iid)
    tid = tickets(owner)[0].id
    admin.post(f"/api/tickets/{tid}/notes", json={"body": "looking"})
    env.vendor.alerts = []
    assert poll(env.iid).resolved == 1
    assert tickets(owner)[0].status == "resolved"


def test_clear_when_ticket_already_resolved_does_nothing_to_it(env, owner, admin):
    env.vendor.alerts = [alert("1")]
    poll(env.iid)
    tid = tickets(owner)[0].id
    admin.patch(f"/api/tickets/{tid}", json={"status": "resolved"})
    env.vendor.alerts = []
    res = poll(env.iid)
    assert res.cleared == 1 and res.resolved == 0 and res.noted == 0
    assert notes(owner) == [] and alert_rows(owner)[0].resolution == "none"


def test_condition_firing_again_after_clear_opens_a_related_ticket(env, owner):
    env.vendor.alerts = [alert("1", uid="u1")]
    poll(env.iid)
    env.vendor.alerts = []
    poll(env.iid)
    env.vendor.alerts = [alert("1", uid="u2")]
    assert poll(env.iid).created == 1
    old, new = tickets(owner)
    link = owner.execute(
        text("SELECT source_ticket_id, target_ticket_id, kind FROM ticket_links")
    ).one()
    assert (link.source_ticket_id, link.target_ticket_id, link.kind) == (new.id, old.id, "related")


def test_new_uid_after_tech_resolved_the_ticket_supersedes(env, owner, admin):
    env.vendor.alerts = [alert("1", uid="u1")]
    poll(env.iid)
    tid = tickets(owner)[0].id
    admin.patch(f"/api/tickets/{tid}", json={"status": "resolved"})
    env.vendor.alerts = [alert("1", uid="u2")]
    res = poll(env.iid)
    assert res.created == 1 and res.repeated == 0
    first, second = alert_rows(owner)
    assert (first.state, first.resolution) == ("cleared", "superseded")
    assert second.state == "open" and second.ticket_id != first.ticket_id
    assert owner.execute(text("SELECT count(*) FROM ticket_links")).scalar() == 1


def test_vendor_failure_changes_nothing_but_the_error(env, owner):
    env.vendor.alerts = [alert("1")]
    poll(env.iid)
    env.vendor.fail_alerts = True
    before = (tickets(owner), alert_rows(owner))
    res = poll(env.iid)
    assert res.error and "HTTP 500" in res.error
    assert (tickets(owner), alert_rows(owner)) == before
    row = owner.execute(text("SELECT alerts_last_error, alerts_polled_at FROM integrations")).one()
    assert "HTTP 500" in row.alerts_last_error and row.alerts_polled_at is not None
    env.vendor.fail_alerts = False
    poll(env.iid)
    assert owner.execute(text("SELECT alerts_last_error FROM integrations")).scalar() is None


def test_adapter_without_list_alerts_is_a_failed_poll(env, owner):
    res = poll(env.iid, adapter=object())
    assert res.error


def test_one_failing_alert_does_not_stop_the_others(env, owner, monkeypatch):
    real = tsvc.create_ticket
    calls = {"n": 0}

    def flaky(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise VendorError("boom")
        return real(*a, **kw)

    monkeypatch.setattr(tsvc, "create_ticket", flaky)
    env.vendor.alerts = [alert("1", "a"), alert("2", "b")]
    res = poll(env.iid)
    assert (res.failed, res.created) == (1, 1)
    assert len(tickets(owner)) == 1 and len(alert_rows(owner)) == 1


def test_due_respects_enabled_minutes_and_requests(env, admin):
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)

    def due_ids():
        with dbmod.new_session() as db:
            dbmod.set_org_scope(db, "all")
            return [i.id for i in rmm_alerts.due(Ctx(db=db, user=None, scope=Scope.all()), now)]

    assert due_ids() == [env.iid]  # never polled
    poll(env.iid, now=now)
    assert due_ids() == []
    poll_at = now + timedelta(minutes=5)
    with dbmod.new_session() as db:
        dbmod.set_org_scope(db, "all")
        assert rmm_alerts.due(Ctx(db=db, user=None, scope=Scope.all()), poll_at)
    assert admin.post(f"/api/integrations/{env.iid}/alerts/poll").status_code == 202
    assert due_ids() == [env.iid]  # asked to poll now
    admin.patch(f"/api/integrations/{env.iid}", json={"config": {"alerts_enabled": False}})
    assert due_ids() == []
