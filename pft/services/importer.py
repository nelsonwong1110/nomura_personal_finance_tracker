"""CSV import with provenance-keyed idempotency.

Each row's provenance is ``(source=file path, ref=hash of the row's content plus
its occurrence number within the file)``. Re-importing the same file therefore
skips everything; appending rows imports only the new ones (the path stays the
same, and only new refs appear); and *content-identical* rows are still kept as
distinct records (occurrence numbers differ), so genuine duplicate purchases are
preserved and can be flagged by the integrity check.

The source is the resolved absolute path rather than the basename, so two
different files that happen to share a name do not collide. The trade-off: moving
or renaming a file gives its rows new provenance, so they would be imported again.
(Content hashes are deliberately not used for the source: appending a row would
change the hash and re-import the entire file as duplicates.)

Import is all-or-nothing: any invalid row aborts the whole file with a message
naming the row, so a typo never leaves a half-imported file behind.
"""

from __future__ import annotations

import csv
import hashlib
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, List

from pft.errors import CsvImportError, PftError
from pft.models.amount import parse_amount
from pft.models.category import DEFAULT_CATEGORY
from pft.models.config import Config
from pft.models.dates import validate_iso_date
from pft.models.kind import Kind
from pft.models.transaction import Transaction
from pft.storage import repository

REQUIRED_COLUMNS = ("kind", "amount", "date", "merchant")
OPTIONAL_COLUMNS = ("category",)
KNOWN_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS


@dataclass(frozen=True)
class ImportResult:
    imported: int
    skipped: int
    transaction_ids: List[int]


def _canonical(tx: Transaction) -> str:
    return "|".join(
        [
            tx.kind.value,
            str(tx.amount_cents),
            tx.date,
            tx.merchant,
            tx.category,
        ]
    )


def _make_ref(canonical: str, occurrence: int) -> str:
    payload = f"{canonical}#{occurrence}".encode("utf-8")
    return hashlib.sha1(payload).hexdigest()


def _row_error(lineno: int, message: str) -> CsvImportError:
    return CsvImportError(f"row {lineno}: {message}")


def _cell(row: List[str], index: Dict[str, int], column: str) -> str:
    position = index.get(column)
    if position is None or position >= len(row):
        return ""
    return row[position].strip()


def _row_to_transaction(
    conn: sqlite3.Connection,
    row: List[str],
    index: Dict[str, int],
    lineno: int,
) -> Transaction:
    for column in REQUIRED_COLUMNS:
        if not _cell(row, index, column):
            raise _row_error(lineno, f"missing value for {column!r}")

    try:
        kind = Kind.parse(_cell(row, index, "kind"))
    except PftError as exc:
        raise _row_error(lineno, str(exc)) from None

    category = _cell(row, index, "category") or DEFAULT_CATEGORY
    if not repository.category_exists(conn, category):
        raise _row_error(
            lineno,
            f"unknown category {category!r} "
            f"(add it with: pft category add {category!r})",
        )

    try:
        return Transaction(
            kind=kind,
            amount_cents=parse_amount(_cell(row, index, "amount")),
            date=validate_iso_date(_cell(row, index, "date")),
            merchant=_cell(row, index, "merchant"),
            category=category,
        )
    except PftError as exc:
        raise _row_error(lineno, str(exc)) from None


def import_csv(conn: sqlite3.Connection, path: str, cfg: Config) -> ImportResult:
    """Import transactions from a CSV file. See module docstring for semantics."""
    csv_path = Path(path).expanduser()
    if not csv_path.is_file():
        raise CsvImportError(f"CSV file not found: {path}")

    try:
        handle = csv_path.open(newline="", encoding="utf-8-sig")
    except OSError as exc:
        raise CsvImportError(f"could not open {path}: {exc}") from None

    with handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            raise CsvImportError(f"CSV file is empty: {path}") from None

        normalized = [column.strip().lower() for column in header]
        missing = [c for c in REQUIRED_COLUMNS if c not in normalized]
        if missing:
            raise CsvImportError(
                f"CSV missing required column(s): {', '.join(missing)} "
                f"(found: {', '.join(header)})"
            )
        index = {
            name: normalized.index(name) for name in KNOWN_COLUMNS if name in normalized
        }

        occurrences: Dict[str, int] = {}
        staged: List[Transaction] = []
        for lineno, row in enumerate(reader, start=2):
            if not row or all(not cell.strip() for cell in row):
                continue
            tx = _row_to_transaction(conn, row, index, lineno)
            canonical = _canonical(tx)
            occurrences[canonical] = occurrences.get(canonical, 0) + 1
            staged.append(
                replace(
                    tx,
                    source=str(csv_path.resolve()),
                    ref=_make_ref(canonical, occurrences[canonical]),
                )
            )

    imported_ids: List[int] = []
    skipped = 0
    try:
        for tx in staged:
            new_id = repository.add_if_new(conn, tx, commit=False)
            if new_id is None:
                skipped += 1
            else:
                imported_ids.append(new_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return ImportResult(
        imported=len(imported_ids), skipped=skipped, transaction_ids=imported_ids
    )
