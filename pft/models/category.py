"""Category: a classification of transactions (e.g. groceries, rent)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Category:
    name: str
    id: Optional[int] = None
