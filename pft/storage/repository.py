"""Repository: all reads/writes of transactions and categories.

Transactions resolve category names to ids on write. An unknown category is a
clean error (foreign keys are enforced), never a silently-created ghost.
"""

from __future__ import annotations

import sqlite3
from typing import List, Optional, Tuple

from pft.errors import NotFoundError, UnknownCategoryError, ValidationError
from pft.models.category import DEFAULT_CATEGORY, Category
from pft.models.filters import TransactionFilter
from pft.models.kind import Kind
from pft.models.summary import CategoryTotal, MonthTotal, Totals
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


def _where_clause(filters: TransactionFilter) -> Tuple[str, List[object]]:
    """Shared WHERE clause for transaction queries."""
    clauses: List[str] = []
    params: List[object] = []
    if filters.date_from:
        clauses.append("t.date >= ?")
        params.append(filters.date_from)
    if filters.date_to:
        clauses.append("t.date <= ?")
        params.append(filters.date_to)
    if filters.category:
        clauses.append("c.name = ?")
        params.append(filters.category)
    if filters.uncategorized:
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
    row = conn.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()
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


def add_transaction(
    conn: sqlite3.Connection, tx: Transaction, commit: bool = True
) -> int:
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


def add_if_new(
    conn: sqlite3.Connection, tx: Transaction, commit: bool = True
) -> Optional[int]:
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
    conn: sqlite3.Connection, filters: TransactionFilter = TransactionFilter()
) -> List[Transaction]:
    """List transactions, newest first (date desc, then entry order desc)."""
    where, params = _where_clause(filters)
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
    conn: sqlite3.Connection, filters: TransactionFilter = TransactionFilter()
) -> Totals:
    """Total income, spend and transaction count for the filtered scope."""
    where, params = _where_clause(filters)
    row = conn.execute(
        f"SELECT {_SELECT_KIND_SUMS}, COUNT(*) AS n " + _FROM + where,
        params,
    ).fetchone()
    return Totals(
        income_cents=int(row["income"]),
        spend_cents=int(row["spend"]),
        transaction_count=int(row["n"]),
    )


def summary_by_category(
    conn: sqlite3.Connection,
    filters: TransactionFilter = TransactionFilter(),
    *,
    kind: Kind,
) -> List[CategoryTotal]:
    """Category totals of one kind for the filtered scope, largest first."""
    where, params = _where_clause(filters)
    where += (" AND " if where else " WHERE ") + "t.kind = ?"
    params.append(kind.value)
    rows = conn.execute(
        """
        SELECT c.name AS name, SUM(t.amount_cents) AS total
        """
        + _FROM
        + where
        + """
        GROUP BY c.name
        ORDER BY total DESC, c.name ASC
        """,
        params,
    ).fetchall()
    return [
        CategoryTotal(name=row["name"], total_cents=int(row["total"])) for row in rows
    ]


def summary_monthly(
    conn: sqlite3.Connection, filters: TransactionFilter = TransactionFilter()
) -> List[MonthTotal]:
    """Month totals for the filtered scope, ascending by month."""
    where, params = _where_clause(filters)
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
        MonthTotal(
            month=row["month"],
            income_cents=int(row["income"]),
            spend_cents=int(row["spend"]),
        )
        for row in rows
    ]


def categorize(conn: sqlite3.Connection, tx_id: int, category: str) -> Transaction:
    """Reassign a transaction's category."""
    if get_transaction(conn, tx_id) is None:
        raise NotFoundError(f"transaction #{tx_id} not found")
    cid = category_id(conn, category)
    conn.execute("UPDATE transactions SET category_id = ? WHERE id = ?", (cid, tx_id))
    conn.commit()
    updated = get_transaction(conn, tx_id)
    assert updated is not None
    return updated


def count_transactions(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM transactions").fetchone()
    return int(row["n"])


def edit_transaction(conn: sqlite3.Connection, tx: Transaction) -> Transaction:
    """Overwrite kind, amount, date, merchant and category of stored row ``tx.id``.

    Provenance is preserved: the UPDATE does not touch source/ref, so a later
    re-import of the originating CSV skips this row and cannot resurrect the
    pre-edit content.
    """
    if tx.id is None:
        raise ValidationError("cannot edit an unsaved transaction")
    if get_transaction(conn, tx.id) is None:
        raise NotFoundError(f"transaction #{tx.id} not found")

    conn.execute(
        """
        UPDATE transactions
        SET kind = ?, amount_cents = ?, date = ?, merchant = ?, category_id = ?
        WHERE id = ?
        """,
        (
            tx.kind.value,
            tx.amount_cents,
            tx.date,
            tx.merchant.strip(),
            category_id(conn, tx.category),
            tx.id,
        ),
    )
    conn.commit()
    updated = get_transaction(conn, tx.id)
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
