"""Pure on-call math (app.oncall): rotation order, overrides, boundaries and DST."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.oncall import shifts, who_is_on

CHI = ZoneInfo("America/Chicago")
T0 = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass
class Rot:
    handoff_weekday: int = 0
    handoff_time: time = time(9, 0)
    anchor_date: date = date(2026, 2, 2)  # a Monday
    active: bool = True


@dataclass
class Mem:
    user_id: int
    position: int


@dataclass
class Ovr:
    user_id: int
    starts_at: datetime
    ends_at: datetime
    created_at: datetime = T0


MEMBERS = [Mem(10, 0), Mem(20, 1), Mem(30, 2)]


def local(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=CHI)


def on(at, rot=None, members=MEMBERS, overrides=()):
    return who_is_on(rot or Rot(), members, list(overrides), at, CHI)


def test_rotation_order_and_wraparound():
    users = [on(local(2026, 2, 2, 9) + timedelta(weeks=w))[0] for w in range(7)]
    assert users == [10, 20, 30, 10, 20, 30, 10]


def test_members_are_ordered_by_position_not_list_order():
    shuffled = [Mem(30, 2), Mem(10, 0), Mem(20, 1)]
    assert on(local(2026, 2, 3), members=shuffled)[0] == 10


def test_before_anchor_inactive_and_no_members_are_none():
    assert on(local(2026, 2, 2, 8, 59)) is None
    assert on(local(2026, 2, 3), rot=Rot(active=False)) is None
    assert on(local(2026, 2, 3), members=[]) is None


def test_handoff_boundary_goes_to_next_member():
    assert on(local(2026, 2, 9, 8, 59))[0] == 10
    assert on(local(2026, 2, 9, 9, 0))[0] == 20
    uid, source, until = on(local(2026, 2, 3))
    assert (uid, source) == (10, "rotation")
    assert until == local(2026, 2, 9, 9).astimezone(UTC)


def test_override_wins_and_latest_override_wins_on_overlap():
    a = Ovr(99, local(2026, 2, 3, 12), local(2026, 2, 3, 18), created_at=T0)
    b = Ovr(98, local(2026, 2, 3, 14), local(2026, 2, 3, 16), created_at=T0 + timedelta(days=1))
    assert on(local(2026, 2, 3, 11), overrides=[a, b])[0] == 10
    uid, source, until = on(local(2026, 2, 3, 12, 30), overrides=[a, b])
    assert (uid, source) == (99, "override")
    assert until == b.starts_at.astimezone(UTC)  # a later override starts first
    assert on(local(2026, 2, 3, 15), overrides=[a, b])[0] == 98
    assert on(local(2026, 2, 3, 17), overrides=[a, b])[0] == 99
    # ends_at is exclusive
    assert on(local(2026, 2, 3, 18), overrides=[a, b])[0] == 10


def test_rotation_until_stops_at_next_override_start():
    o = Ovr(99, local(2026, 2, 5, 12), local(2026, 2, 5, 13))
    assert on(local(2026, 2, 3), overrides=[o])[2] == o.starts_at.astimezone(UTC)


def test_spring_forward_keeps_local_handoff_time():
    # US DST starts Sunday 2026-03-08. Monday 09:00 is 15:00Z before it and 14:00Z after.
    before = on(local(2026, 3, 2, 10))
    assert before[2] == datetime(2026, 3, 9, 14, 0, tzinfo=UTC)
    assert on(datetime(2026, 3, 9, 13, 59, tzinfo=UTC))[0] == before[0]
    assert on(datetime(2026, 3, 9, 14, 0, tzinfo=UTC))[0] != before[0]


def test_fall_back_keeps_local_handoff_time():
    # US DST ends Sunday 2026-11-01. Monday 09:00 is 14:00Z before it and 15:00Z after.
    wk = on(local(2026, 10, 26, 10))
    assert wk[2] == datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
    assert on(datetime(2026, 11, 2, 14, 59, tzinfo=UTC))[0] == wk[0]
    assert on(datetime(2026, 11, 2, 15, 0, tzinfo=UTC))[0] != wk[0]


def test_handoff_inside_the_spring_forward_gap_is_deterministic():
    rot = Rot(handoff_weekday=6, handoff_time=time(2, 30), anchor_date=date(2026, 3, 1))
    first = on(datetime(2026, 3, 5, tzinfo=UTC), rot=rot)
    assert first[0] == 10
    assert first[2] > datetime(2026, 3, 8, 7, tzinfo=UTC)  # 02:30 local does not exist that day
    assert on(first[2], rot=rot)[0] == 20


def assert_tiles(result, start, end):
    assert result[0].starts_at == start.astimezone(UTC)
    assert result[-1].ends_at == end.astimezone(UTC)
    for prev, nxt in zip(result, result[1:], strict=False):
        assert prev.ends_at == nxt.starts_at  # no gaps, no overlaps
    assert all(s.starts_at < s.ends_at for s in result)


def test_shifts_cover_the_window_across_dst():
    start, end = local(2026, 2, 20), local(2026, 3, 30)
    result = shifts(Rot(), MEMBERS, [], start, end, CHI)
    assert_tiles(result, start, end)
    assert [s.user_id for s in result] == [30, 10, 20, 30, 10, 20]
    handoffs = [s.starts_at.astimezone(CHI) for s in result[1:]]
    assert all(h.weekday() == 0 and h.time() == time(9, 0) for h in handoffs)
    assert all(s.source == "rotation" for s in result)


def test_shifts_cut_overrides_into_the_rotation():
    o = Ovr(99, local(2026, 2, 10, 12), local(2026, 2, 12, 12))
    start, end = local(2026, 2, 2, 9), local(2026, 2, 23, 9)
    result = shifts(Rot(), MEMBERS, [o], start, end, CHI)
    assert_tiles(result, start, end)
    assert [(s.user_id, s.source) for s in result] == [
        (10, "rotation"),
        (20, "rotation"),
        (99, "override"),
        (20, "rotation"),
        (30, "rotation"),
    ]


def test_shifts_overlapping_overrides_and_edge_cases():
    a = Ovr(99, local(2026, 2, 3, 12), local(2026, 2, 3, 18), created_at=T0)
    b = Ovr(98, local(2026, 2, 3, 14), local(2026, 2, 3, 20), created_at=T0 + timedelta(days=1))
    start, end = local(2026, 2, 3), local(2026, 2, 4)
    result = shifts(Rot(), MEMBERS, [a, b], start, end, CHI)
    assert_tiles(result, start, end)
    assert [s.user_id for s in result] == [10, 99, 98, 10]
    assert shifts(Rot(), [], [], start, end, CHI) == []
    assert shifts(Rot(), MEMBERS, [], end, start, CHI) == []
    # before the anchor: only the part after the first handoff is covered
    early = shifts(Rot(), MEMBERS, [], local(2026, 1, 26), local(2026, 2, 3), CHI)
    assert early[0].starts_at == local(2026, 2, 2, 9).astimezone(UTC)
