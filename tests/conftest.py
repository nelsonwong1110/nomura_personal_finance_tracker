"""Shared fixtures: an isolated config directory, config, database, CSV helper
and the common transaction factory."""

from __future__ import annotations

import pytest

from pft.models.config import Config, save_config
from pft.models.kind import Kind
from pft.models.transaction import Transaction
from pft.storage import db as db_module


@pytest.fixture
def pft_home(tmp_path, monkeypatch):
    """Point PFT_HOME at an isolated directory so tests never touch ~/.pft."""
    home = tmp_path / "pft_home"
    monkeypatch.setenv("PFT_HOME", str(home))
    return home


@pytest.fixture
def cfg(pft_home):
    """A saved default config inside the isolated PFT_HOME."""
    config = Config()
    config.db_path = str(pft_home / "pft.db")
    save_config(config)
    return config


@pytest.fixture
def make_tx():
    """Factory for transactions with sensible defaults, override any field."""

    def _make(**overrides):
        values = dict(
            kind=Kind.EXPENSE,
            amount_cents=1250,
            date="2026-10-02",
            merchant="FreshMart",
            category="groceries",
        )
        values.update(overrides)
        return Transaction(**values)

    return _make


@pytest.fixture
def conn(cfg):
    """A connected, schema-created, category-seeded database."""
    connection = db_module.connect(cfg.resolved_db_path, cfg.default_categories)
    yield connection
    connection.close()


@pytest.fixture
def write_csv(tmp_path):
    """Write a CSV file into the test temp dir and return its path."""

    def _write(name: str, content: str) -> str:
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        return str(path)

    return _write
