"""CSV import: parsing, provenance idempotency and all-or-nothing errors."""

from __future__ import annotations

import pytest

from pft.errors import CsvImportError
from pft.services.importer import import_csv
from pft.storage import repository

HEADER = "kind,amount,date,merchant,category\n"
ROWS = (
    "expense,42.50,2026-10-02,Safeway,groceries\n"
    "income,3200.00,2026-10-01,Acme Corp,income\n"
    "expense,15.75,2026-10-03,Chipotle,dining\n"
)


def test_import_counts(write_csv, conn, cfg):
    path = write_csv("bank.csv", HEADER + ROWS)
    result = import_csv(conn, path, cfg)
    assert result.imported == 3
    assert result.skipped == 0
    assert repository.count_transactions(conn) == 3


def test_reimport_is_idempotent(write_csv, conn, cfg):
    path = write_csv("bank.csv", HEADER + ROWS)
    import_csv(conn, path, cfg)
    result = import_csv(conn, path, cfg)
    assert result.imported == 0
    assert result.skipped == 3
    assert repository.count_transactions(conn) == 3


def test_append_imports_only_new_rows(write_csv, conn, cfg):
    path = write_csv("bank.csv", HEADER + ROWS)
    import_csv(conn, path, cfg)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("expense,9.99,2026-10-04,Bakery,dining\n")
    result = import_csv(conn, path, cfg)
    assert result.imported == 1
    assert result.skipped == 3
    assert repository.count_transactions(conn) == 4


def test_identical_rows_in_one_file_are_kept(write_csv, conn, cfg):
    """Two genuinely identical purchases must not collapse into one."""
    content = (
        HEADER
        + "expense,42.50,2026-10-02,Safeway,groceries\n"
        + "expense,42.50,2026-10-02,Safeway,groceries\n"
    )
    path = write_csv("bank.csv", content)
    result = import_csv(conn, path, cfg)
    assert result.imported == 2
    assert len(set(result.transaction_ids)) == 2
    assert repository.count_transactions(conn) == 2


def test_same_content_from_different_file_is_imported(write_csv, conn, cfg):
    first = write_csv("bank1.csv", HEADER + ROWS)
    second = write_csv("bank2.csv", HEADER + ROWS)
    import_csv(conn, first, cfg)
    result = import_csv(conn, second, cfg)
    assert result.imported == 3
    assert repository.count_transactions(conn) == 6


def test_missing_required_column(write_csv, conn, cfg):
    path = write_csv("bad.csv", "kind,amount,date\n" + "expense,1.00,2026-10-01\n")
    with pytest.raises(CsvImportError, match="merchant"):
        import_csv(conn, path, cfg)


def test_bad_row_aborts_whole_import(write_csv, conn, cfg):
    content = HEADER + ROWS + "expense,not-a-number,2026-10-04,Bakery,dining\n"
    path = write_csv("bad.csv", content)
    with pytest.raises(CsvImportError, match="row 5"):
        import_csv(conn, path, cfg)
    assert repository.count_transactions(conn) == 0


def test_bad_date_names_row(write_csv, conn, cfg):
    content = HEADER + "expense,1.00,10/01/2026,Bakery,dining\n"
    path = write_csv("bad.csv", content)
    with pytest.raises(CsvImportError, match="row 2"):
        import_csv(conn, path, cfg)


def test_unknown_category_names_row(write_csv, conn, cfg):
    content = HEADER + "expense,1.00,2026-10-01,Bakery,groceris\n"
    path = write_csv("bad.csv", content)
    with pytest.raises(CsvImportError, match="row 2.*groceris"):
        import_csv(conn, path, cfg)


def test_blank_lines_are_skipped(write_csv, conn, cfg):
    content = HEADER + "\n" + ROWS + "\n"
    path = write_csv("bank.csv", content)
    result = import_csv(conn, path, cfg)
    assert result.imported == 3


def test_category_column_optional(write_csv, conn, cfg):
    path = write_csv("bank.csv", "kind,amount,date,merchant\n" + "expense,5.00,2026-10-01,Kiosk\n")
    result = import_csv(conn, path, cfg)
    assert result.imported == 1
    tx = repository.get_transaction(conn, result.transaction_ids[0])
    assert tx.category == "uncategorized"


def test_missing_file(conn, cfg):
    with pytest.raises(CsvImportError, match="not found"):
        import_csv(conn, "/does/not/exist.csv", cfg)
