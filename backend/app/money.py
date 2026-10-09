"""Billing arithmetic. Integer cents everywhere; Decimal only for intermediate products.

Rules (docs/PLAN.md section 6):
  * amount = round_half_up(quantity * unit_price_cents), per line
  * tax    = round_half_up(amount * tax_rate_bp / 10000), per line, on the ROUNDED amount
  * invoice subtotal / tax / total are plain sums of the per-line integers, so the lines
    always add up to the total exactly (no penny drift)
"Half up" means ties round AWAY from zero, so a credit line is the exact mirror of a charge.
"""

from decimal import ROUND_HALF_UP, Decimal

QTY_PLACES = Decimal("0.0001")
BP = Decimal(10000)


def round_cents(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def to_qty(value: Decimal | int | str) -> Decimal:
    return Decimal(value).quantize(QTY_PLACES, rounding=ROUND_HALF_UP)


def hours(minutes: int) -> Decimal:
    """Billable minutes -> hours to 4 places (exact for 15/30/60-minute increments)."""
    return to_qty(Decimal(minutes) / 60)


def line_amounts(quantity: Decimal, unit_price_cents: int, tax_rate_bp: int) -> tuple[int, int]:
    """-> (amount_cents, tax_cents) for one invoice line."""
    amount = round_cents(Decimal(quantity) * unit_price_cents)
    tax = round_cents(Decimal(amount) * tax_rate_bp / BP)
    return amount, tax


def marked_up(cost_cents: int, markup_bp: int) -> int:
    """What a client is charged for something that cost `cost_cents`: cost + markup, the markup
    rounded half up to a whole cent. 12,345 c at 1,500 bp -> 12,345 + 1,852 = 14,197 c."""
    return cost_cents + round_cents(Decimal(cost_cents) * markup_bp / BP)


def format_money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    dollars, rem = divmod(abs(cents), 100)
    return f"{sign}${dollars:,}.{rem:02d}"
