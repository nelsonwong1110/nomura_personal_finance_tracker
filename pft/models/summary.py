"""Summary aggregate value types shared by the storage and service layers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class CategoryTotal:
    name: str
    total_cents: int


@dataclass(frozen=True)
class MonthTotal:
    month: str  # YYYY-MM
    income_cents: int
    spend_cents: int


@dataclass(frozen=True)
class Totals:
    income_cents: int
    spend_cents: int
    transaction_count: int


@dataclass(frozen=True)
class Summary:
    total_income_cents: int
    total_spend_cents: int
    transaction_count: int
    spend_by_category: List[CategoryTotal]
    income_by_category: List[CategoryTotal]
    monthly: List[MonthTotal]

    @property
    def net_cents(self) -> int:
        return self.total_income_cents - self.total_spend_cents
