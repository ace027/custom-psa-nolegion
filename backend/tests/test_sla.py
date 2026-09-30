from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.sla import Calendar, add_business_minutes, business_minutes_between

CT = ZoneInfo("America/Chicago")
CAL = Calendar(CT, frozenset({0, 1, 2, 3, 4}), 8 * 60, 17 * 60)  # Mon-Fri 08:00-17:00 Central


def ct(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=CT).astimezone(UTC)


def test_add_within_a_day():
    # Wed 2026-09-30 09:00 CT + 60 => 10:00
    assert add_business_minutes(ct(2026, 9, 30, 9), 60, CAL) == ct(2026, 9, 30, 10)


def test_add_rolls_over_end_of_day_and_weekend():
    # Fri 16:30 + 60 => 30 min Fri, then Mon 08:30
    assert add_business_minutes(ct(2026, 10, 2, 16, 30), 60, CAL) == ct(2026, 10, 5, 8, 30)


def test_add_before_hours_starts_at_open_and_after_hours_starts_next_day():
    assert add_business_minutes(ct(2026, 9, 30, 2), 60, CAL) == ct(2026, 9, 30, 9)
    assert add_business_minutes(ct(2026, 9, 30, 20), 60, CAL) == ct(2026, 10, 1, 9)


def test_add_multi_day():
    # a 24h (1440 min) target = 160 business hours/9 = 2 days + 6h from Mon 08:00
    assert add_business_minutes(ct(2026, 9, 28, 8), 1440, CAL) == ct(2026, 9, 30, 14)


def test_zero_minutes_is_now():
    t = ct(2026, 9, 30, 12)
    assert add_business_minutes(t, 0, CAL) == t


def test_between_counts_only_business_time():
    assert business_minutes_between(ct(2026, 9, 30, 7), ct(2026, 9, 30, 18), CAL) == 9 * 60
    # Fri 16:00 -> Mon 09:00 = 60 + 60
    assert business_minutes_between(ct(2026, 10, 2, 16), ct(2026, 10, 5, 9), CAL) == 120
    # entirely on a weekend
    assert business_minutes_between(ct(2026, 10, 3, 9), ct(2026, 10, 4, 15), CAL) == 0
    assert business_minutes_between(ct(2026, 9, 30, 12), ct(2026, 9, 30, 11), CAL) == 0


def test_add_and_between_are_inverse():
    start = ct(2026, 9, 29, 15, 10)
    for minutes in (1, 45, 600, 2000):
        end = add_business_minutes(start, minutes, CAL)
        assert business_minutes_between(start, end, CAL) == minutes


def test_dst_spring_forward_is_wall_clock_correct():
    # US DST began Sun 2026-03-08. Fri 03-06 (CST) and Mon 03-09 (CDT) both open at 08:00 local.
    end = add_business_minutes(ct(2026, 3, 6, 16), 120, CAL)
    assert end == ct(2026, 3, 9, 9)  # 60 min Friday + 60 min Monday
    assert end.hour == 14  # 09:00 CDT = 14:00 UTC, whereas Friday's 09:00 CST = 15:00 UTC


def test_custom_calendar_seven_days_24h():
    cal = Calendar(ZoneInfo("UTC"), frozenset(range(7)), 0, 1440)
    start = datetime(2026, 9, 30, 12, tzinfo=UTC)
    assert add_business_minutes(start, 60, cal) == datetime(2026, 9, 30, 13, tzinfo=UTC)
    assert business_minutes_between(start, datetime(2026, 10, 2, 12, tzinfo=UTC), cal) == 2880


@pytest.mark.parametrize(
    "days,s,e",
    [
        (frozenset(), 0, 10),
        (frozenset({9}), 0, 10),
        (frozenset({1}), 600, 600),
        (frozenset({1}), 0, 1441),
    ],
)
def test_calendar_validation(days, s, e):
    with pytest.raises(ValueError):
        Calendar(ZoneInfo("UTC"), days, s, e).validate()
    Calendar(ZoneInfo("UTC"), frozenset({0}), 0, 1440).validate()
