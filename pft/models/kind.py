"""Kind: whether a transaction is income or an expense."""

from __future__ import annotations

from enum import Enum


class Kind(str, Enum):
    """Direction of a transaction's money flow. Amounts are always positive."""

    INCOME = "income"
    EXPENSE = "expense"

    @classmethod
    def parse(cls, value: str) -> "Kind":
        """Parse a user-supplied string into a Kind, raising a clean error."""
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            allowed = ", ".join(k.value for k in cls)
            raise ValueError(f"kind must be one of: {allowed} (got {value!r})") from None
