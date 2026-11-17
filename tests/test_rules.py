"""Field rules: safe ast evaluation, validation and flag emission."""

from __future__ import annotations

import pytest

from pft.errors import ExpressionError
from pft.models.config import Config
from pft.models.rule import Rule
from pft.services import rules


def matches(expression, tx, cfg):
    values = rules.values_for(tx, cfg)
    return rules.evaluate(rules.compile_expression(expression), values)


def test_simple_comparison(make_tx, cfg):
    assert matches("amount > 10", make_tx(), cfg) is True
    assert matches("amount > 13", make_tx(), cfg) is False


def test_amount_is_in_currency_units(make_tx, cfg):
    assert matches("amount == 12.5", make_tx(), cfg)
    assert matches("amount >= 12.50", make_tx(), cfg)


def test_float_literals_are_exact_decimals(make_tx, cfg):
    """12.30 must not suffer binary-float drift against the Decimal amount."""
    values = rules.values_for(make_tx(amount_cents=1230), cfg)  # $12.30
    assert rules.evaluate(rules.compile_expression("amount == 12.30"), values) is True
    assert (
        rules.evaluate(rules.compile_expression("amount + 0.20 == 12.5"), values)
        is True
    )


def test_string_fields(make_tx, cfg):
    assert matches("category == 'groceries'", make_tx(), cfg)
    assert matches("merchant != 'BigBox'", make_tx(), cfg)
    assert matches("kind == 'expense'", make_tx(), cfg)


def test_date_comparison_uses_iso_strings(make_tx, cfg):
    assert matches("date >= '2026-10-01'", make_tx(), cfg)
    assert matches("date < '2025-01-01'", make_tx(), cfg) is False


def test_boolean_logic(make_tx, cfg):
    assert matches("category == 'groceries' and amount >= 12", make_tx(), cfg)
    assert matches("category == 'dining' or amount == 12.5", make_tx(), cfg)
    assert matches("not (category == 'dining')", make_tx(), cfg)
    assert matches(
        "(category == 'dining' or category == 'groceries') and amount > 10",
        make_tx(),
        cfg,
    )


def test_membership(make_tx, cfg):
    assert matches("category in ('groceries', 'dining')", make_tx(), cfg)
    assert matches("category not in ('rent', 'transport')", make_tx(), cfg)


def test_arithmetic(make_tx, cfg):
    assert matches("amount * 2 == 25", make_tx(), cfg)
    assert matches("amount / 5 == 2.5", make_tx(), cfg)
    assert matches("amount + 1 > 13", make_tx(), cfg)


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


def test_type_mismatch_rejected_at_rule_add(cfg):
    with pytest.raises(ExpressionError, match="cannot be evaluated"):
        rules.validate_rule_expression("amount > 'abc'", cfg)


def test_good_expression_passes_rule_add_validation(cfg):
    rules.validate_rule_expression("amount >= 1000 and category == 'groceries'", cfg)


def test_run_rules_emits_flag_on_match(make_tx, cfg):
    rule = Rule(
        id="1",
        description="Big grocery",
        expression="amount >= 12 and category == 'groceries'",
    )
    flags = rules._run_rules([rule], make_tx(id=7), cfg)
    assert len(flags) == 1
    assert flags[0].source == "rule:1"
    assert flags[0].transaction_ids == [7]
    assert "Big grocery" in flags[0].message


def test_run_rules_no_flag_when_no_match(make_tx, cfg):
    rule = Rule(id="1", description="Huge", expression="amount >= 1000")
    assert rules._run_rules([rule], make_tx(), cfg) == []


def test_run_rules_skips_rules_that_cannot_evaluate_this_row(make_tx, cfg):
    rule = Rule(id="1", description="Broken", expression="merchant > 5")
    assert rules._run_rules([rule], make_tx(), cfg) == []


def test_validate_rules_reports_rule_id():
    with pytest.raises(ExpressionError, match="rule 3"):
        rules.validate_rules([Rule(id="3", description="x", expression="amount >")])
