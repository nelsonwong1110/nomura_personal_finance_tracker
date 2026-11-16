"""Summary aggregation: totals, category breakdowns, monthly trends, filters."""

from __future__ import annotations

from pft.models.filters import TransactionFilter
from pft.models.kind import Kind
from pft.models.transaction import Transaction
from pft.services.summary import build_summary
from pft.storage import repository


def add(conn, kind, amount_cents, date, category, merchant="M"):
    return repository.add_transaction(
        conn,
        Transaction(
            kind=kind,
            amount_cents=amount_cents,
            date=date,
            merchant=merchant,
            category=category,
        ),
    )


def seed(conn):
    add(conn, Kind.INCOME, 320000, "2026-10-01", "income")
    add(conn, Kind.EXPENSE, 4250, "2026-10-02", "groceries")
    add(conn, Kind.EXPENSE, 4000, "2026-10-20", "groceries")
    add(conn, Kind.EXPENSE, 1575, "2026-10-03", "dining")
    add(conn, Kind.EXPENSE, 1000, "2026-11-02", "groceries")


def test_empty_summary(conn):
    result = build_summary(conn)
    assert result.total_income_cents == 0
    assert result.total_spend_cents == 0
    assert result.net_cents == 0
    assert result.transaction_count == 0
    assert result.spend_by_category == []
    assert result.monthly == []


def test_totals(conn):
    seed(conn)
    result = build_summary(conn)
    assert result.total_income_cents == 320000
    assert result.total_spend_cents == 4250 + 4000 + 1575 + 1000
    assert result.net_cents == 320000 - (4250 + 4000 + 1575 + 1000)
    assert result.transaction_count == 5


def test_spend_by_category_sorted_desc(conn):
    seed(conn)
    result = build_summary(conn)
    assert [(c.name, c.total_cents) for c in result.spend_by_category] == [
        ("groceries", 4250 + 4000 + 1000),
        ("dining", 1575),
    ]
    assert [(c.name, c.total_cents) for c in result.income_by_category] == [
        ("income", 320000)
    ]


def test_monthly_trend_ascending(conn):
    seed(conn)
    result = build_summary(conn)
    assert [m.month for m in result.monthly] == ["2026-10", "2026-11"]
    october = result.monthly[0]
    assert october.income_cents == 320000
    assert october.spend_cents == 4250 + 4000 + 1575


def test_date_range_filter(conn):
    seed(conn)
    result = build_summary(
        conn, TransactionFilter(date_from="2026-10-01", date_to="2026-10-31")
    )
    assert result.transaction_count == 4
    assert result.total_spend_cents == 4250 + 4000 + 1575


def test_category_filter(conn):
    seed(conn)
    result = build_summary(conn, TransactionFilter(category="dining"))
    assert result.transaction_count == 1
    assert result.total_spend_cents == 1575
    assert result.total_income_cents == 0
