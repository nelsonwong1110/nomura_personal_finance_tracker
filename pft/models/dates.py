"""Date helpers. Transaction dates are stored as ISO YYYY-MM-DD strings."""

from __future__ import annotations

from datetime import date, datetime

from pft.errors import DateError

ISO_FORMAT = "%Y-%m-%d"


def validate_iso_date(text: str) -> str:
    """Validate and normalize an ISO date string (YYYY-MM-DD)."""
    try:
        parsed = datetime.strptime(str(text).strip(), ISO_FORMAT)
    except (TypeError, ValueError):
        raise DateError(f"invalid date {text!r}, expected YYYY-MM-DD") from None
    return parsed.strftime(ISO_FORMAT)


def format_date(iso_date: str, fmt: str = ISO_FORMAT) -> str:
    """Render a stored ISO date using the configured display format."""
    try:
        return datetime.strptime(iso_date, ISO_FORMAT).strftime(fmt)
    except ValueError:
        return iso_date


def today_iso() -> str:
    """Today's date in ISO format."""
    return date.today().strftime(ISO_FORMAT)
