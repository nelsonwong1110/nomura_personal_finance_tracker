"""Summary: derived views over transactions (totals, by category, by month).

All SQL lives in the repository; this service composes the repository's
aggregate dataclasses into a Summary.
"""

from __future__ import annotations

import sqlite3

from pft.models.filters import TransactionFilter
from pft.models.kind import Kind
from pft.models.summary import Summary
from pft.storage import repository


def build_summary(
    conn: sqlite3.Connection, filters: TransactionFilter = TransactionFilter()
) -> Summary:
    """Aggregate totals, category breakdowns and month-over-month spend."""
    totals = repository.summary_totals(conn, filters)
    spend_by_category = repository.summary_by_category(conn, filters, kind=Kind.EXPENSE)
    income_by_category = repository.summary_by_category(conn, filters, kind=Kind.INCOME)
    monthly = repository.summary_monthly(conn, filters)
    return Summary(
        total_income_cents=totals.income_cents,
        total_spend_cents=totals.spend_cents,
        transaction_count=totals.transaction_count,
        spend_by_category=spend_by_category,
        income_by_category=income_by_category,
        monthly=monthly,
    )
