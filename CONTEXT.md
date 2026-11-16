# Personal Finance Tracker

A CLI tracker for one individual's income and expenses: record or import
transactions, categorize them, summarize spending, and flag anomalies when data
is entered.

## Language

**Transaction**:
One income or expense record: kind, amount, date, merchant and category.
_Avoid_: entry, record

**Kind**:
Whether a transaction is income or an expense; the amount itself is always positive.
_Avoid_: type, direction

**Amount**:
A monetary value held as integer minor units (cents), formatted with the configured currency symbol and decimal places.
_Avoid_: money, price, value

**Merchant**:
The counterparty label of a transaction (e.g. FreshMart).
_Avoid_: payee, vendor, description

**Category**:
A classification of a transaction (e.g. groceries, rent), chosen from a seeded, user-extensible set; the default is `uncategorized`.
_Avoid_: tag, label

**Provenance**:
The `(source, ref)` pair recording where a record came from — the CSV file's path and a hash of the row's content plus its occurrence number, or `manual` for hand entry. Provenance is the basis of import idempotency and is not user-visible.
_Avoid_: origin, fingerprint

**Duplicate**:
Two distinct transactions with equal kind, amount, date and merchant — the same content entered or imported twice. Category is deliberately excluded: it is mutable metadata.
_Avoid_: repeat, copy

**Integrity check**:
A relational, data-integrity analysis implemented as an abstract base class with concrete classes (`CheckDuplicateRule`); it compares transactions with each other and runs at entry time.
_Avoid_: validation rule

**Rule**:
A user-defined, flag-only condition stored as `{id, description, expression}`; the expression is Python boolean syntax over transaction fields, evaluated safely via a whitelisted `ast` walker. Rules never block a save.
_Avoid_: policy, constraint

**Expression**:
The boolean condition of a rule, e.g. `(category == 'groceries') and amount >= 1000`; `amount` is in currency units and `date` is an ISO string.
_Avoid_: formula, predicate

**Flag**:
A finding from an integrity check or a rule: the producing subsystem, a message, and the affected transaction ids.
_Avoid_: alert, warning, violation

**Summary**:
A derived view over transactions: totals, breakdown by category, and month-over-month spend.
_Avoid_: report, statistics

**Import**:
Ingesting transactions from a CSV file; rows already ingested under the same provenance are skipped, and the result reports imported and skipped counts.
_Avoid_: load, upload

**Config**:
User preferences (database path, currency, symbol, decimal places, date format, default categories, rules) stored as JSON in the config directory.
_Avoid_: settings file

**Init**:
The guided first-run setup that writes the config, creates and seeds the database, and optionally imports a seed CSV.
_Avoid_: bootstrap, install
