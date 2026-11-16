"""Amount parsing and formatting."""

from __future__ import annotations

import pytest

from pft.errors import AmountError
from pft.models.amount import format_amount, parse_amount


@pytest.mark.parametrize(
    "text,expected",
    [
        ("12.50", 1250),
        ("$12.50", 1250),
        ("12.5", 1250),
        ("12", 1200),
        ("1,234.56", 123456),
        (" 7.00 ", 700),
    ],
)
def test_parse_accepts_display_amounts(text, expected):
    assert parse_amount(text, 2) == expected


def test_parse_respects_decimal_places():
    assert parse_amount("¥1200", 0) == 1200
    assert parse_amount("1200", 0) == 1200


@pytest.mark.parametrize(
    "text",
    ["", "abc", "$", "0", "0.00", "-5", "-0.01", "NaN", "Infinity"],
)
def test_parse_rejects_invalid(text):
    with pytest.raises(AmountError):
        parse_amount(text, 2)


def test_parse_rejects_over_precision():
    with pytest.raises(AmountError):
        parse_amount("12.505", 2)
    with pytest.raises(AmountError):
        parse_amount("1200.5", 0)


def test_parse_rejects_bad_decimal_places():
    with pytest.raises(AmountError):
        parse_amount("10", 5)
    with pytest.raises(AmountError):
        parse_amount("10", -1)


def test_format():
    assert format_amount(1250, "$", 2) == "$12.50"
    assert format_amount(123456, "$", 2) == "$1,234.56"
    assert format_amount(1200, "¥", 0) == "¥1,200"
    assert format_amount(-1200, "$", 2) == "-$12.00"
