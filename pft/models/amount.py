"""Amount: monetary values as integer minor units (cents).

Amounts are stored as integers to avoid floating point drift. Parsing accepts
display strings like "$12.50" or "12.5"; formatting uses the configured
currency symbol and a fixed two decimal places.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from pft.errors import AmountError

CURRENCY_SYMBOLS = ("$", "€", "£", "¥", "₹", "₩", "₽")

# Major-currency convention: two decimal places (cents).
DECIMAL_PLACES = 2


def parse_amount(text: str) -> int:
    """Parse a user-supplied amount string into integer minor units.

    Accepts an optional currency symbol and thousands separators. Rejects
    zero, negative, non-numeric and over-precise values.
    """
    raw = str(text).strip()
    if not raw:
        raise AmountError("amount is empty")

    cleaned = raw
    for symbol in CURRENCY_SYMBOLS:
        cleaned = cleaned.replace(symbol, "")
    cleaned = cleaned.replace(",", "").strip()
    if not cleaned:
        raise AmountError(f"invalid amount: {text!r}")

    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise AmountError(f"invalid amount: {text!r}") from None
    if not value.is_finite():
        raise AmountError(f"invalid amount: {text!r}")
    if value <= 0:
        raise AmountError(f"amount must be positive (got {text!r})")

    scale = Decimal(10) ** DECIMAL_PLACES
    scaled = value * scale
    if scaled != scaled.to_integral_value():
        raise AmountError(
            f"amount {text!r} has more than {DECIMAL_PLACES} decimal place(s)"
        )
    return int(scaled)


def format_amount(minor_units: int, symbol: str = "$") -> str:
    """Format integer minor units for display, e.g. 1250 -> '$12.50'."""
    scale = Decimal(10) ** DECIMAL_PLACES
    value = Decimal(minor_units) / scale
    sign = "-" if value < 0 else ""
    return f"{sign}{symbol}{abs(value):,.{DECIMAL_PLACES}f}"
