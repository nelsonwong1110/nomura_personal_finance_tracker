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
| `pft config set KEY VALUE` | Change a setting: `db_path`, `currency`, `currency_symbol`, `decimal_places` (0–4), `date_format`, `default_categories` |
| `pft add [--kind income\|expense] [--amount A] [--merchant M] [--category C] [--date YYYY-MM-DD]` | Record one transaction; missing kind/amount/merchant are prompted for |
| `pft import FILE` | Bulk import from CSV (see below) |
| `pft list [--from D] [--to D] [--category C] [--uncategorized]` | List transactions, newest first |
| `pft categorize ID CATEGORY` | Reassign one transaction's category |
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
expense,42.50,2026-10-02,Safeway,groceries
income,3200.00,2026-10-01,Acme Payroll,income
```

Import is **all-or-nothing**: an invalid row aborts the whole file and names the
row, so you never get a half-imported file. A `category` in the CSV must already
exist (`pft category add ...`).

**Re-importing is safe.** Every row's provenance (file name + a hash of its
content and occurrence number) is recorded. Importing the same file again skips
everything; appending rows imports only the new ones:
`Imported 0 transaction(s), skipped 6 already imported.`

Identical rows are *not* collapsed: two genuinely identical purchases in one
file are kept as two records (their occurrence numbers differ). Whether they are
a double entry is exactly what the duplicate check flags.

## Rules (flag-only analysis)

Rules live in the config file and are managed with `pft rule ...`. A rule is:

```json
{"id": "1", "description": "Expensive grocery", "expression": "(category == 'groceries') and amount >= 1000"}
```

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
literals.

**Safety:** expressions are parsed with `ast.parse` and evaluated by a
whitelist walker; `eval()` is never used. Calls, attribute access, imports and
other constructs are rejected when the rule is added — a config file you can edit
must never be able to execute code.

### Flags happen at entry time

There is no separate "run the rules" command. Both subsystems — the duplicate
integrity check and your rules — run whenever a transaction is created:

- `pft add`: flags are printed and you are asked **“Save anyway? [y/N]”**. No
  aborts the save (nothing is written); yes saves it.
- `pft import`: rows are ingested idempotently, then any flags for the newly
  created rows are reported. Import never prompts, so bulk loads stay scriptable.

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
- Amounts are stored as integer minor units; input like `"$12.50"`, `"12.5"` and
  `"1,234.56"` is accepted, values with more than the configured decimal places
  are rejected, and amounts must be positive.
- Dates are `YYYY-MM-DD`; `add` defaults to today. The config `date_format` only
  affects display.
- Categories are seeded from config and extensible; an unknown category is a
  clean error (foreign keys are enforced), never a silently-created typo.
- `merchant` is a free-text label; no merchant normalization.
- Summary month-over-month rows are derived from transaction dates.
- Not implemented (out of scope for the exercise): editing/deleting
  transactions, budgets, multi-user, export.

## Design notes

```
pft/
├── models/     pure data: Kind, Amount, Transaction, Category, Rule, Config, Flag
├── storage/    SQLite schema (storage/db.py) and repository (storage/repository.py)
├── services/   logic: rules (ast evaluator), integrity, importer, summary, init wizard
└── cli/        argparse command tree (cli/cli.py)
```

Dependencies flow one way: `cli → services → storage → models`. The rule engine's
extension points are the `ALLOWED_FIELDS` whitelist (new fields) and
`INTEGRITY_CHECKS` (new integrity checks).

Data lives in a SQLite file created at runtime (default `~/.pft/pft.db`; config
at `~/.pft/config.json`). Nothing binary is part of the source; the database is
user data. Set `PFT_HOME=/some/dir` to use an isolated config/database directory.

## Tests

```bash
python3 -m pytest tests/ -v
```

105 tests: amount parsing/formatting, config validation, repository behaviour,
CSV import (idempotency, all-or-nothing errors, duplicate preservation), summary
aggregation and filters, safe expression evaluation (including rejection of
unsafe constructs), duplicate detection, and CLI integration tests that drive
`main()` end-to-end against temporary databases.
