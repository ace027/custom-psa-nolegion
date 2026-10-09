"""Availability math: pure functions, no database access.

All datetimes are timezone-aware; results are expressed in UTC. Intervals are half-open
[start, end), so touching intervals do not overlap. Local wall-clock hours are converted with
`app.sla._at`, which is DST-correct (the same helper the SLA clocks use).
"""

from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.sla import _at

Interval = tuple[datetime, datetime]


def default_weekly(settings) -> dict[int, tuple[int, int]]:
    """Org business hours as a weekly map: weekday (0 = Monday) -> (start_minute, end_minute)."""
    return {
        d: (settings.business_start_minute, settings.business_end_minute)
        for d in settings.business_days
    }


def _local(day: date, minute: int, tz: ZoneInfo) -> datetime:
    # `_at` treats 24:00 as midnight + 24 elapsed hours, which is wrong on DST days;
    # use the next local midnight instead.
    if minute >= 1440:
        return _at(day + timedelta(days=1), 0, tz)
    return _at(day, minute, tz)


def merge(intervals: Iterable[Interval]) -> list[Interval]:
    """Sorted union; overlapping and adjacent intervals are joined, empty ones dropped."""
    out: list[Interval] = []
    for s, e in sorted(i for i in intervals if i[0] < i[1]):
        if out and s <= out[-1][1]:
            if e > out[-1][1]:
                out[-1] = (out[-1][0], e)
        else:
            out.append((s, e))
    return out


def working_windows(
    start: datetime,
    end: datetime,
    tz: ZoneInfo,
    weekly: Mapping[int, tuple[int, int]],
    holidays: Mapping[date, tuple[int, int] | None],
) -> list[Interval]:
    """Working windows (UTC) within [start, end] for a tech in `tz`."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware")
    if end <= start:
        raise ValueError("end must be after start")
    start, end = start.astimezone(UTC), end.astimezone(UTC)
    day = start.astimezone(tz).date() - timedelta(days=1)
    last = end.astimezone(tz).date() + timedelta(days=1)
    windows: list[Interval] = []
    while day <= last:
        hours = weekly.get(day.weekday())
        if hours is not None:
            if day in holidays:
                h = holidays[day]
                hours = None if h is None else (max(hours[0], h[0]), min(hours[1], h[1]))
            if hours is not None and hours[0] < hours[1]:
                w_start = max(_local(day, hours[0], tz), start)
                w_end = min(_local(day, hours[1], tz), end)
                if w_start < w_end:
                    windows.append((w_start, w_end))
        day += timedelta(days=1)
    return merge(windows)


def subtract(windows: Iterable[Interval], busy: Iterable[Interval]) -> list[Interval]:
    """`windows` minus the union of `busy`; sorted, no zero-length pieces."""
    blocked = merge(busy)
    out: list[Interval] = []
    for w_start, w_end in merge(windows):
        cur = w_start
        for b_start, b_end in blocked:
            if b_end <= cur:
                continue
            if b_start >= w_end:
                break
            if b_start > cur:
                out.append((cur, b_start))
            cur = max(cur, b_end)
            if cur >= w_end:
                break
        if cur < w_end:
            out.append((cur, w_end))
    return out


def free_windows(
    start: datetime,
    end: datetime,
    tz: ZoneInfo,
    weekly: Mapping[int, tuple[int, int]],
    holidays: Mapping[date, tuple[int, int] | None],
    busy: Iterable[Interval],
) -> list[Interval]:
    return subtract(working_windows(start, end, tz, weekly, holidays), busy)


def overlaps(a: Interval, b: Interval) -> bool:
    """Half-open overlap: touching intervals do not overlap."""
    return a[0] < b[1] and b[0] < a[1]


def conflicts(
    slot: Interval,
    working: list[Interval],
    time_off: Iterable[tuple[int, str, Interval]],
    appointments: Iterable[tuple[int, Interval]],
) -> list[dict]:
    """Classify why `slot` is not bookable. Callers pass only pending/approved time off."""
    out: list[dict] = []
    if not any(w[0] <= slot[0] and slot[1] <= w[1] for w in merge(working)):
        out.append({"kind": "outside_hours"})
    for tid, status, iv in sorted(time_off, key=lambda t: t[2][0]):
        if overlaps(slot, iv):
            kind = "time_off" if status == "approved" else "time_off_pending"
            out.append({"kind": kind, "time_off_id": tid})
    for aid, iv in sorted(appointments, key=lambda a: a[1][0]):
        if overlaps(slot, iv):
            out.append({"kind": "overlap", "appointment_id": aid})
    return out
