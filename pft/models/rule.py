"""Rule: a user-defined, flag-only condition over transaction fields."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from pft.errors import ConfigError


@dataclass(frozen=True)
class Rule:
    """A flag-only rule: if ``expression`` is true for a transaction, flag it.

    ``expression`` uses Python boolean syntax over the fields ``kind``,
    ``amount`` (in currency units), ``date``, ``merchant`` and ``category``.
    It is validated and evaluated by ``pft.services.rules`` — never eval().
    """

    id: str
    description: str
    expression: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "id": self.id,
            "description": self.description,
            "expression": self.expression,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Rule":
        if not isinstance(data, dict):
            raise ConfigError(f"rule must be an object, got {type(data).__name__}")
        missing = [
            key for key in ("id", "description", "expression") if key not in data
        ]
        if missing:
            raise ConfigError(f"rule is missing field(s): {', '.join(missing)}")
        return cls(
            id=str(data["id"]),
            description=str(data["description"]),
            expression=str(data["expression"]),
        )
