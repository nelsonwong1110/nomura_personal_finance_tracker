"""Integrity checks: data-integrity analyses over transactions.

These are relational checks (they compare rows), unlike field rules. They are
implemented as an abstract base class so more checks can be added by writing a
concrete class and appending it to INTEGRITY_CHECKS.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from typing import List, Type

from pft.models.flag import Flag
from pft.models.transaction import Transaction
from pft.storage import repository


class IntegrityCheck(ABC):
    """A data-integrity check over a transaction and its stored peers."""

    name: str = ""

    @abstractmethod
    def check(self, conn: sqlite3.Connection, tx: Transaction) -> List[Flag]:
        """Return flags for ``tx`` (which may or may not be stored yet)."""


class CheckDuplicateRule(IntegrityCheck):
    """Flag transactions whose (kind, amount, date, merchant) appear more than once.

    This is the one rule-based analysis required by the exercise. It is
    relational: duplicates are two distinct records with identical content.
    Imported duplicates survive import (provenance differs), so they get flagged
    here for the human to judge: double entry, or genuinely two identical buys.

    Category is deliberately not part of the criteria: it is mutable, derived
    metadata, so recategorizing a row must not hide a double entry.
    """

    name = "duplicate"

    def check(self, conn: sqlite3.Connection, tx: Transaction) -> List[Flag]:
        ids = repository.find_duplicate_ids(
            conn, tx.kind, tx.amount_cents, tx.date, tx.merchant
        )
        others = [tx_id for tx_id in ids if tx_id != tx.id]
        if not others:
            return []
        ids = ([tx.id] if tx.id is not None else []) + others
        id_list = ", ".join(f"#{i}" for i in ids)
        if tx.id is None:
            message = (
                f"possible duplicate of transaction(s) {id_list} "
                f"(same kind, amount, date and merchant)"
            )
        else:
            message = (
                f"duplicate group {id_list} — "
                f"same kind, amount, date and merchant"
            )
        return [
            Flag(
                source=f"integrity:{self.name}",
                message=message,
                transaction_ids=ids,
            )
        ]


INTEGRITY_CHECKS: List[Type[IntegrityCheck]] = [CheckDuplicateRule]


def run_checks(conn: sqlite3.Connection, tx: Transaction) -> List[Flag]:
    """Run every registered integrity check against one transaction."""
    flags: List[Flag] = []
    for check_class in INTEGRITY_CHECKS:
        flags.extend(check_class().check(conn, tx))
    return flags
