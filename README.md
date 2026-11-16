# Personal Finance Tracker

A command-line tool to track personal income and expenses for an individual
user. Record or bulk-import transactions, categorize them, review summaries
(totals, per-category, month-over-month), and get flags for suspicious entries
at the moment data enters the tracker.

## Requirements

- Python 3.9+ — **no runtime dependencies** (everything is in the standard library)
- pytest 8+ to run the tests (development only)

## Quick start

```bash
# First run: guided setup writes ~/.pft/config.json and creates the database
python3 -m pft

# Seed some transactions
python3 -m pft import sample_transactions.csv

# Look around
python3 -m pft list
python3 -m pft summary
```

No installation step. Run `python3 -m pft help` (or `python3 -m pft help <command>`)
for usage of any command; every command also supports `--help`.

## Commands

| Command | What it does |
|---|---|
| `pft` | First run triggers setup; afterwards prints the command list |
| `pft init [--csv FILE]` | Re-run setup (existing values become defaults); optionally seed a CSV |
| `pft config show` | Print the configuration as JSON |
| `pft config set KEY VALUE` | Change a setting: `db_path`, `currency`, `currency_symbol`, `date_format`, `default_categories` |
| `pft add [--kind income\|expense] [--amount A] [--merchant M] [--category C] [--date YYYY-MM-DD]` | Record one transaction; missing kind/amount/merchant are prompted for |
| `pft import FILE` | Bulk import from CSV (see below) |
| `pft list [--from D] [--to D] [--category C] [--uncategorized]` | List transactions, newest first |
| `pft categorize ID CATEGORY` | Reassign one transaction's category |
| `pft edit ID [--kind ...] [--amount A] [--date D] [--merchant M] [--category C]` | Change fields of a transaction (at least one flag required; unspecified fields unchanged; same flag-check + prompt as `add`) |
| `pft delete ID` | Remove a transaction (asks for confirmation first) |
| `pft category add NAME` / `pft category list` | Extend / list categories |
| `pft rule add "EXPRESSION" --description TEXT` | Add a flag-only rule |
| `pft rule list` / `pft rule remove ID` | Manage rules |
| `pft summary [--from D] [--to D] [--category C]` | Totals, spend/income by category, month-over-month table |
| `pft help [COMMAND]` | Help |

Global option: `--db PATH` before the command overrides the database location
for that invocation (handy for trying things out).

Date filters are inclusive. `--to` requires `--from`; `--from` alone covers up
to today; no filter means all time.

## Importing CSV

Required columns: `kind`, `amount`, `date`, `merchant`. Optional: `category`
(defaults to `uncategorized`). Header names are case-insensitive; extra columns
are ignored.

```csv
kind,amount,date,merchant,category
expense,42.50,2026-10-02,FreshMart,groceries
income,3200.00,2026-10-01,Northwind Payroll,income
```

Import is **all-or-nothing**: an invalid row aborts the whole file and names the
row, so you never get a half-imported file. A `category` in the CSV must already
exist (`pft category add ...`).

**Re-importing is safe.** Every row's provenance (the file's path + a hash of
its content and occurrence number) is recorded. Importing the same file again
skips everything; appending rows imports only the new ones:
`Imported 0 transaction(s), skipped 6 already imported.` The source is the file's
path (not its basename), so two files that happen to share a name in different
folders are distinct. Trade-off: moving or renaming a file gives its rows new
provenance, so they would import again.

Identical rows are *not* collapsed: two genuinely identical purchases in one
file are kept as two records (their occurrence numbers differ). Whether they are
a double entry is exactly what the duplicate check flags.

## Rules (flag-only analysis)

Rules live in the config file and are managed with `pft rule ...`. A rule is:

```json
{"id": "1", "description": "Expensive grocery", "expression": "(category == 'groceries') and amount >= 1000"}
```

**One rule ships with a fresh setup** so the engine is demonstrable immediately:
`1 — Expensive grocery — (category == 'groceries') and amount >= 1000`
(removing it with `pft rule remove 1` is not undone by a restart). Add your own:

```bash
python3 -m pft rule add "(category == 'groceries') and amount >= 1000" --description "Expensive grocery"
```

Expressions use Python boolean syntax over five fields:

| Field | Value |
|---|---|
| `kind` | `'income'` or `'expense'` |
| `amount` | number in currency units (e.g. `12.50`) |
| `date` | ISO string, so `date >= '2026-10-01'` works |
| `merchant` | string |
| `category` | string |

Supported: `and` / `or` / `not`, comparisons (`==`, `!=`, `<`, `<=`, `>`, `>=`),
membership (`category in ('groceries', 'dining')`), arithmetic, number and string
literals. Numeric literals are evaluated as exact decimals, so
`amount == 12.30` matches a $12.30 transaction.

**Safety:** expressions are parsed with `ast.parse` and evaluated by a
whitelist walker; `eval()` is never used. Calls, attribute access, imports and
other constructs are rejected when the rule is added — a config file you can edit
must never be able to execute code.

### Flags happen at entry time

There is no separate "run the rules" command. Both subsystems — the duplicate
integrity check and your rules — run where data enters the tracker:

- `pft add` and `pft edit`: flags are printed and you are asked
  **“Save anyway? [y/N]”**. No aborts (nothing is written); yes saves it.
- `pft import`: rows are ingested idempotently, then any flags for the newly
  created rows are reported. Import never prompts, so bulk imports stay scriptable.

### The duplicate check

Implemented as an abstract `IntegrityCheck` base class with the concrete
`CheckDuplicateRule`, separate from the config-driven field rules because it is a
relational data-integrity check rather than a per-row condition. It flags
transactions whose **kind, amount, date and merchant** appear more than once.
Category is deliberately excluded: it is mutable, derived metadata, so recategorizing
a row must never hide a double entry.

## Assumptions and scope

- Single user, single currency (set in config); no accounts, transfers, or
  currency conversion.
- Amounts are stored as integer minor units (cents). Two decimal places are
  assumed — the convention for major currencies. Input like `"$12.50"`, `"12.5"`
  and `"1,234.56"` is accepted, values with more than two decimal places are
  rejected, and amounts must be positive.
- Dates are `YYYY-MM-DD`; `add` defaults to today. The config `date_format` only
  affects display.
- Categories are seeded from config and extensible; an unknown category is a
  clean error (foreign keys are enforced), never a silently-created typo.
- `merchant` is a free-text label; no merchant normalization.
- Summary month-over-month rows are derived from transaction dates.
- Not implemented (out of scope for the exercise): budgets, multi-user, export.

## Design notes

```
pft/
├── models/     domain data and config: Kind, Amount, Transaction, Category, Rule, Flag, Config, summary and filter types
├── storage/    SQLite schema (storage/db.py) and repository: all transaction/category SQL (storage/repository.py)
├── services/   logic: rules (ast evaluator), integrity, flags, prompting, importer, summary, init wizard
└── cli/        argparse command tree (cli/cli.py)
```

Dependencies flow one way: `cli → services → storage → models`. All SQL over
transactions and categories lives in the repository (including the duplicate-match
query and the summary aggregates). The rule engine's extension point is the
`FIELD_RESOLVERS` registry in `pft/services/rules.py` (a new rule field), and
`INTEGRITY_CHECKS` in `pft/services/integrity.py` (a new integrity check).

Data lives in a SQLite file created at runtime (default `~/.pft/pft.db`; config
at `~/.pft/config.json`). Nothing binary is part of the source; the database is
user data. Set `PFT_HOME=/some/dir` to use an isolated config/database directory.

## Tests

```bash
python3 -m pytest tests/ -v
```

124 tests: amount parsing/formatting, config validation (including the shipped
rule), repository behaviour
(including edit and delete), CSV import (idempotency, all-or-nothing errors,
duplicate preservation), summary aggregation and filters, safe expression
evaluation (including rejection of unsafe constructs), duplicate detection,
clean errors for invalid input, and CLI integration tests that drive `main()`
end-to-end against temporary databases.
