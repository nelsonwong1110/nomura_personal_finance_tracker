"""Integrity checks: duplicate detection."""

from __future__ import annotations

from pft.models.kind import Kind
from pft.models.transaction import Transaction
from pft.services import integrity
from pft.storage import repository


def make_tx(**overrides):
    values = dict(
        kind=Kind.EXPENSE,
        amount_cents=1250,
        date="2026-10-02",
        merchant="Safeway",
        category="groceries",
    )
    values.update(overrides)
    return Transaction(**values)


def test_no_flag_without_peers(conn):
    assert integrity.run_checks(conn, make_tx()) == []


def test_candidate_duplicate_flags_existing(conn):
    existing_id = repository.add_transaction(conn, make_tx())
    flags = integrity.run_checks(conn, make_tx())
    assert len(flags) == 1
    assert flags[0].transaction_ids == [existing_id]
    assert flags[0].source == "integrity:duplicate"


def test_stored_duplicate_flags_both(conn):
    first = repository.add_transaction(conn, make_tx())
    second = repository.add_transaction(conn, make_tx())
    stored = repository.get_transaction(conn, second)
    flags = integrity.run_checks(conn, stored)
    assert len(flags) == 1
    assert sorted(flags[0].transaction_ids) == sorted([first, second])


def test_kind_mismatch_is_not_a_duplicate(conn):
    repository.add_transaction(conn, make_tx(kind=Kind.INCOME))
    assert integrity.run_checks(conn, make_tx(kind=Kind.EXPENSE)) == []


def test_amount_difference_is_not_a_duplicate(conn):
    repository.add_transaction(conn, make_tx(amount_cents=1250))
    assert integrity.run_checks(conn, make_tx(amount_cents=1251)) == []


def test_category_difference_is_not_a_duplicate_criterion(conn):
    """Category is mutable metadata; a label change must not hide a duplicate."""
    repository.add_transaction(conn, make_tx(category="groceries"))
    flags = integrity.run_checks(conn, make_tx(category="dining"))
    assert len(flags) == 1
    assert flags[0].source == "integrity:duplicate"


def test_same_content_three_times_flags_group(conn):
    ids = [repository.add_transaction(conn, make_tx()) for _ in range(3)]
    stored = repository.get_transaction(conn, ids[-1])
    flags = integrity.run_checks(conn, stored)
    assert len(flags) == 1
    assert sorted(flags[0].transaction_ids) == sorted(ids)
