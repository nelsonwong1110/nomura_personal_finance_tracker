"""Query filters for transaction listing and summary aggregation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TransactionFilter:
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    category: Optional[str] = None
    uncategorized: bool = False
