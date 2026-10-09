import random
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.availability import (
    conflicts,
    default_weekly,
    free_windows,
    merge,
    overlaps,
    subtract,
    working_windows,
)

ZONES = [
    "America/Chicago",
    "America/New_York",
    "Europe/London",
    "Australia/Lord_Howe",
    "America/St_Johns",
    "Asia/Kolkata",
    "UTC",
]
WEEK = {d: (540, 1020) for d in range(7)}
ALL_DAY = {d: (0, 1440) for d in range(7)}
H = timedelta(hours=1)


def utc(*a):
    return datetime(*a, tzinfo=UTC)


def total(ivs):
    return sum((e - s for s, e in ivs), timedelta())


def intersect(a, b):
    out = []
    for s1, e1 in a:
        for s2, e2 in b:
            s, e = max(s1, s2), min(e1, e2)
            if s < e:
                out.append((s, e))
    return out


@pytest.mark.parametrize("zone", ZONES)
def test_every_day_of_2026_has_one_8h_window_starting_at_nine_local(zone):
    tz = ZoneInfo(zone)
    day = date(2026, 1, 1)
    while day < date(2027, 1, 1):
        start = datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(UTC)
        end = datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(UTC) + timedelta(
            hours=26
        )
        # restrict to the local day by taking the window that starts on `day`
        ws = [
            w
            for w in working_windows(start, end, tz, WEEK, {})
            if w[0].astimezone(tz).date() == day
        ]
        assert len(ws) == 1
        assert ws[0][1] - ws[0][0] == 8 * H
        local = ws[0][0].astimezone(tz)
        assert (local.hour, local.minute) == (9, 0)
        day += timedelta(days=1)


@pytest.mark.parametrize(
    "zone,day,hours",
    [
        ("America/Chicago", date(2026, 3, 8), 23),
        ("America/Chicago", date(2026, 11, 1), 25),
        ("Europe/London", date(2026, 3, 29), 23),
        ("Europe/London", date(2026, 10, 25), 25),
        ("America/Chicago", date(2026, 6, 1), 24),
        ("Europe/London", date(2026, 6, 1), 24),
    ],
)
def test_full_day_window_length_on_dst_days(zone, day, hours):
    tz = ZoneInfo(zone)
    start = datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(UTC)
    nxt = day + timedelta(days=1)
    end = datetime(nxt.year, nxt.month, nxt.day, tzinfo=tz).astimezone(UTC)
    ws = working_windows(start, end, tz, ALL_DAY, {})
    assert total(ws) == hours * H


def test_window_starting_in_spring_forward_gap():
    tz = ZoneInfo("America/Chicago")
    weekly = {6: (150, 300)}  # Sunday 02:30-05:00; 02:30 does not exist on 2026-03-08
    ws = working_windows(utc(2026, 3, 8), utc(2026, 3, 9), tz, weekly, {})
    assert len(ws) == 1
    assert ws[0][1] > ws[0][0]


def test_range_spanning_local_midnight():
    tz = ZoneInfo("Asia/Kolkata")
    # 2026-06-01 is Monday. 22:00 UTC Sun = 03:30 Mon IST.
    ws = working_windows(utc(2026, 5, 31, 22), utc(2026, 6, 1, 6), tz, {0: (0, 1440)}, {})
    assert ws == [(utc(2026, 5, 31, 22), utc(2026, 6, 1, 6))]
    # Starting just before local midnight on Sunday only gets the Monday part.
    ws = working_windows(utc(2026, 5, 31, 18), utc(2026, 5, 31, 20), tz, {0: (0, 1440)}, {})
    assert ws == [(utc(2026, 5, 31, 18, 30), utc(2026, 5, 31, 20))]


def test_holidays():
    tz = ZoneInfo("America/Chicago")
    monday = date(2026, 6, 1)
    start, end = utc(2026, 6, 1, 0), utc(2026, 6, 2, 12)
    base = working_windows(start, end, tz, WEEK, {})
    assert total(base) == 8 * H
    assert working_windows(start, end, tz, WEEK, {monday: None}) == []
    short = working_windows(start, end, tz, WEEK, {monday: (600, 780)})
    local = [(s.astimezone(tz), e.astimezone(tz)) for s, e in short]
    assert [(s.hour, e.hour) for s, e in local] == [(10, 13)]
    # holiday on a non-working weekday changes nothing
    weekdays = {d: (540, 1020) for d in range(5)}
    sat = date(2026, 6, 6)
    s, e = utc(2026, 6, 6, 0), utc(2026, 6, 8, 0)
    assert working_windows(s, e, tz, weekdays, {sat: (0, 1440)}) == working_windows(
        s, e, tz, weekdays, {}
    )
    assert working_windows(s, e, tz, weekdays, {sat: (0, 1440)}) == []


def test_naive_and_reversed_ranges_raise():
    tz = ZoneInfo("UTC")
    with pytest.raises(ValueError):
        working_windows(datetime(2026, 1, 1), utc(2026, 1, 2), tz, WEEK, {})
    with pytest.raises(ValueError):
        working_windows(utc(2026, 1, 1), datetime(2026, 1, 2), tz, WEEK, {})
    with pytest.raises(ValueError):
        working_windows(utc(2026, 1, 2), utc(2026, 1, 1), tz, WEEK, {})
    with pytest.raises(ValueError):
        working_windows(utc(2026, 1, 1), utc(2026, 1, 1), tz, WEEK, {})


def test_default_weekly():
    class S:
        business_start_minute = 480
        business_end_minute = 1020
        business_days = [0, 1, 2]

    assert default_weekly(S()) == {0: (480, 1020), 1: (480, 1020), 2: (480, 1020)}


def test_merge_and_free_windows():
    a = utc(2026, 1, 1, 9)
    assert merge([(a, a + H), (a + H, a + 2 * H), (a, a)]) == [(a, a + 2 * H)]
    tz = ZoneInfo("UTC")
    busy = [(utc(2026, 6, 1, 10), utc(2026, 6, 1, 11))]
    fw = free_windows(utc(2026, 6, 1), utc(2026, 6, 2), tz, WEEK, {}, busy)
    assert fw == [
        (utc(2026, 6, 1, 9), utc(2026, 6, 1, 10)),
        (utc(2026, 6, 1, 11), utc(2026, 6, 1, 17)),
    ]


def test_subtract_property():
    rng = random.Random(2026)
    base = utc(2026, 1, 1)

    def rand_ivs(n):
        out = []
        for _ in range(n):
            s = rng.randrange(0, 1000)
            out.append(
                (base + timedelta(minutes=s), base + timedelta(minutes=s + rng.randrange(0, 200)))
            )
        return out

    for _ in range(500):
        windows = merge(rand_ivs(rng.randrange(0, 6)))
        busy = rand_ivs(rng.randrange(0, 6))
        res = subtract(windows, busy)
        assert res == sorted(res)
        for (_s, e), (s2, _e2) in zip(res, res[1:], strict=False):
            assert e <= s2
        for s, e in res:
            assert s < e
            assert any(ws <= s and e <= we for ws, we in windows)
            assert not any(overlaps((s, e), b) for b in busy)
        assert total(windows) == total(res) + total(intersect(windows, merge(busy)))


def test_overlaps_half_open():
    a = (utc(2026, 1, 1, 9), utc(2026, 1, 1, 10))
    b = (utc(2026, 1, 1, 10), utc(2026, 1, 1, 11))
    assert not overlaps(a, b) and not overlaps(b, a)
    assert overlaps(a, (utc(2026, 1, 1, 9, 59), utc(2026, 1, 1, 11)))


def test_conflicts():
    working = [(utc(2026, 6, 1, 9), utc(2026, 6, 1, 17))]
    inside = (utc(2026, 6, 1, 10), utc(2026, 6, 1, 11))
    assert conflicts(inside, working, [], []) == []
    straddle = (utc(2026, 6, 1, 16), utc(2026, 6, 1, 18))
    assert conflicts(straddle, working, [], []) == [{"kind": "outside_hours"}]
    off = [
        (2, "pending", (utc(2026, 6, 1, 10, 30), utc(2026, 6, 1, 12))),
        (1, "approved", (utc(2026, 6, 1, 9), utc(2026, 6, 1, 10, 15))),
    ]
    assert conflicts(inside, working, off, []) == [
        {"kind": "time_off", "time_off_id": 1},
        {"kind": "time_off_pending", "time_off_id": 2},
    ]
    appts = [
        (5, (utc(2026, 6, 1, 11), utc(2026, 6, 1, 12))),  # touching end
        (6, (utc(2026, 6, 1, 9), utc(2026, 6, 1, 10))),  # touching start
        (8, (utc(2026, 6, 1, 10, 30), utc(2026, 6, 1, 12))),
        (7, (utc(2026, 6, 1, 10, 15), utc(2026, 6, 1, 10, 20))),
    ]
    assert conflicts(inside, working, [], appts) == [
        {"kind": "overlap", "appointment_id": 7},
        {"kind": "overlap", "appointment_id": 8},
    ]
