"""Outlook push (REQ-04): the outbox is written by the API and pushed by the worker job."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.calendar_sync import push_pending
from app.db import new_session
from app.mail.graph import GraphError, event_payload

MON = datetime(2030, 1, 7, tzinfo=UTC)
NOW = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)


def at(hour: int, day: int = 0) -> str:
    return (MON + timedelta(days=day, hours=hour)).isoformat()


class FakeCalendarClient:
    """In-memory Outlook: events per mailbox, idempotent creates, one-shot failure injection."""

    def __init__(self):
        self.events: dict[tuple[str, str], dict] = {}
        self.by_txn: dict[str, str] = {}
        self.calls: list[tuple] = []
        self.fail: list[tuple[str, GraphError]] = []  # (method, error), consumed in order
        self.on_create = None
        self.lose_response = False  # create succeeds in Outlook, the caller sees a timeout

    def _maybe_fail(self, method):
        for i, (m, err) in enumerate(self.fail):
            if m == method:
                del self.fail[i]
                raise err

    def create_event(self, user, event, transaction_id):
        self.calls.append(("create", user, transaction_id))
        self._maybe_fail("create")
        if self.on_create:
            self.on_create()
        if transaction_id not in self.by_txn:
            self.by_txn[transaction_id] = f"evt-{len(self.by_txn) + 1}"
            self.events[(user, self.by_txn[transaction_id])] = event
        if self.lose_response:
            self.lose_response = False
            raise GraphError("timeout", None, True)
        return self.by_txn[transaction_id]

    def update_event(self, user, event_id, event):
        self.calls.append(("update", user, event_id))
        self._maybe_fail("update")
        if (user, event_id) not in self.events:
            raise GraphError("not found", 404, False)
        self.events[(user, event_id)] = event

    def delete_event(self, user, event_id):
        self.calls.append(("delete", user, event_id))
        self._maybe_fail("delete")
        self.events.pop((user, event_id), None)  # like GraphClient: a 404 is fine


@pytest.fixture
def fake():
    return FakeCalendarClient()


@pytest.fixture
def enabled(owner):
    owner.execute(text("UPDATE settings SET outlook_sync_enabled = true"))


@pytest.fixture
def tech(login):
    return login("tech", "tech1@example.com")


@pytest.fixture
def tech2(login):
    return login("tech", "tech2@example.com")


def book(admin, ticket_id, tech, start=None, end=None):
    r = admin.post(
        "/api/appointments",
        json={
            "ticket_id": ticket_id,
            "tech_id": tech.user["id"],
            "starts_at": start or at(15),
            "ends_at": end or at(16),
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def sync(owner, appt):
    return owner.execute(
        text(
            "SELECT state, desired_version, synced_version, generation, attempts, last_error, "
            "graph_event_id, synced_tech_id, next_attempt_at FROM appointment_sync "
            "WHERE appointment_id = :i"
        ),
        {"i": appt},
    ).one()


def push(fake, now=NOW, **kw):
    with new_session() as db:
        return push_pending(db, fake, now=now, **kw)


@pytest.fixture
def appt(admin, make_ticket, tech):
    return book(admin, make_ticket()["id"], tech)


def test_api_writes_leave_a_pending_row(admin, owner, make_ticket, tech, tech2):
    a = book(admin, make_ticket()["id"], tech)
    assert tuple(sync(owner, a))[:3] == ("pending", 1, 0)
    admin.patch(f"/api/appointments/{a}", json={"notes": "just a note"})
    assert sync(owner, a).desired_version == 1  # notes are not pushed
    admin.patch(f"/api/appointments/{a}", json={"ends_at": at(17)})
    assert sync(owner, a).desired_version == 2
    admin.patch(f"/api/appointments/{a}", json={"tech_id": tech2.user["id"]})
    assert sync(owner, a).desired_version == 3
    admin.post(f"/api/appointments/{a}/cancel", json={})
    assert tuple(sync(owner, a))[:3] == ("pending", 4, 0)


def test_disabled_setting_does_nothing(owner, fake, appt):
    assert push(fake) == 0
    assert fake.calls == []
    assert sync(owner, appt).state == "pending"


def test_create_pushes_the_approved_payload(owner, fake, enabled, appt, make_user):
    assert push(fake) == 1
    row = sync(owner, appt)
    ticket_id = owner.execute(
        text("SELECT ticket_id FROM appointments WHERE id = :i"), {"i": appt}
    ).scalar_one()
    txn = f"psa-appt-{appt}-{row.synced_tech_id}-1"
    assert fake.calls == [("create", "tech1@example.com", txn)]
    expected = event_payload(ticket_id, MON + timedelta(hours=15), MON + timedelta(hours=16), "")
    sent = fake.events[("tech1@example.com", row.graph_event_id)]
    assert sent["start"] == expected["start"] and sent["end"] == expected["end"]
    assert sent["subject"] == f"PSA #{ticket_id} appointment" and sent["sensitivity"] == "private"
    assert (row.state, row.synced_version, row.attempts, row.last_error) == ("synced", 1, 0, None)
    assert push(fake) == 0  # nothing left to do


def test_retried_create_makes_no_duplicate(owner, fake, enabled, appt):
    fake.lose_response = True
    push(fake)
    row = sync(owner, appt)
    assert row.state == "pending" and row.attempts == 1 and row.graph_event_id is None
    assert push(fake, NOW + timedelta(minutes=3)) == 1
    assert len(fake.events) == 1
    assert sync(owner, appt).state == "synced"


def test_move_updates_the_same_event(admin, owner, fake, enabled, appt):
    push(fake)
    event_id = sync(owner, appt).graph_event_id
    admin.patch(f"/api/appointments/{appt}", json={"starts_at": at(14), "ends_at": at(15)})
    push(fake)
    assert fake.calls[-1] == ("update", "tech1@example.com", event_id)
    assert len(fake.events) == 1
    row = sync(owner, appt)
    assert (row.state, row.synced_version, row.desired_version) == ("synced", 2, 2)


def test_reassign_deletes_old_and_creates_new(admin, owner, fake, enabled, appt, tech2):
    push(fake)
    old_id = sync(owner, appt).graph_event_id
    admin.patch(f"/api/appointments/{appt}", json={"tech_id": tech2.user["id"]})
    push(fake)
    assert fake.calls[-2] == ("delete", "tech1@example.com", old_id)
    assert fake.calls[-1][:2] == ("create", "tech2@example.com")
    assert [k[0] for k in fake.events] == ["tech2@example.com"]
    row = sync(owner, appt)
    assert (row.state, row.generation, row.synced_tech_id) == ("synced", 2, tech2.user["id"])


def test_reassign_with_failing_delete_waits_without_creating(
    admin, owner, fake, enabled, appt, tech2
):
    push(fake)
    admin.patch(f"/api/appointments/{appt}", json={"tech_id": tech2.user["id"]})
    fake.fail.append(("delete", GraphError("busy", 503, True)))
    push(fake)
    assert [c[0] for c in fake.calls] == ["create", "delete"]
    row = sync(owner, appt)
    assert row.state == "pending" and row.attempts == 1
    assert row.next_attempt_at == NOW + timedelta(minutes=2)
    assert row.synced_tech_id is not None and row.graph_event_id is not None
    push(fake, NOW + timedelta(minutes=2))
    assert [k[0] for k in fake.events] == ["tech2@example.com"]
    assert sync(owner, appt).state == "synced"


def test_cancel_deletes_and_a_missing_event_is_fine(admin, owner, fake, enabled, appt):
    push(fake)
    event_id = sync(owner, appt).graph_event_id
    fake.events.clear()  # the event was already removed by hand
    admin.post(f"/api/appointments/{appt}/cancel", json={})
    push(fake)
    assert fake.calls[-1] == ("delete", "tech1@example.com", event_id)
    row = sync(owner, appt)
    assert (row.state, row.graph_event_id, row.synced_tech_id) == ("synced", None, None)


def test_cancel_before_the_first_push_has_nothing_to_delete(admin, owner, fake, enabled, appt):
    admin.post(f"/api/appointments/{appt}/cancel", json={})
    assert push(fake) == 1
    assert fake.calls == []
    assert sync(owner, appt).state == "synced"


def test_404_on_update_recreates(owner, fake, enabled, admin, appt):
    push(fake)
    fake.events.clear()  # deleted in Outlook by hand
    admin.patch(f"/api/appointments/{appt}", json={"ends_at": at(17)})
    push(fake)
    assert [c[0] for c in fake.calls] == ["create", "update", "create"]
    assert len(fake.events) == 1
    row = sync(owner, appt)
    assert (row.state, row.generation) == ("synced", 2)
    assert fake.calls[-1][2].endswith("-2")


def test_transient_errors_back_off_then_fail(owner, fake, enabled, appt):
    now = NOW
    for attempt in range(1, 7):
        fake.fail.append(("create", GraphError("down", 503, True)))
        assert push(fake, now) == 1
        row = sync(owner, appt)
        assert row.attempts == attempt and "down" in row.last_error
        if attempt == 1:
            assert row.next_attempt_at == now + timedelta(minutes=2)
        if attempt < 6:
            assert row.state == "pending"
        now += timedelta(hours=2)
    assert row.state == "failed"
    assert push(fake, now) == 0  # failed rows are left alone


def test_a_permanent_error_fails_at_once(owner, fake, enabled, appt):
    fake.fail.append(("create", GraphError("Forbidden for this mailbox", 403, False)))
    push(fake)
    row = sync(owner, appt)
    assert row.state == "failed" and "Forbidden" in row.last_error and row.attempts == 1


def test_tech_without_an_email_fails(owner, fake, enabled, appt):
    owner.execute(text("UPDATE users SET email = '' WHERE email = 'tech1@example.com'"))
    push(fake)
    row = sync(owner, appt)
    assert (row.state, row.last_error) == ("failed", "Tech has no email address")
    assert fake.calls == []


def test_a_write_during_a_push_leaves_the_row_pending(admin, owner, fake, enabled, appt):
    fake.on_create = lambda: admin.patch(
        f"/api/appointments/{appt}", json={"starts_at": at(14), "ends_at": at(15)}
    )
    push(fake)
    row = sync(owner, appt)
    assert (row.state, row.synced_version, row.desired_version) == ("pending", 1, 2)
    assert row.graph_event_id is not None
    fake.on_create = None
    assert push(fake, datetime.now(UTC) + timedelta(minutes=1)) == 1
    assert fake.calls[-1][0] == "update"
    row = sync(owner, appt)
    assert (row.state, row.synced_version) == ("synced", 2)


def test_long_ended_appointments_are_skipped(owner, fake, enabled, make_org_with_ticket, tech):
    org, ticket = make_org_with_ticket("Org A")
    appt = owner.execute(
        text(
            "INSERT INTO appointments (organization_id, ticket_id, tech_id, starts_at, ends_at) "
            "VALUES (:o, :t, :u, '2029-12-01 09:00+00', '2029-12-01 10:00+00') RETURNING id"
        ),
        {"o": org["id"], "t": ticket["id"], "u": tech.user["id"]},
    ).scalar_one()
    owner.execute(
        text("INSERT INTO appointment_sync (appointment_id, organization_id) VALUES (:i, :o)"),
        {"i": appt, "o": org["id"]},
    )
    push(fake)
    assert fake.calls == []
    assert sync(owner, appt).state == "skipped"


def test_rows_of_two_orgs_are_both_processed(
    admin, owner, fake, enabled, make_org_with_ticket, tech
):
    (_, t1), (_, t2) = make_org_with_ticket("Org A"), make_org_with_ticket("Org B")
    a1, a2 = book(admin, t1["id"], tech), book(admin, t2["id"], tech, at(17), at(18))
    assert push(fake) == 2
    assert sync(owner, a1).state == sync(owner, a2).state == "synced"
    assert len(fake.events) == 2


def test_batch_limits_the_rows_processed(admin, owner, fake, enabled, make_ticket, tech):
    ids = [book(admin, make_ticket()["id"], tech, at(8 + i), at(9 + i)) for i in range(3)]
    assert push(fake, batch=2) == 2
    assert push(fake) == 1
    assert {sync(owner, i).state for i in ids} == {"synced"}
