"""Command-line interface for the Personal Finance Tracker.

All write paths check integrity + rules at entry time: ``add`` prompts before
saving a flagged transaction; ``import`` reports flags after ingesting. There is
no separate "run rules" command — flags happen where data enters the tracker.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import uuid
from dataclasses import replace
from typing import Dict, List, Optional, Tuple

from pft.errors import NotFoundError, PftError
from pft.models.amount import format_amount, parse_amount
from pft.models.config import (
    Config,
    coerce_setting,
    load_config,
    save_config,
)
from pft.models.dates import format_date, today_iso, validate_iso_date
from pft.models.flag import Flag
from pft.models.kind import Kind
from pft.models.rule import Rule
from pft.models.transaction import Transaction
from pft.services import integrity, rules
from pft.services import summary as summary_service
from pft.services.importer import import_csv
from pft.services.init import run_init
from pft.storage import db, repository

PROG = "pft"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _ask(prompt: str, default: str = "") -> str:
    try:
        answer = input(f"{prompt} [{default}]: ").strip()
    except EOFError:
        return default
    return answer or default


def _confirm(prompt: str) -> bool:
    try:
        answer = input(f"{prompt} ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


def _ensure_config() -> Config:
    """Load config, running first-run setup when none exists."""
    cfg = load_config()
    if cfg is not None:
        return cfg
    print("No configuration found — starting first-run setup.")
    return run_init()


def _open(args) -> Tuple[Config, sqlite3.Connection]:
    """Load config (validating rules), apply --db, and open the database."""
    cfg = _ensure_config()
    rules.validate_rules(cfg.rules)
    db_override = getattr(args, "db", None)
    if db_override:
        cfg.db_path = db_override
    conn = db.connect(cfg.resolved_db_path, cfg.default_categories)
    return cfg, conn


def _fmt(cfg: Config, cents: int) -> str:
    return format_amount(cents, cfg.currency_symbol, cfg.decimal_places)


def _print_table(headers: List[str], rows: List[List[str]]) -> None:
    widths = [
        max(len(headers[i]), *(len(row[i]) for row in rows)) for i in range(len(headers))
    ]
    print("  ".join(header.ljust(widths[i]) for i, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))


def _print_flags(flags: List[Flag], tx: Optional[Transaction] = None) -> None:
    for flag in flags:
        prefix = f"#{tx.id} " if tx is not None and tx.id is not None else ""
        print(f"  flag [{flag.source}] {prefix}{flag.message}")


def _date_range(args) -> Tuple[Optional[str], Optional[str]]:
    if args.date_to and not args.date_from:
        args._parser.error("--to requires --from")
    date_from = validate_iso_date(args.date_from) if args.date_from else None
    date_to = validate_iso_date(args.date_to) if args.date_to else None
    return date_from, date_to


def _build_transaction(
    kind: Kind, amount_raw: str, date_raw: str, merchant: str, category: str, cfg: Config
) -> Transaction:
    return Transaction(
        kind=kind,
        amount_cents=parse_amount(amount_raw, cfg.decimal_places),
        date=validate_iso_date(date_raw),
        merchant=merchant.strip(),
        category=category,
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_init(args) -> int:
    cfg = run_init(ask_seed=args.csv is None)
    if args.csv:
        conn = db.connect(cfg.resolved_db_path, cfg.default_categories)
        try:
            result = import_csv(conn, args.csv, cfg)
            print(
                f"Seeded {result.imported} transaction(s), "
                f"skipped {result.skipped} already imported."
            )
        finally:
            conn.close()
    return 0


def cmd_config_show(args) -> int:
    cfg = _ensure_config()
    print(json.dumps(cfg.to_dict(), indent=2, ensure_ascii=False))
    return 0


def cmd_config_set(args) -> int:
    cfg = _ensure_config()
    value = coerce_setting(args.key, args.value)
    setattr(cfg, args.key, value)
    save_config(cfg)
    shown = value if not isinstance(value, list) else ", ".join(value)
    print(f"{args.key} = {shown}")
    if args.key == "db_path":
        print("Note: existing data stays in the previous database file.")
    return 0


def cmd_add(args) -> int:
    cfg, conn = _open(args)
    try:
        kind_raw = args.kind if args.kind is not None else _ask("Kind (income/expense)", "expense")
        try:
            kind = Kind.parse(kind_raw)
        except ValueError as exc:
            raise PftError(str(exc)) from None
        amount_raw = args.amount if args.amount is not None else _ask("Amount")
        merchant_raw = args.merchant if args.merchant is not None else _ask("Merchant")
        date_raw = args.date if args.date is not None else today_iso()
        category = args.category if args.category is not None else "uncategorized"

        tx = _build_transaction(kind, amount_raw, date_raw, merchant_raw, category, cfg)
        repository.category_id(conn, category)

        flags = integrity.run_checks(conn, tx) + rules.run_rules(cfg.rules, tx, cfg)
        if flags:
            _print_flags(flags)
            if not _confirm("Save anyway? [y/N]"):
                print("Aborted — nothing was saved.")
                return 1

        saved = repository.add_transaction(
            conn, replace(tx, source="manual", ref=uuid.uuid4().hex)
        )
        print(f"Saved transaction #{saved}.")
        return 0
    finally:
        conn.close()


def cmd_import(args) -> int:
    cfg, conn = _open(args)
    try:
        result = import_csv(conn, args.path, cfg)
        print(
            f"Imported {result.imported} transaction(s), "
            f"skipped {result.skipped} already imported."
        )
        flagged: List[Transaction] = []
        seen = set()
        for tx_id in result.transaction_ids:
            tx = repository.get_transaction(conn, tx_id)
            if tx is None:
                continue
            flags = integrity.run_checks(conn, tx) + rules.run_rules(cfg.rules, tx, cfg)
            if not flags:
                continue
            unique = []
            for flag in flags:
                key = (flag.source, tuple(sorted(flag.transaction_ids)))
                if key not in seen:
                    seen.add(key)
                    unique.append(flag)
            if unique:
                _print_flags(unique, tx)
                flagged.append(tx)
        if flagged:
            print(f"Flags raised for {len(flagged)} imported transaction(s).")
        return 0
    finally:
        conn.close()


def cmd_list(args) -> int:
    cfg, conn = _open(args)
    try:
        date_from, date_to = _date_range(args)
        txs = repository.list_transactions(
            conn,
            date_from=date_from,
            date_to=date_to,
            category=args.category,
            uncategorized=args.uncategorized,
        )
        if not txs:
            print("No transactions found.")
            return 0
        headers = ["ID", "DATE", "KIND", "AMOUNT", "MERCHANT", "CATEGORY"]
        rows = [
            [
                str(tx.id),
                format_date(tx.date, cfg.date_format),
                tx.kind.value,
                _fmt(cfg, tx.amount_cents),
                tx.merchant,
                tx.category,
            ]
            for tx in txs
        ]
        _print_table(headers, rows)
        return 0
    finally:
        conn.close()


def cmd_categorize(args) -> int:
    cfg, conn = _open(args)
    try:
        tx = repository.categorize(conn, args.id, args.category)
        print(f"Transaction #{tx.id} categorized as {tx.category!r}.")
        return 0
    finally:
        conn.close()


def cmd_category_add(args) -> int:
    cfg, conn = _open(args)
    try:
        created = repository.add_category(conn, args.name)
        if created:
            print(f"Category {args.name!r} added.")
        else:
            print(f"Category {args.name!r} already exists.")
        return 0
    finally:
        conn.close()


def cmd_category_list(args) -> int:
    cfg, conn = _open(args)
    try:
        categories = repository.list_categories(conn)
        for category in categories:
            print(category.name)
        return 0
    finally:
        conn.close()


def cmd_rule_add(args) -> int:
    cfg = _ensure_config()
    rules.validate_rule_expression(args.expression, cfg)
    existing_ids = {rule.id for rule in cfg.rules}
    next_id = 1
    while str(next_id) in existing_ids:
        next_id += 1
    rule = Rule(id=str(next_id), description=args.description, expression=args.expression)
    cfg.rules.append(rule)
    save_config(cfg)
    print(f"Added rule {rule.id}: {rule.description} — {rule.expression}")
    return 0


def cmd_rule_list(args) -> int:
    cfg = _ensure_config()
    if not cfg.rules:
        print("No rules configured. Add one with: pft rule add \"amount >= 1000\" --description \"...\"")
        return 0
    headers = ["ID", "DESCRIPTION", "EXPRESSION"]
    rows = [[rule.id, rule.description, rule.expression] for rule in cfg.rules]
    _print_table(headers, rows)
    return 0


def cmd_rule_remove(args) -> int:
    cfg = _ensure_config()
    remaining = [rule for rule in cfg.rules if rule.id != str(args.id)]
    if len(remaining) == len(cfg.rules):
        raise NotFoundError(f"rule {args.id!r} not found")
    cfg.rules = remaining
    save_config(cfg)
    print(f"Removed rule {args.id}.")
    return 0


def cmd_summary(args) -> int:
    cfg, conn = _open(args)
    try:
        date_from, date_to = _date_range(args)
        result = summary_service.build_summary(
            conn, date_from=date_from, date_to=date_to, category=args.category
        )
        if date_from or date_to or args.category:
            scope = " ".join(
                part
                for part in (
                    f"from {date_from}" if date_from else "",
                    f"to {date_to}" if date_to else "",
                    f"category {args.category!r}" if args.category else "",
                )
                if part
            )
            print(f"Scope: {scope}")
        print(f"Transactions: {result.transaction_count}")
        print(f"Income: {_fmt(cfg, result.total_income_cents)}")
        print(f"Spend:  {_fmt(cfg, result.total_spend_cents)}")
        print(f"Net:    {_fmt(cfg, result.net_cents)}")

        if result.spend_by_category:
            print()
            print("Spend by category:")
            _print_table(
                ["CATEGORY", "SPEND"],
                [
                    [item.name, _fmt(cfg, item.total_cents)]
                    for item in result.spend_by_category
                ],
            )
        if result.income_by_category:
            print()
            print("Income by category:")
            _print_table(
                ["CATEGORY", "INCOME"],
                [
                    [item.name, _fmt(cfg, item.total_cents)]
                    for item in result.income_by_category
                ],
            )
        if result.monthly:
            print()
            print("Monthly:")
            _print_table(
                ["MONTH", "INCOME", "SPEND"],
                [
                    [
                        item.month,
                        _fmt(cfg, item.income_cents),
                        _fmt(cfg, item.spend_cents),
                    ]
                    for item in result.monthly
                ],
            )
        return 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def build_parser() -> Tuple[argparse.ArgumentParser, Dict[str, argparse.ArgumentParser]]:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Personal Finance Tracker — track personal income and expenses.",
    )
    parser.add_argument(
        "--db",
        metavar="PATH",
        default=None,
        help="override the database path for this command",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    commands: Dict[str, argparse.ArgumentParser] = {}

    def add(name: str, help_text: str) -> argparse.ArgumentParser:
        subparser = sub.add_parser(name, help=help_text, description=help_text)
        subparser.set_defaults(_parser=subparser)
        commands[name] = subparser
        return subparser

    p = add("init", "initialize or reconfigure the tracker")
    p.add_argument("--csv", metavar="FILE", help="CSV file of transactions to seed")
    p.set_defaults(handler=cmd_init)

    p = add("add", "record a single transaction")
    p.add_argument("--kind", choices=["income", "expense"], help="transaction kind")
    p.add_argument("--amount", help='amount, e.g. "12.50"')
    p.add_argument("--merchant", help="counterparty (e.g. Safeway)")
    p.add_argument("--category", help="category name (default: uncategorized)")
    p.add_argument("--date", help="ISO date YYYY-MM-DD (default: today)")
    p.set_defaults(handler=cmd_add)

    p = add("import", "import transactions from a CSV file")
    p.add_argument("path", metavar="FILE")
    p.set_defaults(handler=cmd_import)

    p = add("list", "list transactions")
    p.add_argument("--from", dest="date_from", metavar="YYYY-MM-DD")
    p.add_argument("--to", dest="date_to", metavar="YYYY-MM-DD")
    p.add_argument("--category", help="filter by category")
    p.add_argument("--uncategorized", action="store_true", help="only uncategorized")
    p.set_defaults(handler=cmd_list)

    p = add("categorize", "change a transaction's category")
    p.add_argument("id", type=int, metavar="ID")
    p.add_argument("category", help="category name")
    p.set_defaults(handler=cmd_categorize)

    p = add("category", "manage categories")
    csub = p.add_subparsers(dest="category_command", metavar="<add|list>")
    cp = csub.add_parser("add", help="add a category")
    cp.add_argument("name")
    cp.set_defaults(handler=cmd_category_add, _parser=cp)
    cp = csub.add_parser("list", help="list categories")
    cp.set_defaults(handler=cmd_category_list, _parser=cp)
    p.set_defaults(handler=None)

    p = add("rule", "manage flag-only rules")
    rsub = p.add_subparsers(dest="rule_command", metavar="<add|list|remove>")
    cp = rsub.add_parser("add", help="add a rule")
    cp.add_argument("expression", help="e.g. \"amount >= 1000 and category == 'groceries'\"")
    cp.add_argument("--description", required=True, help="human-readable description")
    cp.set_defaults(handler=cmd_rule_add, _parser=cp)
    cp = rsub.add_parser("list", help="list rules")
    cp.set_defaults(handler=cmd_rule_list, _parser=cp)
    cp = rsub.add_parser("remove", help="remove a rule")
    cp.add_argument("id", help="rule id")
    cp.set_defaults(handler=cmd_rule_remove, _parser=cp)
    p.set_defaults(handler=None)

    p = add("summary", "summarize income and spending")
    p.add_argument("--from", dest="date_from", metavar="YYYY-MM-DD")
    p.add_argument("--to", dest="date_to", metavar="YYYY-MM-DD")
    p.add_argument("--category", help="filter by category")
    p.set_defaults(handler=cmd_summary)

    p = add("config", "show or change configuration")
    csub = p.add_subparsers(dest="config_command", metavar="<show|set>")
    cp = csub.add_parser("show", help="print the current configuration")
    cp.set_defaults(handler=cmd_config_show, _parser=cp)
    cp = csub.add_parser("set", help="change a configuration value")
    cp.add_argument("key")
    cp.add_argument("value")
    cp.set_defaults(handler=cmd_config_set, _parser=cp)
    p.set_defaults(handler=None)

    p = add("help", "show help for a command")
    p.add_argument("command_name", nargs="?", metavar="COMMAND")
    p.set_defaults(handler=None)

    parser.set_defaults(_parser=parser)
    return parser, commands


def main(argv: Optional[List[str]] = None) -> int:
    parser, commands = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        try:
            _ensure_config()
        except PftError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        parser.print_help()
        return 0

    if args.command == "help":
        target = getattr(args, "command_name", None)
        if target:
            target_parser = commands.get(target)
            if target_parser is None:
                parser.error(f"unknown command {target!r}")
            print(target_parser.format_help().rstrip())
            return 0
        parser.print_help()
        return 0

    handler = getattr(args, "handler", None)
    if handler is None:
        args._parser.print_help()
        return 0

    try:
        return handler(args)
    except PftError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
