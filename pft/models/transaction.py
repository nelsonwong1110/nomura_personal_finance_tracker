"""Transaction: one income or expense record."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from pft.errors import AmountError
from pft.models.kind import Kind


@dataclass(frozen=True)
class Transaction:
    """A single income or expense entry for an individual user.

    ``category`` holds the category name (resolved to an id at storage time).
    ``source``/``ref`` hold provenance: where the record came from, used for
    import idempotency. They are None for hand-edited data.
    """

    kind: Kind
    amount_cents: int
    date: str  # ISO YYYY-MM-DD
    merchant: str
    category: str = "uncategorized"
    source: Optional[str] = None
    ref: Optional[str] = None
    id: Optional[int] = None
    created_at: Optional[str] = None

    def __post_init__(self) -> None:
        if self.amount_cents <= 0:
            raise AmountError("amount must be positive")
        if not self.merchant or not self.merchant.strip():
            raise ValueError("merchant must not be empty")
        if not self.category or not self.category.strip():
            raise ValueError("category must not be empty")
