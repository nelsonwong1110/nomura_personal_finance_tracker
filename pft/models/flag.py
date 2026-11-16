"""Flag: a finding emitted by an integrity check or a rule."""

from __future__ import annotations

from typing import List, NamedTuple


class Flag(NamedTuple):
    """One finding. ``source`` names the producing subsystem (e.g. 'integrity:duplicate'
    or 'rule:1'); ``transaction_ids`` are the affected transactions (may be empty for
    a not-yet-saved candidate)."""

    source: str
    message: str
    transaction_ids: List[int]
