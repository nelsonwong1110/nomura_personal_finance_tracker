"""CLI integration tests: drive main() end-to-end against a temp database."""

from __future__ import annotations

import pytest

from pft.cli.cli import coerce_setting, main
from pft.errors import ConfigError
from pft.models.config import config_path, load_config
from pft.storage import db as db_module
from pft.storage import repository


def add_args(*extra):
    return [
        "add",
        "--kind",
        "expense",
        "--amount",
        "12.50",
        "--merchant",
        "FreshMart",
        "--category",
        "groceries",
        *extra,
    ]


def open_conn(cfg):
    return db_module.connect(cfg.resolved_db_path, cfg.default_categories)


def test_first_run_runs_setup_wizard(pft_home, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    assert main(["summary"]) == 0
    out = capsys.readouterr().out
    assert config_path().is_file()
    assert "setup" in out.lower()
    assert "Transactions: 0" in out


def test_add_persists_transaction(cfg, capsys):
    assert main(add_args()) == 0
    assert "Saved transaction #1" in capsys.readouterr().out

    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "FreshMart" in out
    assert "$12.50" in out


def test_add_prompts_for_missing_fields(cfg, monkeypatch, capsys):
    answers = iter(["expense", "9.99", "Corner Shop"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert main(["add"]) == 0
    assert "Saved transaction #1" in capsys.readouterr().out


def test_duplicate_prompt_abort_saves_nothing(cfg, monkeypatch, capsys):
    assert main(add_args()) == 0
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    assert main(add_args()) == 1
    assert "Aborted" in capsys.readouterr().out
    conn = open_conn(cfg)
    try:
        assert repository.count_transactions(conn) == 1
    finally:
        conn.close()


def test_duplicate_prompt_confirm_saves(cfg, monkeypatch, capsys):
    assert main(add_args()) == 0
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    assert main(add_args()) == 0
    assert "Saved transaction #2" in capsys.readouterr().out


def test_rule_flag_prompts_on_add(cfg, monkeypatch, capsys):
    code = main(
        [
            "rule",
            "add",
            "amount >= 1000 and category == 'groceries'",
            "--description",
            "Expensive grocery",
        ]
    )
    assert code == 0
    capsys.readouterr()

    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    assert main(add_args("--amount", "1200")) == 1
    out = capsys.readouterr().out
    assert "Expensive grocery" in out
    assert "Aborted" in out


def test_rule_add_rejects_unsafe_expression(cfg, capsys):
    code = main(["rule", "add", "__import__('os').system('echo hi')", "--description", "x"])
    assert code == 2
    assert "error:" in capsys.readouterr().err


def test_default_rule_listed_on_fresh_config(cfg, capsys):
    assert main(["rule", "list"]) == 0
    assert "Expensive grocery" in capsys.readouterr().out


def test_rule_add_list_remove(cfg, capsys):
    # Rule 1 ships by default, so the new rule gets id 2.
    assert main(["rule", "add", "amount > 1000", "--description", "Big"]) == 0
    assert "Added rule 2" in capsys.readouterr().out

    assert main(["rule", "list"]) == 0
    out = capsys.readouterr().out
    assert "Big" in out
    assert "Expensive grocery" in out

    assert main(["rule", "remove", "2"]) == 0
    capsys.readouterr()
    assert main(["rule", "remove", "1"]) == 0
    capsys.readouterr()

    assert main(["rule", "list"]) == 0
    assert "No rules configured" in capsys.readouterr().out


def test_rule_remove_missing(cfg, capsys):
    assert main(["rule", "remove", "99"]) == 2
    assert "not found" in capsys.readouterr().err


def test_import_twice_is_idempotent_and_reports_flags(cfg, write_csv, capsys):
    content = (
        "kind,amount,date,merchant,category\n"
        "expense,42.50,2026-10-02,FreshMart,groceries\n"
        "expense,42.50,2026-10-02,FreshMart,groceries\n"
    )
    path = write_csv("bank.csv", content)

    assert main(["import", path]) == 0
    out = capsys.readouterr().out
    assert "Imported 2 transaction(s), skipped 0" in out
    assert "integrity:duplicate" in out
    # The duplicate group is reported once, not once per member row.
    assert out.count("integrity:duplicate") == 1

    assert main(["import", path]) == 0
    out = capsys.readouterr().out
    assert "Imported 0 transaction(s), skipped 2" in out


def test_summary_date_filter_and_to_requires_from(cfg, capsys):
    main(add_args("--date", "2026-10-01"))
    main(add_args("--date", "2026-11-01"))
    capsys.readouterr()

    assert main(["summary", "--from", "2026-10-15"]) == 0
    out = capsys.readouterr().out
    assert "Transactions: 1" in out
    assert "Scope:" in out

    with pytest.raises(SystemExit) as excinfo:
        main(["list", "--to", "2026-10-31"])
    assert excinfo.value.code == 2


def test_categorize_and_category_management(cfg, capsys):
    main(add_args("--category", "uncategorized"))
    capsys.readouterr()

    assert main(["categorize", "1", "dining"]) == 0
    assert "categorized as 'dining'" in capsys.readouterr().out

    assert main(["category", "add", "pet care"]) == 0
    assert "added" in capsys.readouterr().out

    assert main(["category", "list"]) == 0
    assert "pet care" in capsys.readouterr().out

    assert main(["category", "add", "pet care"]) == 0
    assert "already exists" in capsys.readouterr().out


def test_unknown_category_add_fails_cleanly(cfg, capsys):
    assert main(add_args("--category", "groceris")) == 2
    assert "unknown category" in capsys.readouterr().err


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


def test_blank_merchant_is_a_clean_error(cfg, capsys):
    assert main(["add", "--kind", "expense", "--amount", "5", "--merchant", "   "]) == 2
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "merchant" in captured.err
    assert "Traceback" not in captured.err


def test_blank_category_is_a_clean_error(cfg, capsys):
    assert main(add_args("--category", "   ")) == 2
    captured = capsys.readouterr()
    assert "category" in captured.err
    assert "Traceback" not in captured.err


def test_config_show_and_set(cfg, capsys):
    assert main(["config", "set", "currency_symbol", "€"]) == 0
    capsys.readouterr()

    assert main(["config", "show"]) == 0
    assert "€" in capsys.readouterr().out

    assert main(["config", "set", "decimal_places", "9"]) == 2
    assert "error:" in capsys.readouterr().err


def test_decimal_places_change_always_refused(cfg, capsys):
    assert main(["config", "set", "decimal_places", "0"]) == 2
    err = capsys.readouterr().err
    assert "reinterpreted" in err

    # The setting is unchanged.
    assert main(["config", "show"]) == 0
    assert '"decimal_places": 2' in capsys.readouterr().out


def test_decimal_places_same_value_is_noop(cfg, capsys):
    assert main(["config", "set", "decimal_places", "2"]) == 0
    assert "decimal_places = 2" in capsys.readouterr().out


def test_init_rerun_keeps_decimal_places(pft_home, monkeypatch, capsys):
    attempts = {"n": 0}

    def fake_input(prompt=""):
        if "Decimal places" in prompt:
            attempts["n"] += 1
            return "3" if attempts["n"] == 1 else "0"
        return ""

    monkeypatch.setattr("builtins.input", fake_input)
    assert main(["init"]) == 0
    assert main(["init"]) == 0
    out = capsys.readouterr().out
    assert "Decimal places (fixed at setup): 3" in out
    assert load_config().decimal_places == 3


def test_help_commands(capsys):
    assert main(["help"]) == 0
    assert "usage: pft" in capsys.readouterr().out

    assert main(["help", "summary"]) == 0
    assert "--from" in capsys.readouterr().out


def test_help_unknown_command(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["help", "nope"])
    assert excinfo.value.code == 2


def test_no_command_prints_help(cfg, capsys):
    assert main([]) == 0
    assert "usage: pft" in capsys.readouterr().out


def test_group_without_subcommand_prints_its_help(cfg, capsys):
    assert main(["config"]) == 0
    assert "show" in capsys.readouterr().out
    assert main(["rule"]) == 0
    assert "add" in capsys.readouterr().out


def test_edit_transaction(cfg, capsys):
    assert main(add_args()) == 0  # #1: $12.50 FreshMart groceries
    capsys.readouterr()
    conn = open_conn(cfg)
    try:
        before = repository.get_transaction(conn, 1)
    finally:
        conn.close()

    assert main(
        ["edit", "1", "--amount", "15.75", "--merchant", "Taco Casa", "--category", "dining"]
    ) == 0
    assert "Updated transaction #1" in capsys.readouterr().out

    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "Taco Casa" in out
    assert "$15.75" in out
    assert "FreshMart" not in out

    # Fields not passed to edit are carried forward unchanged.
    conn = open_conn(cfg)
    try:
        after = repository.get_transaction(conn, 1)
    finally:
        conn.close()
    assert after.kind == before.kind
    assert after.date == before.date


def test_edit_requires_at_least_one_field(cfg, capsys):
    assert main(add_args()) == 0
    capsys.readouterr()
    with pytest.raises(SystemExit) as excinfo:
        main(["edit", "1"])
    assert excinfo.value.code == 2


def test_edit_duplicate_prompt_abort_keeps_original(cfg, monkeypatch, capsys):
    assert main(add_args("--merchant", "Alpha")) == 0  # #1
    assert main(add_args("--merchant", "Beta")) == 0   # #2
    capsys.readouterr()

    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    assert main(["edit", "2", "--merchant", "Alpha"]) == 1
    assert "Aborted" in capsys.readouterr().out

    conn = open_conn(cfg)
    try:
        assert repository.get_transaction(conn, 2).merchant == "Beta"
    finally:
        conn.close()


def test_edit_duplicate_prompt_confirm_saves(cfg, monkeypatch, capsys):
    assert main(add_args("--merchant", "Alpha")) == 0
    assert main(add_args("--merchant", "Beta")) == 0
    capsys.readouterr()

    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    assert main(["edit", "2", "--merchant", "Alpha"]) == 0
    capsys.readouterr()

    assert main(["list"]) == 0
    assert "Beta" not in capsys.readouterr().out


def test_delete_with_confirmation(cfg, monkeypatch, capsys):
    assert main(add_args()) == 0
    capsys.readouterr()

    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    assert main(["delete", "1"]) == 0
    assert "Deleted transaction #1" in capsys.readouterr().out

    assert main(["list"]) == 0
    assert "No transactions found" in capsys.readouterr().out


def test_delete_abort_keeps_row(cfg, monkeypatch, capsys):
    assert main(add_args()) == 0
    capsys.readouterr()

    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    assert main(["delete", "1"]) == 1
    capsys.readouterr()

    assert main(["list"]) == 0
    assert "FreshMart" in capsys.readouterr().out


def test_delete_unknown_id(cfg, capsys):
    assert main(["delete", "999"]) == 2
    assert "not found" in capsys.readouterr().err


def test_init_with_seed_csv(pft_home, write_csv, monkeypatch, capsys):
    path = write_csv(
        "seed.csv",
        "kind,amount,date,merchant,category\n"
        "expense,10.00,2026-10-01,Bakery,dining\n",
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    assert main(["init", "--csv", path]) == 0
    out = capsys.readouterr().out
    assert "Seeded 1 transaction(s)" in out

    assert main(["list"]) == 0
    assert "Bakery" in capsys.readouterr().out
