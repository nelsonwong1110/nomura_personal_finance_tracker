"""Repository: inserts, categories, listing and provenance idempotency."""

from __future__ import annotations

import pytest

from pft.errors import NotFoundError, UnknownCategoryError
from pft.models.kind import Kind
from pft.models.transaction import Transaction
from pft.storage import repository


def tx(**overrides):
    values = dict(
        kind=Kind.EXPENSE,
        amount_cents=1250,
        date="2026-10-02",
        merchant="Safeway",
        category="groceries",
    )
    values.update(overrides)
    return Transaction(**values)


def test_add_and_get(conn):
    tx_id = repository.add_transaction(conn, tx())
    fetched = repository.get_transaction(conn, tx_id)
    assert fetched is not None
    assert fetched.merchant == "Safeway"
    assert fetched.kind == Kind.EXPENSE
    assert fetched.category == "groceries"
    assert fetched.created_at  # audit metadata is populated


def test_default_category_is_uncategorized(conn):
    tx_id = repository.add_transaction(conn, tx(category="uncategorized"))
    assert repository.get_transaction(conn, tx_id).category == "uncategorized"


def test_unknown_category_is_rejected(conn):
    with pytest.raises(UnknownCategoryError):
        repository.add_transaction(conn, tx(category="groceris"))
    assert repository.count_transactions(conn) == 0


def test_add_category_is_idempotent(conn):
    assert repository.add_category(conn, "pet care") is True
    assert repository.add_category(conn, "pet care") is False
    assert repository.category_exists(conn, "pet care")


def test_categorize(conn):
    tx_id = repository.add_transaction(conn, tx(category="uncategorized"))
    updated = repository.categorize(conn, tx_id, "dining")
    assert updated.category == "dining"


def test_categorize_unknown_category_rejected(conn):
    tx_id = repository.add_transaction(conn, tx())
    with pytest.raises(UnknownCategoryError):
        repository.categorize(conn, tx_id, "groceris")


def test_categorize_missing_transaction_rejected(conn):
    with pytest.raises(NotFoundError):
        repository.categorize(conn, 999, "dining")


def test_list_orders_by_date_then_entry_order(conn):
    first = repository.add_transaction(conn, tx(date="2026-10-01", merchant="A"))
    second = repository.add_transaction(conn, tx(date="2026-10-03", merchant="B"))
    third = repository.add_transaction(conn, tx(date="2026-10-01", merchant="C"))
    listed = repository.list_transactions(conn)
    # Newest date first; within equal dates, the later-entered row first.
    assert [t.id for t in listed] == [second, third, first]


def test_list_filters(conn):
    repository.add_transaction(conn, tx(date="2026-10-01", category="groceries"))
    repository.add_transaction(conn, tx(date="2026-10-05", category="dining"))
    repository.add_transaction(conn, tx(date="2026-11-01", category="uncategorized"))

    in_range = repository.list_transactions(
        conn, date_from="2026-10-01", date_to="2026-10-31"
    )
    assert len(in_range) == 2
    only_dining = repository.list_transactions(conn, category="dining")
    assert [t.category for t in only_dining] == ["dining"]
    uncategorized = repository.list_transactions(conn, uncategorized=True)
    assert len(uncategorized) == 1


def test_add_if_new_skips_same_provenance(conn):
    first = tx(source="bank.csv", ref="abc")
    assert repository.add_if_new(conn, first) is not None
    assert repository.add_if_new(conn, first) is None
    assert repository.count_transactions(conn) == 1


def test_add_if_new_keeps_content_identical_rows_from_other_provenance(conn):
    repository.add_if_new(conn, tx(source="a.csv", ref="1"))
    repository.add_if_new(conn, tx(source="a.csv", ref="2"))
    repository.add_if_new(conn, tx(source="b.csv", ref="1"))
    assert repository.count_transactions(conn) == 3


def test_list_categories_in_seed_order(conn):
    names = [c.name for c in repository.list_categories(conn)]
    assert names[0] == "uncategorized"
    assert "groceries" in names
