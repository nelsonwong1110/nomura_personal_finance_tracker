"""Repository: all reads/writes of transactions and categories.

Transactions resolve category names to ids on write. An unknown category is a
clean error (foreign keys are enforced), never a silently-created ghost.
"""

from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional, Tuple

from pft.errors import NotFoundError, UnknownCategoryError, ValidationError
from pft.models.category import DEFAULT_CATEGORY, Category
from pft.models.kind import Kind
from pft.models.transaction import Transaction

_FROM = """
FROM transactions t
JOIN categories c ON c.id = t.category_id
"""

_SELECT = (
    """
SELECT t.id, t.kind, t.amount_cents, t.date, t.merchant,
       c.name AS category, t.source, t.ref, t.created_at
"""
    + _FROM
)

_SELECT_KIND_SUMS = """
COALESCE(SUM(CASE WHEN t.kind = 'income' THEN t.amount_cents END), 0) AS income,
COALESCE(SUM(CASE WHEN t.kind = 'expense' THEN t.amount_cents END), 0) AS spend
"""


def _filters(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category: Optional[str] = None,
    uncategorized: bool = False,
) -> Tuple[str, List[object]]:
    """Shared WHERE clause for transaction queries."""
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
    if uncategorized:
        clauses.append("c.name = ?")
        params.append(DEFAULT_CATEGORY)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def _row_to_transaction(row: sqlite3.Row) -> Transaction:
    return Transaction(
        id=row["id"],
        kind=Kind(row["kind"]),
        amount_cents=row["amount_cents"],
        date=row["date"],
        merchant=row["merchant"],
        category=row["category"],
        source=row["source"],
        ref=row["ref"],
        created_at=row["created_at"],
    )


def category_id(conn: sqlite3.Connection, name: str) -> int:
    """Resolve a category name to its id, or raise UnknownCategoryError."""
    row = conn.execute(
        "SELECT id FROM categories WHERE name = ?", (name,)
    ).fetchone()
    if row is None:
        raise UnknownCategoryError(
            f"unknown category {name!r}; add it first with: pft category add {name!r}"
        )
    return row["id"]


def category_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute("SELECT 1 FROM categories WHERE name = ?", (name,)).fetchone()
        is not None
    )


def add_category(conn: sqlite3.Connection, name: str) -> bool:
    """Add a category. Returns True if created, False if it already existed."""
    cleaned = str(name).strip()
    if not cleaned:
        raise UnknownCategoryError("category name must not be empty")
    cursor = conn.execute(
        "INSERT OR IGNORE INTO categories(name) VALUES (?)", (cleaned,)
    )
    conn.commit()
    return cursor.rowcount > 0


def list_categories(conn: sqlite3.Connection) -> List[Category]:
    rows = conn.execute("SELECT id, name FROM categories ORDER BY id").fetchall()
    return [Category(id=row["id"], name=row["name"]) for row in rows]


def add_transaction(conn: sqlite3.Connection, tx: Transaction, commit: bool = True) -> int:
    """Insert a transaction. Raises UnknownCategoryError for an unknown category."""
    cid = category_id(conn, tx.category)
    cursor = conn.execute(
        """
        INSERT INTO transactions
            (kind, amount_cents, date, merchant, category_id, source, ref)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tx.kind.value,
            tx.amount_cents,
            tx.date,
            tx.merchant.strip(),
            cid,
            tx.source,
            tx.ref,
        ),
    )
    if commit:
        conn.commit()
    return int(cursor.lastrowid)


def add_if_new(conn: sqlite3.Connection, tx: Transaction, commit: bool = True) -> Optional[int]:
    """Insert unless this exact provenance (source, ref) was already ingested.

    Content-identical rows with different provenance are inserted: two genuine
    identical purchases must not collapse into one. Returns None when skipped.
    """
    if tx.source is not None and tx.ref is not None:
        existing = conn.execute(
            "SELECT id FROM transactions WHERE source = ? AND ref = ?",
            (tx.source, tx.ref),
        ).fetchone()
        if existing is not None:
            return None
    return add_transaction(conn, tx, commit=commit)


def get_transaction(conn: sqlite3.Connection, tx_id: int) -> Optional[Transaction]:
    row = conn.execute(_SELECT + " WHERE t.id = ?", (tx_id,)).fetchone()
    return _row_to_transaction(row) if row else None


def list_transactions(
    conn: sqlite3.Connection,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category: Optional[str] = None,
    uncategorized: bool = False,
) -> List[Transaction]:
    """List transactions, newest first (date desc, then entry order desc)."""
    where, params = _filters(date_from, date_to, category, uncategorized)
    rows = conn.execute(
        _SELECT + where + " ORDER BY t.date DESC, t.id DESC", params
    ).fetchall()
    return [_row_to_transaction(row) for row in rows]


def find_duplicate_ids(
    conn: sqlite3.Connection,
    kind: Kind,
    amount_cents: int,
    date: str,
    merchant: str,
) -> List[int]:
    """Ids of stored transactions with the same kind, amount, date and merchant."""
    rows = conn.execute(
        """
        SELECT id FROM transactions
        WHERE kind = ? AND amount_cents = ? AND date = ? AND merchant = ?
        ORDER BY id
        """,
        (kind.value, amount_cents, date, merchant.strip()),
    ).fetchall()
    return [row["id"] for row in rows]


def summary_totals(
    conn: sqlite3.Connection,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category: Optional[str] = None,
) -> Dict[str, int]:
    """Total income, spend and transaction count for the filtered scope."""
    where, params = _filters(date_from, date_to, category)
    row = conn.execute(
        f"SELECT {_SELECT_KIND_SUMS}, COUNT(*) AS n " + _FROM + where,
        params,
    ).fetchone()
    return {
        "income": int(row["income"]),
        "spend": int(row["spend"]),
        "count": int(row["n"]),
    }


def summary_by_category(
    conn: sqlite3.Connection,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category: Optional[str] = None,
) -> List[Tuple[str, str, int]]:
    """(category name, kind, total) rows for the filtered scope, largest first."""
    where, params = _filters(date_from, date_to, category)
    rows = conn.execute(
        """
        SELECT c.name AS name, t.kind AS kind, SUM(t.amount_cents) AS total
        """
        + _FROM
        + where
        + """
        GROUP BY c.name, t.kind
        ORDER BY total DESC, c.name ASC
        """,
        params,
    ).fetchall()
    return [(row["name"], row["kind"], int(row["total"])) for row in rows]


def summary_monthly(
    conn: sqlite3.Connection,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category: Optional[str] = None,
) -> List[Tuple[str, int, int]]:
    """(month, income, spend) rows for the filtered scope, ascending by month."""
    where, params = _filters(date_from, date_to, category)
    rows = conn.execute(
        f"SELECT substr(t.date, 1, 7) AS month, {_SELECT_KIND_SUMS} "
        + _FROM
        + where
        + """
        GROUP BY month
        ORDER BY month ASC
        """,
        params,
    ).fetchall()
    return [
        (row["month"], int(row["income"]), int(row["spend"])) for row in rows
    ]


def categorize(conn: sqlite3.Connection, tx_id: int, category: str) -> Transaction:
    """Reassign a transaction's category."""
    if get_transaction(conn, tx_id) is None:
        raise NotFoundError(f"transaction #{tx_id} not found")
    cid = category_id(conn, category)
    conn.execute(
        "UPDATE transactions SET category_id = ? WHERE id = ?", (cid, tx_id)
    )
    conn.commit()
    updated = get_transaction(conn, tx_id)
    assert updated is not None
    return updated


def count_transactions(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM transactions").fetchone()
    return int(row["n"])


def edit_transaction(
    conn: sqlite3.Connection,
    tx_id: int,
    *,
    kind: Optional[Kind] = None,
    amount_cents: Optional[int] = None,
    date: Optional[str] = None,
    merchant: Optional[str] = None,
    category: Optional[str] = None,
) -> Transaction:
    """Update fields of a transaction; fields left as None are unchanged.

    Provenance is preserved, so a later re-import of the originating CSV skips
    this row and cannot resurrect the pre-edit content.
    """
    current = get_transaction(conn, tx_id)
    if current is None:
        raise NotFoundError(f"transaction #{tx_id} not found")

    new_kind = kind or current.kind
    new_amount = amount_cents if amount_cents is not None else current.amount_cents
    new_date = date or current.date
    new_merchant = merchant.strip() if merchant is not None else current.merchant
    new_category = category or current.category
    if not new_merchant:
        raise ValidationError("merchant must not be empty")

    conn.execute(
        """
        UPDATE transactions
        SET kind = ?, amount_cents = ?, date = ?, merchant = ?, category_id = ?
        WHERE id = ?
        """,
        (
            new_kind.value,
            new_amount,
            new_date,
            new_merchant,
            category_id(conn, new_category),
            tx_id,
        ),
    )
    conn.commit()
    updated = get_transaction(conn, tx_id)
    assert updated is not None
    return updated


def delete_transaction(conn: sqlite3.Connection, tx_id: int) -> Transaction:
    """Remove a transaction, returning the deleted row."""
    current = get_transaction(conn, tx_id)
    if current is None:
        raise NotFoundError(f"transaction #{tx_id} not found")
    conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    conn.commit()
    return current
