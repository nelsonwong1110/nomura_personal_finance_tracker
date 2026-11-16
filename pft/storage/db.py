"""SQLite connection and schema management.

The database file is created at runtime in the user's config directory (or the
path given by --db). It is user data, never part of the source deliverable.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS transactions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    kind         TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    date         TEXT NOT NULL,
    merchant     TEXT NOT NULL,
    category_id  INTEGER NOT NULL REFERENCES categories(id),
    source       TEXT,
    ref          TEXT,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_provenance
    ON transactions(source, ref) WHERE source IS NOT NULL;
"""


def connect(path: str, categories: Optional[Iterable[str]] = None) -> sqlite3.Connection:
    """Open (and if necessary create) the database, seeding categories.

    ``categories`` are inserted if missing; existing data is never modified.
    """
    db_path = Path(path).expanduser()
    if str(db_path) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    if categories:
        seed_categories(conn, categories)
    conn.commit()
    return conn


def seed_categories(conn: sqlite3.Connection, names: Iterable[str]) -> None:
    """Insert category names that do not exist yet (idempotent)."""
    for name in names:
        cleaned = str(name).strip()
        if cleaned:
            conn.execute(
                "INSERT OR IGNORE INTO categories(name) VALUES (?)", (cleaned,)
            )
    conn.commit()
