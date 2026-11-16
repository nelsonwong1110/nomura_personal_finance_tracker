"""First-run setup wizard.

Runs automatically when no config file exists, or explicitly via ``pft init``.
Prompts for each setting (Enter accepts the default), writes the config, creates
and seeds the database, and optionally imports a seed CSV.
"""

from __future__ import annotations

from typing import Callable

from pft.errors import ConfigError
from pft.models.config import (
    Config,
    config_path,
    default_config,
    load_config,
    save_config,
)
from pft.services.importer import import_csv
from pft.storage import db


def _ask(prompt: str, default: str = "") -> str:
    try:
        answer = input(f"{prompt} [{default}]: ").strip()
    except EOFError:
        return default
    return answer or default


def run_init(
    ask: Callable[[str, str], str] = None,
    out: Callable[[str], None] = print,
    ask_seed: bool = True,
) -> Config:
    """Run the setup wizard. Existing config values (if any) are the defaults."""
    ask = ask or _ask
    target = config_path()
    existing = load_config(target) or default_config()

    out("Personal Finance Tracker — setup")
    out("Press Enter to accept the value in brackets.")
    db_path = ask("Database path", existing.db_path)
    currency = ask("Currency code", existing.currency)
    symbol = ask("Currency symbol", existing.currency_symbol)
    decimals_raw = ask("Decimal places (0-4)", str(existing.decimal_places))
    date_format = ask("Date display format", existing.date_format)
    categories_raw = ask(
        "Default categories (comma-separated)", ",".join(existing.default_categories)
    )
    seed_csv = ask("Seed CSV to import (blank to skip)", "") if ask_seed else ""

    try:
        decimals = int(decimals_raw)
    except ValueError:
        raise ConfigError(
            f"decimal places must be an integer, got {decimals_raw!r}"
        ) from None

    cfg = Config.from_dict(
        {
            "db_path": db_path,
            "currency": currency,
            "currency_symbol": symbol,
            "decimal_places": decimals,
            "date_format": date_format,
            "default_categories": categories_raw,
            "rules": [rule.to_dict() for rule in existing.rules],
        }
    )
    saved = save_config(cfg)

    conn = db.connect(cfg.resolved_db_path, cfg.default_categories)
    try:
        out(f"Config saved to {saved}")
        if seed_csv:
            result = import_csv(conn, seed_csv, cfg)
            out(
                f"Seeded {result.imported} transaction(s), "
                f"skipped {result.skipped} already imported."
            )
    finally:
        conn.close()
    return cfg
