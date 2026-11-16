"""CLI integration tests: drive main() end-to-end against a temp database."""

from __future__ import annotations

import pytest

from pft.cli.cli import main
from pft.models.config import config_path
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
        "Safeway",
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
    assert "Safeway" in out
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


def test_rule_add_list_remove(cfg, capsys):
    assert main(["rule", "add", "amount > 1000", "--description", "Big"]) == 0
    assert "Added rule 1" in capsys.readouterr().out

    assert main(["rule", "list"]) == 0
    assert "Big" in capsys.readouterr().out

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
        "expense,42.50,2026-10-02,Safeway,groceries\n"
        "expense,42.50,2026-10-02,Safeway,groceries\n"
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


def test_config_show_and_set(cfg, capsys):
    assert main(["config", "set", "currency_symbol", "€"]) == 0
    capsys.readouterr()

    assert main(["config", "show"]) == 0
    assert "€" in capsys.readouterr().out

    assert main(["config", "set", "decimal_places", "9"]) == 2
    assert "error:" in capsys.readouterr().err


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
