"""Scheduled report emails: due periods, the worker job, recipient rules and the schedule routes."""

from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app import report_metrics as rm
from app import report_schedules as rs
from app import worker
from app.db import new_session, set_org_scope
from app.deps import Ctx
from app.scope import Scope

MON = date(2026, 3, 9)  # a Monday; the previous week is 2026-03-02 .. 2026-03-08


def sched(**kw):
    base = dict(frequency="weekly", weekday=0, day_of_month=None)
    return SimpleNamespace(**{**base, **kw})


@contextmanager
def system_ctx():
    db = new_session()
    try:
        set_org_scope(db, "all")
        yield Ctx(db=db, user=None, scope=Scope.all())
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def run_due(today=MON):
    with system_ctx() as ctx:
        return rs.run_due(ctx, today)


# ---- due_period ----
def test_weekly_due_period_around_the_boundaries():
    wed = sched(weekday=2)
    assert rs.due_period(wed, date(2026, 3, 9)) is None  # Monday, before Wednesday
    assert rs.due_period(wed, date(2026, 3, 10)) is None
    assert rs.due_period(wed, date(2026, 3, 11)) == (date(2026, 3, 2), date(2026, 3, 8))
    assert rs.due_period(wed, date(2026, 3, 15)) == (date(2026, 3, 2), date(2026, 3, 8))  # Sunday
    assert rs.due_period(wed, date(2026, 3, 16)) is None  # next Monday: not due again yet
    assert rs.due_period(wed, date(2026, 3, 18)) == (date(2026, 3, 9), date(2026, 3, 15))
    assert rs.due_period(sched(weekday=0), MON) == (date(2026, 3, 2), date(2026, 3, 8))
    assert rs.due_period(sched(weekday=6), date(2026, 3, 14)) is None  # Saturday, due on Sunday
    assert rs.due_period(sched(weekday=6), date(2026, 3, 15)) == (
        date(2026, 3, 2),
        date(2026, 3, 8),
    )


def test_monthly_due_period_including_day_28_and_year_ends():
    m28 = sched(frequency="monthly", weekday=None, day_of_month=28)
    assert rs.due_period(m28, date(2026, 3, 27)) is None
    assert rs.due_period(m28, date(2026, 3, 28)) == (date(2026, 2, 1), date(2026, 2, 28))
    assert rs.due_period(m28, date(2026, 3, 31)) == (date(2026, 2, 1), date(2026, 2, 28))
    assert rs.due_period(m28, date(2026, 1, 28)) == (date(2025, 12, 1), date(2025, 12, 31))
    assert rs.due_period(m28, date(2028, 3, 28)) == (date(2028, 2, 1), date(2028, 2, 29))
    first = sched(frequency="monthly", weekday=None, day_of_month=1)
    assert rs.due_period(first, date(2026, 3, 1)) == (date(2026, 2, 1), date(2026, 2, 28))


# ---- helpers ----
@pytest.fixture
def staff(login, make_user):
    login("billing", "bill1@example.com")
    return {
        "b1": make_user("billing", "bill1@example.com"),
        "b2": make_user("billing", "bill2@example.com"),
        "tech": make_user("tech", "tech1@example.com"),
    }


def body(staff, **kw):
    return {
        "name": "Weekly utilisation",
        "report": "utilisation",
        "frequency": "weekly",
        "weekday": 0,
        "recipient_user_ids": [staff["b1"]["id"], staff["b2"]["id"]],
        **kw,
    }


def create(admin, staff, **kw):
    r = admin.post("/api/reports/schedules", json=body(staff, **kw))
    assert r.status_code == 201, r.text
    return r.json()


def runs(owner, schedule_id):
    return list(
        owner.execute(
            text(
                "SELECT status, detail, recipients, email_message_id, period_start, period_end "
                "FROM report_schedule_runs WHERE schedule_id = :s ORDER BY period_start"
            ),
            {"s": schedule_id},
        )
    )


def emails(owner):
    return list(
        owner.execute(
            text("SELECT id, to_emails, subject, send_status, direction FROM email_messages"),
        )
    )


# ---- the worker job ----
def test_run_due_sends_once_per_period_with_the_csv_to_staff_only(admin, owner, staff):
    s = create(admin, staff)
    assert run_due() == {"sent": 1, "skipped": 0, "failed": 0}
    assert run_due() == {"sent": 0, "skipped": 0, "failed": 0}  # a second pass changes nothing
    assert run_due(date(2026, 3, 12)) == {"sent": 0, "skipped": 0, "failed": 0}  # same period

    (run,) = runs(owner, s["id"])
    assert run.status == "sent" and run.period_start == date(2026, 3, 2)
    assert run.period_end == date(2026, 3, 8)
    (mail,) = emails(owner)
    assert mail.id == run.email_message_id
    assert (mail.direction, mail.send_status) == ("out", "pending")
    assert sorted(mail.to_emails) == ["bill1@example.com", "bill2@example.com"]
    assert sorted(run.recipients) == sorted(mail.to_emails)
    assert mail.subject == "Weekly utilisation: 2026-03-02 to 2026-03-08"
    att = owner.execute(text("SELECT filename, content_type, data FROM outbound_attachments")).all()
    assert len(att) == 1
    assert att[0].filename == "utilisation-2026-03-02-2026-03-08.csv"
    assert att[0].content_type == "text/csv"
    assert bytes(att[0].data).decode().startswith("user,capacity_minutes,logged_minutes")

    # the next week is a new period
    assert run_due(date(2026, 3, 16))["sent"] == 1
    assert len(emails(owner)) == 2


def test_aging_schedule_attaches_the_report_as_of_the_run(admin, owner, staff):
    s = create(admin, staff, name="AR", report="aging")
    assert run_due()["sent"] == 1
    (run,) = runs(owner, s["id"])
    name = owner.execute(text("SELECT filename FROM outbound_attachments")).scalar_one()
    assert name.startswith("aging-") and run.status == "sent"


def test_recipients_who_lost_report_read_are_dropped(admin, owner, staff):
    s = create(admin, staff)
    owner.execute(text("UPDATE users SET role = 'tech' WHERE id = :i"), {"i": staff["b2"]["id"]})
    assert run_due()["sent"] == 1
    (mail,) = emails(owner)
    assert mail.to_emails == ["bill1@example.com"]
    assert runs(owner, s["id"])[0].recipients == ["bill1@example.com"]


def test_schedule_with_no_eligible_recipient_left_is_skipped(admin, owner, staff):
    s = create(admin, staff)
    owner.execute(text("UPDATE users SET role = 'tech' WHERE id = :i"), {"i": staff["b2"]["id"]})
    owner.execute(
        text("UPDATE users SET is_active = false WHERE id = :i"), {"i": staff["b1"]["id"]}
    )
    assert run_due() == {"sent": 0, "skipped": 1, "failed": 0}
    (run,) = runs(owner, s["id"])
    assert run.status == "skipped" and "report:read" in run.detail
    assert emails(owner) == []
    assert run_due() == {"sent": 0, "skipped": 0, "failed": 0}  # skipped is recorded, not retried


def test_one_failing_schedule_does_not_block_another(admin, owner, staff, monkeypatch):
    bad = create(admin, staff, name="Bad", report="sla")
    good = create(admin, staff, name="Good", report="utilisation")
    real = rm.csv_for

    def flaky(ctx, report, start, end, *a):
        if report == "sla":
            raise RuntimeError("boom")
        return real(ctx, report, start, end, *a)

    monkeypatch.setattr(rm, "csv_for", flaky)
    assert run_due() == {"sent": 1, "skipped": 0, "failed": 1}
    (failed,) = runs(owner, bad["id"])
    assert failed.status == "failed" and "boom" in failed.detail and failed.email_message_id is None
    assert runs(owner, good["id"])[0].status == "sent"
    assert len(emails(owner)) == 1  # nothing half-queued by the failed schedule
    assert run_due() == {"sent": 0, "skipped": 0, "failed": 0}


def test_monthly_schedule_on_day_28(admin, owner, staff):
    s = create(
        admin, staff, name="Monthly", frequency="monthly", weekday=None, day_of_month=28,
        report="profitability",
    )  # fmt: skip
    assert run_due(date(2026, 3, 27)) == {"sent": 0, "skipped": 0, "failed": 0}
    assert run_due(date(2026, 3, 28))["sent"] == 1
    assert run_due(date(2026, 3, 31))["sent"] == 0
    (run,) = runs(owner, s["id"])
    assert (run.period_start, run.period_end) == (date(2026, 2, 1), date(2026, 2, 28))
    assert run_due(date(2026, 4, 28))["sent"] == 1


def test_worker_report_jobs_runs_due_schedules(admin, owner, staff):
    s = create(admin, staff, weekday=0)  # Monday: due on every day of a week
    worker.report_jobs()
    worker.report_jobs()
    assert len(runs(owner, s["id"])) == 1 and len(emails(owner)) == 1


# ---- validation ----
def test_saving_a_schedule_with_a_tech_recipient_is_refused(admin, staff):
    r = admin.post(
        "/api/reports/schedules", json=body(staff, recipient_user_ids=[staff["tech"]["id"]])
    )
    assert r.status_code == 409 and "tech user" in r.json()["detail"]
    assert admin.get("/api/reports/schedules").json() == []


def test_recipient_rules(admin, owner, staff):
    path = "/api/reports/schedules"
    missing = admin.post(path, json=body(staff, recipient_user_ids=[999999]))
    assert missing.status_code == 409 and "999999" in missing.json()["detail"]
    owner.execute(
        text("UPDATE users SET is_active = false WHERE id = :i"), {"i": staff["b2"]["id"]}
    )
    inactive = admin.post(path, json=body(staff))
    assert inactive.status_code == 409 and "billing user" in inactive.json()["detail"]
    assert admin.post(path, json=body(staff, recipient_user_ids=[])).status_code == 422


def test_timing_rules(admin, staff):
    path = "/api/reports/schedules"
    assert admin.post(path, json=body(staff, weekday=None)).status_code == 409
    monthly = body(staff, frequency="monthly", weekday=None)
    assert admin.post(path, json=monthly).status_code == 409  # no day_of_month
    assert admin.post(path, json={**monthly, "day_of_month": 29}).status_code == 422
    assert admin.post(path, json={**monthly, "day_of_month": 0}).status_code == 422
    assert admin.post(path, json={**body(staff), "weekday": 7}).status_code == 422
    ok = admin.post(path, json={**monthly, "day_of_month": 28})
    assert ok.status_code == 201 and ok.json()["weekday"] is None
    # the other frequency's field is cleared
    both = admin.post(path, json={**body(staff), "day_of_month": 5})
    assert both.status_code == 201 and both.json()["day_of_month"] is None


# ---- routes ----
def test_every_route_and_its_permissions(admin, login, staff):
    s = create(admin, staff)
    sid = s["id"]
    billing = login("billing", "bill1@example.com")
    assert [x["id"] for x in billing.get("/api/reports/schedules").json()] == [sid]
    assert billing.get(f"/api/reports/schedules/{sid}/runs").json() == []
    # billing may read but not manage
    assert billing.post("/api/reports/schedules", json=body(staff)).status_code == 403
    assert billing.patch(f"/api/reports/schedules/{sid}", json={"name": "x"}).status_code == 403
    for role in ("tech", "read_only"):
        c = login(role)
        assert c.get("/api/reports/schedules").status_code == 403
        assert c.get(f"/api/reports/schedules/{sid}/runs").status_code == 403
        assert c.post("/api/reports/schedules", json=body(staff)).status_code == 403
    run_due()
    runs_ = billing.get(f"/api/reports/schedules/{sid}/runs").json()
    assert [r["status"] for r in runs_] == ["sent"] and runs_[0]["period_start"] == "2026-03-02"
    got = admin.patch(f"/api/reports/schedules/{sid}", json={"name": "Renamed", "weekday": 3})
    assert got.status_code == 200 and got.json()["name"] == "Renamed" and got.json()["weekday"] == 3


def test_unknown_ids_are_404_and_there_is_no_delete(admin):
    assert admin.patch("/api/reports/schedules/999", json={"name": "x"}).status_code == 404
    assert admin.get("/api/reports/schedules/999/runs").status_code == 404
    assert admin.delete("/api/reports/schedules/999").status_code == 405


def test_patch_rules(admin, staff):
    sid = create(admin, staff)["id"]
    url = f"/api/reports/schedules/{sid}"
    to_monthly = admin.patch(url, json={"frequency": "monthly"})
    assert to_monthly.status_code == 409  # needs a day_of_month
    ok = admin.patch(url, json={"frequency": "monthly", "day_of_month": 15})
    assert ok.json()["weekday"] is None and ok.json()["day_of_month"] == 15
    back = admin.patch(url, json={"frequency": "weekly", "weekday": 4}).json()
    assert back["day_of_month"] is None and back["weekday"] == 4
    tech = admin.patch(url, json={"recipient_user_ids": [staff["tech"]["id"]]})
    assert tech.status_code == 409
    only_b1 = admin.patch(url, json={"recipient_user_ids": [staff["b1"]["id"]]}).json()
    assert only_b1["recipient_user_ids"] == [staff["b1"]["id"]]


def test_deactivating_a_schedule_stops_the_worker(admin, owner, staff):
    s = create(admin, staff)
    off = admin.patch(f"/api/reports/schedules/{s['id']}", json={"active": False})
    assert off.status_code == 200 and off.json()["active"] is False
    assert run_due() == {"sent": 0, "skipped": 0, "failed": 0}
    assert emails(owner) == [] and runs(owner, s["id"]) == []
    # a deactivated schedule can still be saved without re-checking its recipients
    owner.execute(text("UPDATE users SET role = 'tech' WHERE id = :i"), {"i": staff["b2"]["id"]})
    assert admin.patch(f"/api/reports/schedules/{s['id']}", json={"name": "Old"}).status_code == 200
    admin.patch(f"/api/reports/schedules/{s['id']}", json={"active": True})
    assert run_due()["sent"] == 1


def test_changes_and_sends_are_audited(admin, staff):
    sid = create(admin, staff)["id"]
    admin.patch(f"/api/reports/schedules/{sid}", json={"active": False})
    items = admin.get("/api/audit", params={"action": "report_schedule.create"}).json()["items"]
    assert len(items) == 1
    items = admin.get("/api/audit", params={"action": "report_schedule.update"}).json()["items"]
    assert len(items) == 1
    admin.patch(f"/api/reports/schedules/{sid}", json={"active": True})
    run_due()
    sends = admin.get("/api/audit", params={"action": "report_schedule.send"}).json()["items"]
    assert len(sends) == 1
