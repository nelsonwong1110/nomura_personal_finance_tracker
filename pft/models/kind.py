"""Kind: whether a transaction is income or an expense."""

from __future__ import annotations

from enum import Enum

from pft.errors import ValidationError


class Kind(str, Enum):
    """Whether a transaction is income or an expense; amounts are always positive."""

    INCOME = "income"
    EXPENSE = "expense"

    @classmethod
    def parse(cls, value: str) -> "Kind":
        """Parse a user-supplied string into a Kind, raising a clean error."""
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            allowed = ", ".join(k for k in cls)
            raise ValidationError(
                f"kind must be one of: {allowed} (got {value!r})"
            ) from None
