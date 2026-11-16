"""Summary: derived views over transactions (totals, by category, by month)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import List, Optional, Tuple

_BASE = """
FROM transactions t
JOIN categories c ON c.id = t.category_id
"""


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


def _where(
    date_from: Optional[str], date_to: Optional[str], category: Optional[str]
) -> Tuple[str, List[object]]:
    clauses: List[str] = []
    params: List[object] = []
    if date_from:
        clauses.append("t.date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("t.date <= ?")
        params.append(date_to)
    if category:
        clauses.append("c.name = ?")
        params.append(category)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def build_summary(
    conn: sqlite3.Connection,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category: Optional[str] = None,
) -> Summary:
    """Aggregate totals, category breakdowns and month-over-month spend."""
    where, params = _where(date_from, date_to, category)

    totals = conn.execute(
        f"""
        SELECT
            COALESCE(SUM(CASE WHEN t.kind = 'income' THEN t.amount_cents END), 0) AS income,
            COALESCE(SUM(CASE WHEN t.kind = 'expense' THEN t.amount_cents END), 0) AS spend,
            COUNT(*) AS n
        """
        + _BASE
        + where,
        params,
    ).fetchone()

    category_rows = conn.execute(
        """
        SELECT c.name AS name, t.kind AS kind, SUM(t.amount_cents) AS total
        """
        + _BASE
        + where
        + """
        GROUP BY c.name, t.kind
        ORDER BY total DESC, c.name ASC
        """,
        params,
    ).fetchall()

    spend_by_category = [
        CategoryTotal(name=row["name"], total_cents=int(row["total"]))
        for row in category_rows
        if row["kind"] == "expense"
    ]
    income_by_category = [
        CategoryTotal(name=row["name"], total_cents=int(row["total"]))
        for row in category_rows
        if row["kind"] == "income"
    ]

    month_rows = conn.execute(
        """
        SELECT substr(t.date, 1, 7) AS month,
               COALESCE(SUM(CASE WHEN t.kind = 'income' THEN t.amount_cents END), 0) AS income,
               COALESCE(SUM(CASE WHEN t.kind = 'expense' THEN t.amount_cents END), 0) AS spend
        """
        + _BASE
        + where
        + """
        GROUP BY month
        ORDER BY month ASC
        """,
        params,
    ).fetchall()

    monthly = [
        MonthTotal(
            month=row["month"],
            income_cents=int(row["income"]),
            spend_cents=int(row["spend"]),
        )
        for row in month_rows
    ]

    return Summary(
        total_income_cents=int(totals["income"]),
        total_spend_cents=int(totals["spend"]),
        transaction_count=int(totals["n"]),
        spend_by_category=spend_by_category,
        income_by_category=income_by_category,
        monthly=monthly,
    )
