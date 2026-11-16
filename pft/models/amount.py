"""Amount: monetary values as integer minor units (cents).

Amounts are stored as integers to avoid floating point drift. Parsing accepts
display strings like "$12.50" or "12.5"; formatting uses the configured
currency symbol and decimal places.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from pft.errors import AmountError

CURRENCY_SYMBOLS = ("$", "€", "£", "¥", "₹", "₩", "₽")


def parse_amount(text: str, decimal_places: int = 2) -> int:
    """Parse a user-supplied amount string into integer minor units.

    Accepts an optional currency symbol and thousands separators. Rejects
    zero, negative, non-numeric and over-precise values.
    """
    if not isinstance(decimal_places, int) or isinstance(decimal_places, bool):
        raise AmountError("decimal places must be an integer")
    if not 0 <= decimal_places <= 4:
        raise AmountError("decimal places must be between 0 and 4")

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

    scale = Decimal(10) ** decimal_places
    scaled = value * scale
    if scaled != scaled.to_integral_value():
        raise AmountError(
            f"amount {text!r} has more than {decimal_places} decimal place(s)"
        )
    return int(scaled)


def format_amount(minor_units: int, symbol: str = "$", decimal_places: int = 2) -> str:
    """Format integer minor units for display, e.g. 1250 -> '$12.50'."""
    scale = Decimal(10) ** decimal_places
    value = Decimal(minor_units) / scale
    sign = "-" if value < 0 else ""
    return f"{sign}{symbol}{abs(value):,.{decimal_places}f}"
