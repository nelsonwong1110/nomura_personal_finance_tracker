"""Field rules: user-defined flag-only conditions over transaction fields.

Expressions use Python boolean syntax, e.g.::

    (category == 'groceries') and amount >= 1000

They are NEVER passed to eval(). Instead they are parsed with ``ast.parse`` and
evaluated by a whitelist walker that permits only boolean/comparison/arithmetic
operations over the exposed fields. Calls, attribute access, imports and every
other construct are rejected at ``rule add`` time — a config file is
user-editable, so a rule must never be able to execute code.
"""

from __future__ import annotations

import ast
import operator
from decimal import Decimal
from typing import Any, Callable, Dict, List

from pft.errors import ExpressionError
from pft.models.category import DEFAULT_CATEGORY
from pft.models.config import Config
from pft.models.flag import Flag
from pft.models.kind import Kind
from pft.models.rule import Rule
from pft.models.transaction import Transaction


def _resolve_amount(tx: Transaction, cfg: Config) -> Decimal:
    scale = Decimal(10) ** cfg.decimal_places
    return Decimal(tx.amount_cents) / scale


# The single extension point for rule fields: add one entry here to expose a new
# field to expressions; ALLOWED_FIELDS and values_for derive from this registry.
FIELD_RESOLVERS: Dict[str, Callable[[Transaction, Config], Any]] = {
    "kind": lambda tx, cfg: tx.kind.value,
    "amount": _resolve_amount,
    "date": lambda tx, cfg: tx.date,
    "merchant": lambda tx, cfg: tx.merchant,
    "category": lambda tx, cfg: tx.category,
}

ALLOWED_FIELDS = tuple(FIELD_RESOLVERS.keys())

_ALLOWED_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.UnaryOp,
    ast.Not,
    ast.USub,
    ast.UAdd,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Tuple,
    ast.List,
)

_BINARY_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
}

_COMPARE_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda left, right: left in right,
    ast.NotIn: lambda left, right: left not in right,
}


def compile_expression(expression: str) -> ast.Expression:
    """Parse and validate an expression, returning its AST.

    Raises ExpressionError for syntax errors and any non-whitelisted construct.
    """
    expr = str(expression).strip()
    if not expr:
        raise ExpressionError("expression is empty")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(
            f"syntax error in expression {expr!r}: {exc.msg}"
        ) from None

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ExpressionError(
                f"unsupported construct {type(node).__name__!r} in expression "
                f"{expr!r}; only field comparisons and boolean logic are allowed"
            )
        if isinstance(node, ast.Name) and node.id not in ALLOWED_FIELDS:
            raise ExpressionError(
                f"unknown field {node.id!r} in expression {expr!r}; "
                f"allowed fields: {', '.join(ALLOWED_FIELDS)}"
            )
        if isinstance(node, ast.Constant) and not isinstance(
            node.value, (str, int, float, bool)
        ):
            raise ExpressionError(
                f"unsupported literal {node.value!r} in expression {expr!r}"
            )
    return tree


def values_for(tx: Transaction, cfg: Config) -> Dict[str, Any]:
    """The field values a rule sees for a transaction.

    ``amount`` is exposed in currency units as a Decimal (e.g. 12.50), not in
    minor units, so expressions read naturally.
    """
    return {field: resolver(tx, cfg) for field, resolver in FIELD_RESOLVERS.items()}


def _eval(node: ast.AST, values: Dict[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return _eval(node.body, values)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, float):
            return Decimal(str(node.value))
        return node.value
    if isinstance(node, ast.Name):
        return values[node.id]
    if isinstance(node, ast.Tuple):
        return tuple(_eval(item, values) for item in node.elts)
    if isinstance(node, ast.List):
        return [_eval(item, values) for item in node.elts]
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            result: Any = True
            for operand in node.values:
                result = _eval(operand, values)
                if not result:
                    return result
            return result
        result = False
        for operand in node.values:
            result = _eval(operand, values)
            if result:
                return result
        return result
    if isinstance(node, ast.UnaryOp):
        operand = _eval(node.operand, values)
        if isinstance(node.op, ast.Not):
            return not operand
        if isinstance(node.op, ast.USub):
            return -operand
        return +operand
    if isinstance(node, ast.BinOp):
        left = _eval(node.left, values)
        right = _eval(node.right, values)
        return _BINARY_OPS[type(node.op)](left, right)
    if isinstance(node, ast.Compare):
        left = _eval(node.left, values)
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval(comparator, values)
            if not _COMPARE_OPS[type(op)](left, right):
                return False
            left = right
        return True
    raise ExpressionError(f"cannot evaluate node {type(node).__name__!r}")


def evaluate(tree: ast.Expression, values: Dict[str, Any]) -> bool:
    """Evaluate a compiled expression against a transaction's field values."""
    try:
        return bool(_eval(tree, values))
    except (TypeError, ZeroDivisionError) as exc:
        raise ExpressionError(f"could not evaluate expression: {exc}") from None


def sample_values(cfg: Config) -> Dict[str, Any]:
    """Representative values used to sanity-check a new expression."""
    sample = Transaction(
        kind=Kind.EXPENSE,
        amount_cents=1000,
        date="2026-01-01",
        merchant="sample",
        category=DEFAULT_CATEGORY,
    )
    return values_for(sample, cfg)


def validate_rule_expression(expression: str, cfg: Config) -> None:
    """Validate a rule expression for addition: parse plus sample evaluation."""
    tree = compile_expression(expression)
    try:
        evaluate(tree, sample_values(cfg))
    except ExpressionError as exc:
        raise ExpressionError(
            f"expression {expression!r} cannot be evaluated: {exc}"
        ) from None


def validate_rules(rules_to_check: List[Rule]) -> None:
    """Validate all stored rules' syntax (called when config is loaded)."""
    for rule in rules_to_check:
        try:
            compile_expression(rule.expression)
        except ExpressionError as exc:
            raise ExpressionError(
                f"rule {rule.id} ({rule.description}): {exc}"
            ) from None


def _run_rules(rules_to_run: List[Rule], tx: Transaction, cfg: Config) -> List[Flag]:
    """Evaluate all rules for one transaction; return a Flag per match.

    A rule that cannot be evaluated against this particular row (e.g. a type
    mismatch) is skipped rather than crashing the write path.
    """
    values = values_for(tx, cfg)
    flags: List[Flag] = []
    for rule in rules_to_run:
        try:
            matched = evaluate(compile_expression(rule.expression), values)
        except ExpressionError:
            continue
        if matched:
            flags.append(
                Flag(
                    source=f"rule:{rule.id}",
                    message=f"{rule.description} (expression: {rule.expression})",
                    transaction_ids=[tx.id] if tx.id is not None else [],
                )
            )
    return flags
