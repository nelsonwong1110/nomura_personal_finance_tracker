"""Repository: all reads/writes of transactions and categories.

Transactions resolve category names to ids on write. An unknown category is a
clean error (foreign keys are enforced), never a silently-created ghost.
"""

from __future__ import annotations

import sqlite3
from typing import List, Optional

from pft.errors import NotFoundError, UnknownCategoryError
from pft.models.category import Category
from pft.models.kind import Kind
from pft.models.transaction import Transaction

_SELECT = """
SELECT t.id, t.kind, t.amount_cents, t.date, t.merchant,
       c.name AS category, t.source, t.ref, t.created_at
FROM transactions t
JOIN categories c ON c.id = t.category_id
"""


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
        clauses.append("c.name = 'uncategorized'")
    sql = _SELECT
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY t.date DESC, t.id DESC"
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_transaction(row) for row in rows]


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
