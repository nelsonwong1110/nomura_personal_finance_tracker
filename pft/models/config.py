"""Config: user preferences stored as JSON in the config directory.

The config file lives at ``$PFT_HOME/config.json`` (default ``~/.pft/config.json``).
``PFT_HOME`` exists so tests and multiple profiles can point elsewhere.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pft.errors import ConfigError
from pft.models.rule import Rule

DEFAULT_CATEGORIES = [
    "uncategorized",
    "groceries",
    "rent",
    "dining",
    "transport",
    "utilities",
    "entertainment",
    "income",
]

REQUIRED_CATEGORY = "uncategorized"


def config_dir() -> Path:
    """Directory holding config.json and, by default, the database."""
    override = os.environ.get("PFT_HOME")
    return Path(override) if override else Path.home() / ".pft"


def config_path() -> Path:
    """Full path to the config file."""
    return config_dir() / "config.json"


def default_db_path() -> str:
    """Default SQLite database path (inside the config directory)."""
    return str(config_dir() / "pft.db")


def _validate_decimal_places(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError("decimal_places must be an integer between 0 and 4")
    if not 0 <= value <= 4:
        raise ConfigError("decimal_places must be between 0 and 4")
    return value


def _validate_date_format(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ConfigError("date_format must be a non-empty string")
    try:
        datetime.now().strftime(value)
    except ValueError as exc:
        raise ConfigError(f"invalid date_format {value!r}: {exc}") from None
    return value


def _validate_categories(value: Any) -> List[str]:
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]
    if not isinstance(value, list):
        raise ConfigError("default_categories must be a list of strings")
    names: List[str] = []
    for item in value:
        name = str(item).strip()
        if name and name not in names:
            names.append(name)
    if not names:
        raise ConfigError("default_categories must not be empty")
    if REQUIRED_CATEGORY not in names:
        names.insert(0, REQUIRED_CATEGORY)
    return names


@dataclass
class Config:
    """User preferences. Values are validated on construction from dicts."""

    db_path: str = field(default_factory=default_db_path)
    currency: str = "USD"
    currency_symbol: str = "$"
    decimal_places: int = 2
    date_format: str = "%Y-%m-%d"
    default_categories: List[str] = field(
        default_factory=lambda: list(DEFAULT_CATEGORIES)
    )
    rules: List[Rule] = field(default_factory=list)

    @property
    def resolved_db_path(self) -> str:
        """Database path with ``~`` expanded."""
        return str(Path(os.path.expanduser(self.db_path)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "db_path": self.db_path,
            "currency": self.currency,
            "currency_symbol": self.currency_symbol,
            "decimal_places": self.decimal_places,
            "date_format": self.date_format,
            "default_categories": list(self.default_categories),
            "rules": [rule.to_dict() for rule in self.rules],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        if not isinstance(data, dict):
            raise ConfigError("config must be a JSON object")
        defaults = cls()
        db_path = data.get("db_path", defaults.db_path)
        if not isinstance(db_path, str) or not db_path.strip():
            raise ConfigError("db_path must be a non-empty string")
        currency = data.get("currency", defaults.currency)
        if not isinstance(currency, str) or not currency.strip():
            raise ConfigError("currency must be a non-empty string")
        symbol = data.get("currency_symbol", defaults.currency_symbol)
        if not isinstance(symbol, str):
            raise ConfigError("currency_symbol must be a string")
        rules = [Rule.from_dict(item) for item in data.get("rules", [])]
        return cls(
            db_path=db_path,
            currency=currency.strip().upper(),
            currency_symbol=symbol,
            decimal_places=_validate_decimal_places(
                data.get("decimal_places", defaults.decimal_places)
            ),
            date_format=_validate_date_format(
                data.get("date_format", defaults.date_format)
            ),
            default_categories=_validate_categories(
                data.get("default_categories", list(DEFAULT_CATEGORIES))
            ),
            rules=rules,
        )


def default_config() -> Config:
    """A Config with all defaults."""
    return Config()


def load_config(path: Optional[Path] = None) -> Optional[Config]:
    """Load config from disk; returns None if the file does not exist."""
    target = Path(path) if path else config_path()
    if not target.is_file():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"could not read config {target}: {exc}") from None
    return Config.from_dict(data)


def save_config(config: Config, path: Optional[Path] = None) -> Path:
    """Persist config as JSON, creating parent directories as needed."""
    target = Path(path) if path else config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(config.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


SETTABLE_KEYS = {
    "db_path",
    "currency",
    "currency_symbol",
    "decimal_places",
    "date_format",
    "default_categories",
}


def coerce_setting(key: str, raw_value: str) -> Any:
    """Validate and coerce a ``config set <key> <value>`` argument."""
    if key not in SETTABLE_KEYS:
        raise ConfigError(
            f"unknown setting {key!r}; settable keys: {', '.join(sorted(SETTABLE_KEYS))}"
        )
    if key == "decimal_places":
        try:
            return _validate_decimal_places(int(raw_value))
        except ValueError:
            raise ConfigError("decimal_places must be an integer between 0 and 4") from None
    if key == "default_categories":
        return _validate_categories(raw_value)
    if key == "date_format":
        return _validate_date_format(raw_value)
    if key == "currency":
        if not raw_value.strip():
            raise ConfigError("currency must be a non-empty string")
        return raw_value.strip().upper()
    if key == "db_path":
        if not raw_value.strip():
            raise ConfigError("db_path must be a non-empty string")
        return raw_value.strip()
    return raw_value
