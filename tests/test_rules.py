"""Field rules: safe ast evaluation, validation and flag emission."""

from __future__ import annotations

import pytest

from pft.errors import ExpressionError
from pft.models.config import default_config
from pft.models.kind import Kind
from pft.models.rule import Rule
from pft.models.transaction import Transaction
from pft.services import rules


def make_tx(**overrides):
    values = dict(
        kind=Kind.EXPENSE,
        amount_cents=1250,
        date="2026-10-02",
        merchant="Safeway",
        category="groceries",
        id=7,
    )
    values.update(overrides)
    return Transaction(**values)


def matches(expression, tx=None, cfg=None):
    cfg = cfg or default_config()
    values = rules.values_for(tx or make_tx(), cfg)
    return rules.evaluate(rules.compile_expression(expression), values)


def test_simple_comparison():
    assert matches("amount > 10") is True
    assert matches("amount > 13") is False


def test_amount_is_in_currency_units():
    assert matches("amount == 12.5")
    assert matches("amount >= 12.50")


def test_string_fields():
    assert matches("category == 'groceries'")
    assert matches("merchant != 'Costco'")
    assert matches("kind == 'expense'")


def test_date_comparison_uses_iso_strings():
    assert matches("date >= '2026-10-01'")
    assert matches("date < '2025-01-01'") is False


def test_boolean_logic():
    assert matches("category == 'groceries' and amount >= 12")
    assert matches("category == 'dining' or amount == 12.5")
    assert matches("not (category == 'dining')")
    assert matches("(category == 'dining' or category == 'groceries') and amount > 10")


def test_membership():
    assert matches("category in ('groceries', 'dining')")
    assert matches("category not in ('rent', 'transport')")


def test_arithmetic():
    assert matches("amount * 2 == 25")
    assert matches("amount / 5 == 2.5")
    assert matches("amount + 1 > 13")


def test_unknown_field_rejected():
    with pytest.raises(ExpressionError, match="unknown field"):
        rules.compile_expression("balance > 100")


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('echo hi')",
        "amount.__class__",
        "(lambda: 1)()",
        "open('/etc/passwd')",
        "f'{amount}'",
        "[x for x in (1, 2)]",
    ],
)
def test_unsafe_expressions_rejected(expression):
    with pytest.raises(ExpressionError):
        rules.compile_expression(expression)


def test_syntax_error_is_clean():
    with pytest.raises(ExpressionError, match="syntax error"):
        rules.compile_expression("amount >= ")
    with pytest.raises(ExpressionError, match="empty"):
        rules.compile_expression("   ")


def test_type_mismatch_rejected_at_rule_add():
    with pytest.raises(ExpressionError, match="cannot be evaluated"):
        rules.validate_rule_expression("amount > 'abc'", default_config())


def test_good_expression_passes_rule_add_validation():
    rules.validate_rule_expression("amount >= 1000 and category == 'groceries'", default_config())


def test_run_rules_emits_flag_on_match():
    cfg = default_config()
    rule = Rule(id="1", description="Big grocery", expression="amount >= 12 and category == 'groceries'")
    flags = rules.run_rules([rule], make_tx(), cfg)
    assert len(flags) == 1
    assert flags[0].source == "rule:1"
    assert flags[0].transaction_ids == [7]
    assert "Big grocery" in flags[0].message


def test_run_rules_no_flag_when_no_match():
    cfg = default_config()
    rule = Rule(id="1", description="Huge", expression="amount >= 1000")
    assert rules.run_rules([rule], make_tx(), cfg) == []


def test_run_rules_skips_rules_that_cannot_evaluate_this_row():
    cfg = default_config()
    rule = Rule(id="1", description="Broken", expression="merchant > 5")
    assert rules.run_rules([rule], make_tx(), cfg) == []


def test_validate_rules_reports_rule_id():
    with pytest.raises(ExpressionError, match="rule 3"):
        rules.validate_rules([Rule(id="3", description="x", expression="amount >")])
