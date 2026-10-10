"""Free/busy cache (REQ-04): the worker polls getSchedule into busy_blocks."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app import worker
from app.calendar_sync import refresh_busy
from app.db import new_session
from app.mail.graph import BusyItem, GraphError

NOW = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)


class FakeBusyClient:
    def __init__(self):
        self.calls: list[dict] = []
        self.busy: dict[str, list[BusyItem]] = {}
        self.error: GraphError | None = None
        self.omit: set[str] = set()

    def get_schedule(self, caller, schedules, start, end, interval_minutes=15):
        self.calls.append(
            dict(caller=caller, schedules=list(schedules), start=start, end=end, i=interval_minutes)
        )
        if self.error:
            raise self.error
        return {s.lower(): self.busy.get(s, []) for s in schedules if s not in self.omit}


@pytest.fixture
def fake():
    return FakeBusyClient()


@pytest.fixture
def enabled(owner):
    owner.execute(text("UPDATE settings SET outlook_sync_enabled = true"))


def item(hour, status="busy"):
    s = NOW + timedelta(hours=hour)
    return BusyItem(s, s + timedelta(hours=1), status)


def run(fake, now=NOW):
    with new_session() as db:
        return refresh_busy(db, fake, now=now)


def blocks(owner, user_id):
    return owner.execute(
        text("SELECT starts_at, status FROM busy_blocks WHERE user_id = :u ORDER BY starts_at"),
        {"u": user_id},
    ).all()


def status(owner, user_id):
    return owner.execute(
        text("SELECT fetched_at, last_error FROM calendar_busy_status WHERE user_id = :u"),
        {"u": user_id},
    ).one_or_none()


def test_disabled_does_nothing(login, fake):
    login("tech", "t1@example.com")
    assert run(fake) == 0
    assert fake.calls == []


def test_blocks_replace_old_ones(login, owner, fake, enabled):
    t = login("tech", "t1@example.com").user
    fake.busy["t1@example.com"] = [item(1), item(3, "tentative")]
    assert run(fake) == 1
    call = fake.calls[0]
    assert call["caller"] == "t1@example.com" and call["i"] == 15
    assert call["start"] == NOW - timedelta(days=1) and call["end"] == NOW + timedelta(days=14)
    assert [b.status for b in blocks(owner, t["id"])] == ["busy", "tentative"]
    assert status(owner, t["id"]).fetched_at == NOW

    fake.busy["t1@example.com"] = [item(5)]
    run(fake, NOW + timedelta(minutes=5))
    rows = blocks(owner, t["id"])
    assert len(rows) == 1 and rows[0].starts_at == NOW + timedelta(hours=5)
    assert status(owner, t["id"]).fetched_at == NOW + timedelta(minutes=5)


def test_user_without_email_is_skipped(login, owner, fake, enabled):
    t = login("tech", "t1@example.com").user
    owner.execute(text("UPDATE users SET email = '' WHERE id = :i"), {"i": t["id"]})
    assert run(fake) == 0
    assert fake.calls == []


def test_removed_from_tech_role_is_not_refreshed(login, owner, fake, enabled):
    t = login("tech", "t1@example.com").user
    owner.execute(text("UPDATE users SET role = 'read_only' WHERE id = :i"), {"i": t["id"]})
    assert run(fake) == 0
    assert fake.calls == []


def test_batches_of_twenty(make_user, fake, enabled):
    for i in range(25):
        make_user("tech", f"t{i:02d}@example.com")
    assert run(fake) == 25
    assert [len(c["schedules"]) for c in fake.calls] == [20, 5]
    assert [c["caller"] for c in fake.calls] == [c["schedules"][0] for c in fake.calls]
    assert fake.calls[0]["caller"] == "t00@example.com"


def test_graph_error_keeps_old_blocks_and_records_it(login, owner, fake, enabled):
    t = login("tech", "t1@example.com").user
    fake.busy["t1@example.com"] = [item(1)]
    run(fake)
    fake.error = GraphError("x" * 800, 503, True)
    assert run(fake, NOW + timedelta(minutes=5)) == 0
    assert len(blocks(owner, t["id"])) == 1
    s = status(owner, t["id"])
    assert s.fetched_at == NOW and len(s.last_error) == 500


def test_missing_user_keeps_blocks_while_others_refresh(login, owner, fake, enabled):
    a = login("tech", "a@example.com").user
    b = login("tech", "b@example.com").user
    fake.busy.update({"a@example.com": [item(1)], "b@example.com": [item(2)]})
    run(fake)
    fake.busy.update({"a@example.com": [item(7)], "b@example.com": [item(8)]})
    fake.omit = {"b@example.com"}
    assert run(fake, NOW + timedelta(minutes=5)) >= 1
    assert blocks(owner, a["id"])[0].starts_at == NOW + timedelta(hours=7)
    assert blocks(owner, b["id"])[0].starts_at == NOW + timedelta(hours=2)
    assert status(owner, b["id"]).last_error
    assert status(owner, a["id"]).last_error is None


def test_worker_throttles_to_five_minutes(login, fake, enabled, monkeypatch):
    login("tech", "t1@example.com")
    clock = [1000.0]
    monkeypatch.setattr(worker.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(worker, "_last_busy", None)
    worker.busy_job(fake)
    n = len(fake.calls)
    assert n >= 1
    clock[0] += 299
    worker.busy_job(fake)
    assert len(fake.calls) == n
    clock[0] += 2
    worker.busy_job(fake)
    assert len(fake.calls) == 2 * n
