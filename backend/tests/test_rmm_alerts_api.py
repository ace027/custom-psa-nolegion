"""Alert settings, the admin alert routes, the worker job and ticket asset fields."""

import pytest
from sqlalchemy import text

from app import worker
from tests.test_asset_sync import setup_ninja
from tests.test_integrations import connect
from tests.vendorfakes import HUDU, NINJA, alert, dev, run_sync, vendors  # noqa: F401


def patch(admin, iid, **cfg):
    return admin.patch(f"/api/v1/integrations/{iid}", json={"config": cfg})


@pytest.fixture
def env(admin, make_org, vendors):  # noqa: F811
    org, i, v = setup_ninja(admin, make_org, vendors, [dev("1", "PC-1", "SER-ONE-0001")])
    run_sync(i["id"])
    assert patch(admin, i["id"], alerts_enabled=True).status_code == 200
    return type("Env", (), {"org": org, "iid": i["id"], "vendor": v})


def test_valid_alert_config_is_saved(admin):
    i = connect(admin)
    cfg = {
        "alerts_enabled": True,
        "alert_min_severity": "MAJOR",
        "alert_clear_rule": "note_only",
        "alert_poll_minutes": 15,
    }
    r = patch(admin, i["id"], **cfg)
    assert r.status_code == 200 and r.json()["config"] == cfg
    assert r.json()["alerts_requested"] is False and r.json()["alerts_polled_at"] is None


@pytest.mark.parametrize(
    "cfg",
    [
        {"alerts_enabled": "yes"},
        {"alert_min_severity": "HUGE"},
        {"alert_clear_rule": "whenever"},
        {"alert_poll_minutes": 0},
        {"alert_poll_minutes": 61},
        {"alert_poll_minutes": True},
        {"alert_poll_minutes": "5"},
        {"alert_typo": 1},
        {"alerts_enable": True},
    ],
)
def test_invalid_alert_config_is_refused(admin, cfg):
    i = connect(admin)
    assert patch(admin, i["id"], **cfg).status_code == 409


def test_alert_keys_on_hudu_are_refused(admin):
    h = connect(admin, HUDU)
    r = patch(admin, h["id"], alerts_enabled=True)
    assert r.status_code == 409 and "only available for NinjaOne" in r.json()["detail"]
    bad = admin.post(
        "/api/v1/integrations",
        json={**HUDU, "config": {**HUDU["config"], "alert_clear_rule": "note_only"}},
    )
    assert bad.status_code == 409


@pytest.mark.parametrize("role", ["tech", "read_only"])
def test_non_admins_cannot_use_the_alert_routes(login, env, role):
    c = login(role)
    assert c.get(f"/api/v1/integrations/{env.iid}/alerts").status_code == 403
    assert c.post(f"/api/v1/integrations/{env.iid}/alerts/poll").status_code == 403


def test_alert_list_has_names_and_filters_by_state(admin, env):
    env.vendor.alerts = [alert("1", "disk"), alert("1", "cpu")]
    worker.alert_jobs()
    env.vendor.alerts = [alert("1", "cpu")]
    admin.post(f"/api/v1/integrations/{env.iid}/alerts/poll")
    worker.alert_jobs()
    admin.post(f"/api/v1/integrations/{env.iid}/alerts/poll")
    worker.alert_jobs()  # a clear needs two polls
    openr = admin.get(f"/api/v1/integrations/{env.iid}/alerts").json()
    assert len(openr) == 1
    a = openr[0]
    assert a["asset_name"] == "PC-1" and a["organization_name"] == env.org["name"]
    assert a["ticket_number"] and a["state"] == "open" and a["severity"] == "MAJOR"
    cleared = admin.get(
        f"/api/v1/integrations/{env.iid}/alerts", params={"state": "cleared"}
    ).json()
    assert len(cleared) == 1 and cleared[0]["resolution"] == "resolved"
    everything = admin.get(f"/api/v1/integrations/{env.iid}/alerts", params={"state": "all"}).json()
    assert len(everything) == 2 and everything[0]["id"] > everything[1]["id"]
    assert (
        len(
            admin.get(
                f"/api/v1/integrations/{env.iid}/alerts", params={"state": "all", "limit": 1}
            ).json()
        )
        == 1
    )
    assert (
        admin.get(f"/api/v1/integrations/{env.iid}/alerts", params={"limit": 0}).status_code == 422
    )
    assert admin.get("/api/v1/integrations/9999/alerts").status_code == 404


def test_poll_request_rules(admin, env):
    r = admin.post(f"/api/v1/integrations/{env.iid}/alerts/poll")
    assert r.status_code == 202 and r.json()["alerts_requested"] is True
    assert admin.post("/api/v1/integrations/9999/alerts/poll").status_code == 404
    patch(admin, env.iid, alerts_enabled=False)
    assert admin.post(f"/api/v1/integrations/{env.iid}/alerts/poll").status_code == 409
    h = connect(admin, HUDU)
    assert admin.post(f"/api/v1/integrations/{h['id']}/alerts/poll").status_code == 409


def test_worker_job_creates_the_ticket_end_to_end_and_is_idempotent(admin, env, owner):
    env.vendor.alerts = [alert("1", severity="CRITICAL")]
    worker.alert_jobs()
    assert owner.execute(text("SELECT count(*) FROM tickets WHERE source = 'rmm'")).scalar() == 1
    row = admin.get("/api/v1/integrations").json()[0]
    assert row["alerts_polled_at"] and row["alerts_last_error"] is None
    worker.alert_jobs()  # nothing due now
    assert owner.execute(text("SELECT count(*) FROM tickets")).scalar() == 1


def test_worker_job_is_a_no_op_when_nothing_is_due(admin, owner, vendors):  # noqa: F811
    connect(admin)  # alerts disabled by default
    worker.alert_jobs()
    assert owner.execute(text("SELECT count(*) FROM tickets")).scalar() == 0


def test_worker_job_records_a_vendor_failure(admin, env, owner):
    env.vendor.fail_alerts = True
    worker.alert_jobs()
    err = admin.get("/api/v1/integrations").json()[0]["alerts_last_error"]
    assert err and "HTTP 500" in err


def test_tickets_expose_the_linked_asset(admin, env):
    env.vendor.alerts = [alert("1")]
    worker.alert_jobs()
    listed = [t for t in admin.get("/api/v1/tickets").json()["items"] if t["source"] == "rmm"]
    assert len(listed) == 1 and listed[0]["asset_name"] == "PC-1"
    t = admin.get(f"/api/v1/tickets/{listed[0]['id']}").json()
    assert t["source"] == "rmm" and t["asset_id"] and t["asset_name"] == "PC-1"
    r = admin.post("/api/v1/tickets", json={"organization_id": env.org["id"], "subject": "Hi"})
    assert r.status_code == 201, r.text
    plain = r.json()
    assert plain["asset_id"] is None and plain["asset_name"] is None
    got = admin.get(f"/api/v1/tickets/{plain['id']}").json()
    assert got["asset_id"] is None and got["asset_name"] is None


def test_worker_one_failing_integration_does_not_stop_the_next(admin, env, owner, monkeypatch):
    from app import rmm_alerts

    other = connect(admin, {**NINJA, "name": "Ninja Two"})
    assert patch(admin, other["id"], alerts_enabled=True).status_code == 200
    real = rmm_alerts.poll
    seen = []

    def flaky(ctx, integration, *a, **kw):
        seen.append(integration.id)
        if len(seen) == 1:
            raise RuntimeError("boom")
        return real(ctx, integration, *a, **kw)

    monkeypatch.setattr(rmm_alerts, "poll", flaky)
    worker.alert_jobs()
    assert len(seen) == 2
    rows = admin.get("/api/v1/integrations").json()
    assert sum(1 for r in rows if r["alerts_polled_at"]) == 1
