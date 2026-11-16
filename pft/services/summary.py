"""Summary: derived views over transactions (totals, by category, by month).

All SQL lives in the repository; this service shapes the rows into dataclasses.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import List, Optional

from pft.storage import repository


@dataclass(frozen=True)
class CategoryTotal:
    name: str
    total_cents: int


@dataclass(frozen=True)
class MonthTotal:
    month: str  # YYYY-MM
    income_cents: int
    spend_cents: int


@dataclass(frozen=True)
class Summary:
    total_income_cents: int
    total_spend_cents: int
    transaction_count: int
    spend_by_category: List[CategoryTotal]
    income_by_category: List[CategoryTotal]
    monthly: List[MonthTotal]

    @property
    def net_cents(self) -> int:
        return self.total_income_cents - self.total_spend_cents


def build_summary(
    conn: sqlite3.Connection,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category: Optional[str] = None,
) -> Summary:
    """Aggregate totals, category breakdowns and month-over-month spend."""
    totals = repository.summary_totals(conn, date_from, date_to, category)

    category_rows = repository.summary_by_category(conn, date_from, date_to, category)
    spend_by_category = [
        CategoryTotal(name=name, total_cents=total)
        for name, kind, total in category_rows
        if kind == "expense"
    ]
    income_by_category = [
        CategoryTotal(name=name, total_cents=total)
        for name, kind, total in category_rows
        if kind == "income"
    ]

    monthly = [
        MonthTotal(month=month, income_cents=income, spend_cents=spend)
        for month, income, spend in repository.summary_monthly(
            conn, date_from, date_to, category
        )
    ]

    return Summary(
        total_income_cents=totals["income"],
        total_spend_cents=totals["spend"],
        transaction_count=totals["count"],
        spend_by_category=spend_by_category,
        income_by_category=income_by_category,
        monthly=monthly,
    )
