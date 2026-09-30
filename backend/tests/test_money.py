import random
from decimal import Decimal
from fractions import Fraction

import pytest

from app.money import format_money, hours, line_amounts, round_cents, to_qty


@pytest.mark.parametrize(
    "value,expected",
    [
        (Decimal("0.5"), 1),
        (Decimal("1.5"), 2),
        (Decimal("2.5"), 3),  # ties go UP, not to even
        (Decimal("0.49999"), 0),
        (Decimal("-0.5"), -1),
        (Decimal("-1.5"), -2),  # away from zero
        (Decimal("3086.25"), 3086),
        (Decimal("254.595"), 255),
        (Decimal(0), 0),
    ],
)
def test_round_half_up_ties_away_from_zero(value, expected):
    assert round_cents(value) == expected


@pytest.mark.parametrize(
    "qty,price,bp,amount,tax",
    [
        (Decimal("1"), 12500, 0, 12500, 0),
        (Decimal("25"), 1200, 0, 30000, 0),  # 25 users x $12.00
        (Decimal("0.25"), 12345, 0, 3086, 0),  # 3086.25 -> 3086
        (Decimal("0.25"), 12345, 825, 3086, 255),  # 8.25% of 3086 = 254.595 -> 255
        (Decimal("1.5"), 15000, 825, 22500, 1856),  # 1856.25 -> 1856
        (Decimal("3"), 999, 1000, 2997, 300),  # 299.7 -> 300
        (Decimal("1"), 1, 5000, 1, 1),  # 0.5 -> 1
        (Decimal("-1"), 1, 5000, -1, -1),  # mirror image for a credit
        (Decimal("-2"), 5000, 825, -10000, -825),
        (Decimal("0"), 5000, 825, 0, 0),
    ],
)
def test_line_amounts(qty, price, bp, amount, tax):
    assert line_amounts(qty, price, bp) == (amount, tax)


def test_tax_is_computed_on_the_rounded_amount_and_credits_mirror_charges():
    rng = random.Random(42)
    for _ in range(2000):
        qty = Decimal(rng.randint(1, 200000)) / Decimal(10000)  # up to 20.0000
        price, bp = rng.randint(0, 500000), rng.choice([0, 500, 825, 1000, 1025])
        amount, tax = line_amounts(qty, price, bp)
        assert (amount, tax) == (
            round_half_up_reference(Fraction(qty) * price),
            round_half_up_reference(Fraction(amount) * bp / 10000),
        )
        assert line_amounts(-qty, price, bp) == (-amount, -tax)


def round_half_up_reference(x: Fraction) -> int:
    """Independent reference using exact rational arithmetic (no Decimal)."""
    sign = -1 if x < 0 else 1
    x = abs(x)
    return sign * int(x + Fraction(1, 2)) if x - int(x) >= Fraction(1, 2) else sign * int(x)


def test_invoice_totals_are_the_sum_of_lines_with_no_penny_drift():
    """Per-line rounding means the invoice never disagrees with its own lines."""
    rng = random.Random(7)
    for _ in range(500):
        lines = [
            line_amounts(Decimal(rng.randint(1, 400)) / 4, rng.randint(1, 20000), 825)
            for _ in range(rng.randint(1, 12))
        ]
        subtotal, tax = sum(a for a, _ in lines), sum(t for _, t in lines)
        total = subtotal + tax
        assert total == sum(a + t for a, t in lines)
        # Tax on the whole invoice can legitimately differ by a few cents from tax per line;
        # what must hold is that WE ARE CONSISTENT with the per-line rule.
        assert abs(tax - round_cents(Decimal(subtotal) * 825 / 10000)) <= len(lines)


@pytest.mark.parametrize(
    "minutes,expected",
    [
        (15, "0.2500"),
        (30, "0.5000"),
        (45, "0.7500"),
        (60, "1.0000"),
        (90, "1.5000"),
        (10, "0.1667"),
        (20, "0.3333"),
        (0, "0.0000"),
    ],
)
def test_hours(minutes, expected):
    assert str(hours(minutes)) == expected


def test_to_qty_quantizes_to_four_places():
    assert str(to_qty("2.00005")) == "2.0001" and str(to_qty(3)) == "3.0000"


@pytest.mark.parametrize(
    "cents,text",
    [
        (0, "$0.00"),
        (5, "$0.05"),
        (100, "$1.00"),
        (123456, "$1,234.56"),
        (-2500, "-$25.00"),
        (100000000, "$1,000,000.00"),
    ],
)
def test_format_money(cents, text):
    assert format_money(cents) == text
