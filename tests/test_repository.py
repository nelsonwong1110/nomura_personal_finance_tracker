"""Repository: inserts, categories, listing, edit/delete and provenance idempotency."""

from __future__ import annotations

from dataclasses import replace

import pytest

from pft.errors import NotFoundError, UnknownCategoryError
from pft.models.filters import TransactionFilter
from pft.models.kind import Kind
from pft.storage import repository


def test_add_and_get(conn, make_tx):
    tx_id = repository.add_transaction(conn, make_tx())
    fetched = repository.get_transaction(conn, tx_id)
    assert fetched is not None
    assert fetched.merchant == "FreshMart"
    assert fetched.kind == Kind.EXPENSE
    assert fetched.category == "groceries"
    assert fetched.created_at  # audit metadata is populated


def test_default_category_is_uncategorized(conn, make_tx):
    tx_id = repository.add_transaction(conn, make_tx(category="uncategorized"))
    assert repository.get_transaction(conn, tx_id).category == "uncategorized"


def test_unknown_category_is_rejected(conn, make_tx):
    with pytest.raises(UnknownCategoryError):
        repository.add_transaction(conn, make_tx(category="groceris"))
    assert repository.count_transactions(conn) == 0


def test_add_category_is_idempotent(conn):
    assert repository.add_category(conn, "pet care") is True
    assert repository.add_category(conn, "pet care") is False
    assert repository.category_exists(conn, "pet care")


def test_categorize(conn, make_tx):
    tx_id = repository.add_transaction(conn, make_tx(category="uncategorized"))
    updated = repository.categorize(conn, tx_id, "dining")
    assert updated.category == "dining"


def test_categorize_unknown_category_rejected(conn, make_tx):
    tx_id = repository.add_transaction(conn, make_tx())
    with pytest.raises(UnknownCategoryError):
        repository.categorize(conn, tx_id, "groceris")


def test_categorize_missing_transaction_rejected(conn):
    with pytest.raises(NotFoundError):
        repository.categorize(conn, 999, "dining")


def test_list_orders_by_date_then_entry_order(conn, make_tx):
    first = repository.add_transaction(conn, make_tx(date="2026-10-01", merchant="A"))
    second = repository.add_transaction(conn, make_tx(date="2026-10-03", merchant="B"))
    third = repository.add_transaction(conn, make_tx(date="2026-10-01", merchant="C"))
    listed = repository.list_transactions(conn)
    # Newest date first; within equal dates, the later-entered row first.
    assert [t.id for t in listed] == [second, third, first]


def test_list_filters(conn, make_tx):
    repository.add_transaction(conn, make_tx(date="2026-10-01", category="groceries"))
    repository.add_transaction(conn, make_tx(date="2026-10-05", category="dining"))
    repository.add_transaction(conn, make_tx(date="2026-11-01", category="uncategorized"))

    in_range = repository.list_transactions(
        conn, TransactionFilter(date_from="2026-10-01", date_to="2026-10-31")
    )
    assert len(in_range) == 2
    only_dining = repository.list_transactions(
        conn, TransactionFilter(category="dining")
    )
    assert [t.category for t in only_dining] == ["dining"]
    uncategorized = repository.list_transactions(
        conn, TransactionFilter(uncategorized=True)
    )
    assert len(uncategorized) == 1


def test_add_if_new_skips_same_provenance(conn, make_tx):
    first = make_tx(source="bank.csv", ref="abc")
    assert repository.add_if_new(conn, first) is not None
    assert repository.add_if_new(conn, first) is None
    assert repository.count_transactions(conn) == 1


def test_add_if_new_keeps_content_identical_rows_from_other_provenance(conn, make_tx):
    repository.add_if_new(conn, make_tx(source="a.csv", ref="1"))
    repository.add_if_new(conn, make_tx(source="a.csv", ref="2"))
    repository.add_if_new(conn, make_tx(source="b.csv", ref="1"))
    assert repository.count_transactions(conn) == 3


def test_list_categories_in_seed_order(conn):
    names = [c.name for c in repository.list_categories(conn)]
    assert names[0] == "uncategorized"
    assert "groceries" in names


def test_edit_transaction(conn, make_tx):
    tx_id = repository.add_transaction(conn, make_tx())
    current = repository.get_transaction(conn, tx_id)
    candidate = replace(
        current, amount_cents=2000, merchant="BigBox", category="dining"
    )
    updated = repository.edit_transaction(conn, candidate)
    assert updated.amount_cents == 2000
    assert updated.merchant == "BigBox"
    assert updated.category == "dining"
    # Fields carried forward in the candidate are unchanged.
    assert updated.kind == Kind.EXPENSE
    assert updated.date == "2026-10-02"


def test_edit_preserves_provenance(conn, make_tx):
    tx_id = repository.add_transaction(conn, make_tx(source="/bank.csv", ref="abc"))
    current = repository.get_transaction(conn, tx_id)
    updated = repository.edit_transaction(conn, replace(current, merchant="BigBox"))
    # Provenance survives the edit, so a re-import skips this row and cannot
    # resurrect the pre-edit content.
    assert updated.source == "/bank.csv"
    assert updated.ref == "abc"


def test_edit_transaction_unknown_id(conn, make_tx):
    with pytest.raises(NotFoundError):
        repository.edit_transaction(conn, make_tx(id=999))


def test_edit_transaction_unknown_category(conn, make_tx):
    tx_id = repository.add_transaction(conn, make_tx())
    current = repository.get_transaction(conn, tx_id)
    with pytest.raises(UnknownCategoryError):
        repository.edit_transaction(conn, replace(current, category="groceris"))


def test_delete_transaction(conn, make_tx):
    tx_id = repository.add_transaction(conn, make_tx())
    deleted = repository.delete_transaction(conn, tx_id)
    assert deleted.id == tx_id
    assert repository.get_transaction(conn, tx_id) is None
    assert repository.count_transactions(conn) == 0


def test_delete_transaction_unknown_id(conn):
    with pytest.raises(NotFoundError):
        repository.delete_transaction(conn, 999)
