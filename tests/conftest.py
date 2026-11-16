"""Shared fixtures: an isolated config directory, config, database and CSV helper."""

from __future__ import annotations

import pytest

from pft.models.config import default_config, save_config
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
    config = default_config()
    config.db_path = str(pft_home / "pft.db")
    save_config(config)
    return config


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
