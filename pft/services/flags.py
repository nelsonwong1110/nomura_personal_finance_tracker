"""Entry-time flag collection: integrity checks plus configured field rules."""

from __future__ import annotations

import sqlite3
from typing import List

from pft.models.config import Config
from pft.models.flag import Flag
from pft.models.transaction import Transaction
from pft.services.integrity import _run_checks
from pft.services.rules import _run_rules


def collect_flags(conn: sqlite3.Connection, cfg: Config, tx: Transaction) -> List[Flag]:
    """All flags for one transaction: integrity checks and field rules."""
    return _run_checks(conn, tx) + _run_rules(cfg.rules, tx, cfg)
