"""Config loading, saving and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from pft.errors import ConfigError
from pft.models.config import (
    Config,
    coerce_setting,
    config_path,
    default_config,
    load_config,
    save_config,
)


def test_missing_config_returns_none(pft_home):
    assert load_config() is None


def test_save_and_load_roundtrip(cfg):
    loaded = load_config()
    assert loaded is not None
    assert loaded.db_path == cfg.db_path
    assert loaded.decimal_places == 2
    assert loaded.default_categories == cfg.default_categories


def test_config_path_follows_pft_home(pft_home):
    assert config_path() == pft_home / "config.json"


def test_default_categories_always_include_uncategorized():
    config = Config.from_dict({"default_categories": ["food", "food", "rent"]})
    assert config.default_categories == ["uncategorized", "food", "rent"]


def test_default_categories_accept_comma_string():
    config = Config.from_dict({"default_categories": "a, b ,a"})
    assert config.default_categories == ["uncategorized", "a", "b"]


def test_invalid_decimal_places_rejected():
    with pytest.raises(ConfigError):
        Config.from_dict({"decimal_places": 9})
    with pytest.raises(ConfigError):
        Config.from_dict({"decimal_places": "two"})


def test_invalid_rules_rejected():
    with pytest.raises(ConfigError):
        Config.from_dict({"rules": [{"id": "1"}]})


def test_resolved_db_path_expands_home(pft_home):
    config = default_config()
    config.db_path = "~/data/pft.db"
    assert config.resolved_db_path == str(Path.home() / "data" / "pft.db")


def test_coerce_setting():
    assert coerce_setting("decimal_places", "3") == 3
    assert coerce_setting("currency", "eur") == "EUR"
    assert coerce_setting("default_categories", "a,b") == [
        "uncategorized",
        "a",
        "b",
    ]
    with pytest.raises(ConfigError):
        coerce_setting("decimal_places", "many")
    with pytest.raises(ConfigError):
        coerce_setting("unknown_key", "x")


def test_config_set_db_path_survives_save(cfg):
    cfg.db_path = "/tmp/elsewhere.db"
    save_config(cfg)
    assert load_config().db_path == "/tmp/elsewhere.db"
