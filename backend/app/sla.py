"""SLA clocks in BUSINESS minutes. Pure functions: no database access, easy to test.

Design: a ticket's due date is always derived as
    add_business_minutes(created_at, target_minutes + paused_business_minutes)
so pausing (waiting on customer, resolved, closed) never needs due dates to be "shifted";
we just credit the business minutes spent stopped and recompute.
"""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.models import CLOCK_STOPPED, Ticket

MAX_DAYS = 3660  # safety valve: never loop forever on a bad calendar


@dataclass(frozen=True)
class Calendar:
    tz: ZoneInfo
    days: frozenset[int]  # 0 = Monday
    start_minute: int
    end_minute: int
    # Local date -> None (closed all day) or (open, close) minutes. Only applies on business days.
    exceptions: Mapping[date, tuple[int, int] | None] = field(default_factory=dict, compare=False)

    @classmethod
    def from_settings(cls, s, exceptions: Mapping | None = None) -> "Calendar":
        return cls(
            ZoneInfo(s.timezone),
            frozenset(s.business_days),
            s.business_start_minute,
            s.business_end_minute,
            exceptions or {},
        )

    def validate(self) -> None:
        if not self.days or not self.days <= set(range(7)):
            raise ValueError("business_days must be a non-empty subset of 0..6")
        if not 0 <= self.start_minute < self.end_minute <= 1440:
            raise ValueError("business hours must satisfy 0 <= start < end <= 1440")


def _at(d: date, minute: int, tz: ZoneInfo) -> datetime:
    """Wall-clock time on local date `d`, returned in UTC (DST-correct)."""
    h, m = divmod(minute, 60)
    if h == 24:
        return datetime(d.year, d.month, d.day, tzinfo=tz).astimezone(UTC) + timedelta(days=1)
    return datetime(d.year, d.month, d.day, h, m, tzinfo=tz).astimezone(UTC)


def windows_from(start: datetime, cal: Calendar) -> Iterator[tuple[datetime, datetime]]:
    """Business windows (UTC) that end after `start`, in order."""
    day = start.astimezone(cal.tz).date()
    for _ in range(MAX_DAYS):
        if day.weekday() in cal.days:
            hours = cal.exceptions.get(day, (cal.start_minute, cal.end_minute))
            if hours is not None:
                w_start, w_end = _at(day, hours[0], cal.tz), _at(day, hours[1], cal.tz)
                if w_end > start:
                    yield w_start, w_end
        day += timedelta(days=1)


def add_business_minutes(start: datetime, minutes: int, cal: Calendar) -> datetime:
    if minutes <= 0:
        return start
    remaining = timedelta(minutes=minutes)
    for w_start, w_end in windows_from(start, cal):
        begin = max(w_start, start)
        available = w_end - begin
        if remaining <= available:
            return begin + remaining
        remaining -= available
    raise ValueError("no business time found within the search horizon")


def business_minutes_between(a: datetime, b: datetime, cal: Calendar) -> int:
    if b <= a:
        return 0
    total = timedelta()
    for w_start, w_end in windows_from(a, cal):
        if w_start >= b:
            break
        total += min(w_end, b) - max(w_start, a)
    return int(total.total_seconds() // 60)


def compute_due_dates(ticket: Ticket, cal: Calendar) -> tuple[datetime | None, datetime | None]:
    p = ticket.priority
    created = ticket.created_at

    def due(target: int | None) -> datetime | None:
        if not target:
            return None
        return add_business_minutes(created, target + ticket.sla_paused_minutes, cal)

    return due(p.first_response_minutes), due(p.resolution_minutes)


def sla_state(ticket: Ticket, cal: Calendar, at_risk_percent: int, now: datetime) -> str:
    """none | ok | at_risk | breached | paused | done"""
    if ticket.status in ("resolved", "closed"):
        return "done"
    if ticket.status in CLOCK_STOPPED:
        return "paused"
    clocks = []
    if ticket.first_responded_at is None:
        clocks.append((ticket.sla_first_response_due, ticket.priority.first_response_minutes))
    clocks.append((ticket.sla_resolution_due, ticket.priority.resolution_minutes))
    clocks = [(d, t) for d, t in clocks if d and t]
    if not clocks:
        return "none"
    state = "ok"
    for due, target in clocks:
        if now > due:
            return "breached"
        if business_minutes_between(now, due, cal) <= target * at_risk_percent / 100:
            state = "at_risk"
    return state
