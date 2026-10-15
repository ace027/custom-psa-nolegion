"""Pure on-call math: who is on call at an instant, and the shift list for a window. No DB access.

Rotation handoffs are wall-clock times in the business timezone (anchor_date at handoff_time, then
every 7 local days), so a DST change never moves a handoff off its local time. Overrides cover a
rotation member for a period and win over the rotation; the latest created override wins when
several overlap.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

Source = Literal["rotation", "override"]


class RotationLike(Protocol):
    handoff_weekday: int
    handoff_time: time
    anchor_date: date
    active: bool


class MemberLike(Protocol):
    user_id: int
    position: int


class OverrideLike(Protocol):
    user_id: int
    starts_at: datetime
    ends_at: datetime
    created_at: datetime


@dataclass(frozen=True)
class Shift:
    user_id: int
    starts_at: datetime
    ends_at: datetime
    source: Source


def _handoff(rotation: RotationLike, k: int, tz: ZoneInfo) -> datetime:
    """The k-th handoff instant (k = 0 is the anchor), as UTC."""
    day = rotation.anchor_date + timedelta(days=7 * k)
    return datetime.combine(day, rotation.handoff_time, tzinfo=tz).astimezone(UTC)


def _week_index(rotation: RotationLike, at: datetime, tz: ZoneInfo) -> int:
    """Index of the handoff at or before `at`; -1 when `at` is before the anchor handoff."""
    anchor_local = datetime.combine(rotation.anchor_date, rotation.handoff_time)
    at_local = at.astimezone(tz).replace(tzinfo=None)
    k = (at_local - anchor_local) // timedelta(days=7)
    # Settle the wall-clock estimate against real instants (gap/overlap hours near a handoff).
    while _handoff(rotation, k + 1, tz) <= at:
        k += 1
    while k >= 0 and _handoff(rotation, k, tz) > at:
        k -= 1
    return max(k, -1)


def _rotation_user(
    rotation: RotationLike, members: Sequence[MemberLike], at: datetime, tz: ZoneInfo
) -> tuple[int, int] | None:
    """(user_id, week index) from the rotation alone."""
    if not rotation.active or not members:
        return None
    k = _week_index(rotation, at, tz)
    if k < 0:
        return None
    ordered = sorted(members, key=lambda m: m.position)
    return ordered[k % len(ordered)].user_id, k


def _winning_override(overrides: Sequence[OverrideLike], at: datetime) -> OverrideLike | None:
    covering = [
        (o.created_at, i, o) for i, o in enumerate(overrides) if o.starts_at <= at < o.ends_at
    ]
    if not covering:
        return None
    return max(covering, key=lambda c: (c[0], c[1]))[2]


def who_is_on(
    rotation: RotationLike,
    members: Sequence[MemberLike],
    overrides: Sequence[OverrideLike],
    at: datetime,
    tz: ZoneInfo,
) -> tuple[int, str, datetime | None] | None:
    """(user_id, source, until) for the person on call at `at`, or None when nobody is."""
    at = at.astimezone(UTC)
    later_starts = [o.starts_at for o in overrides if o.starts_at > at]
    over = _winning_override(overrides, at)
    if over is not None:
        until = min([over.ends_at, *later_starts])
        return over.user_id, "override", until
    found = _rotation_user(rotation, members, at, tz)
    if found is None:
        return None
    user_id, k = found
    return user_id, "rotation", min([_handoff(rotation, k + 1, tz), *later_starts])


def shifts(
    rotation: RotationLike,
    members: Sequence[MemberLike],
    overrides: Sequence[OverrideLike],
    start: datetime,
    end: datetime,
    tz: ZoneInfo,
) -> list[Shift]:
    """Segments covering [start, end) with overrides cut into the rotation. Time with nobody on
    call (before the anchor, inactive, no members) is left out."""
    start, end = start.astimezone(UTC), end.astimezone(UTC)
    if end <= start:
        return []
    points = {start, end}
    for o in overrides:
        points.update(p for p in (o.starts_at, o.ends_at) if start < p < end)
    if rotation.active and members:
        k = max(_week_index(rotation, start, tz) + 1, 0)
        while (h := _handoff(rotation, k, tz)) < end:
            if h > start:
                points.add(h)
            k += 1
    out: list[Shift] = []
    ordered = sorted(points)
    for a, b in zip(ordered, ordered[1:], strict=False):
        who = who_is_on(rotation, members, overrides, a, tz)
        if who is None:
            continue
        user_id, source = who[0], who[1]
        if out and out[-1].ends_at == a and out[-1].user_id == user_id and out[-1].source == source:
            out[-1] = Shift(user_id, out[-1].starts_at, b, source)
        else:
            out.append(Shift(user_id, a, b, source))
    return out
