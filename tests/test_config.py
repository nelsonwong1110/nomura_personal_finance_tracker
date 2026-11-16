"""Config loading, saving and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from pft.errors import ConfigError
from pft.models.config import Config, config_path, load_config, save_config


def test_missing_config_returns_none(pft_home):
    assert load_config() is None


def test_save_and_load_roundtrip(cfg):
    loaded = load_config()
    assert loaded is not None
    assert loaded.db_path == cfg.db_path
    assert loaded.default_categories == cfg.default_categories


def test_config_path_follows_pft_home(pft_home):
    assert config_path() == pft_home / "config.json"


def test_default_categories_always_include_uncategorized():
    config = Config.from_dict({"default_categories": ["food", "food", "rent"]})
    assert config.default_categories == ["uncategorized", "food", "rent"]


def test_default_categories_accept_comma_string():
    config = Config.from_dict({"default_categories": "a, b ,a"})
    assert config.default_categories == ["uncategorized", "a", "b"]


def test_invalid_rules_rejected():
    with pytest.raises(ConfigError):
        Config.from_dict({"rules": [{"id": "1"}]})


def test_resolved_db_path_expands_home(pft_home):
    config = Config()
    config.db_path = "~/data/pft.db"
    assert config.resolved_db_path == str(Path.home() / "data" / "pft.db")


def test_config_set_db_path_survives_save(cfg):
    cfg.db_path = "/tmp/elsewhere.db"
    save_config(cfg)
    assert load_config().db_path == "/tmp/elsewhere.db"


def test_default_config_ships_one_rule():
    config = Config()
    assert len(config.rules) == 1
    assert config.rules[0].description == "Expensive grocery"


def test_missing_rules_key_gets_default():
    assert len(Config.from_dict({}).rules) == 1


def test_explicit_empty_rules_are_not_reseeded():
    """Removing every rule must survive a reload."""
    assert Config.from_dict({"rules": []}).rules == []
