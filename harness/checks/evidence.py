"""evidence.py -- value-on-page and recompute checks.

value_on_page asks whether a quoted value appears in the source it cites.
recompute re-derives a claimed number from its inputs with a small arithmetic
evaluator that runs no names, attributes or calls outside a fixed list.
"""
from __future__ import annotations

import ast
import operator
import re

from ..contract_checks import agrees
from .receipt import FAIL, PASS, UNVERIFIABLE

_SPACE = re.compile(r"\s+")


def _norm(text: str, fold_case: bool) -> str:
    text = _SPACE.sub(" ", text).strip()
    return text.casefold() if fold_case else text


def _forms(value) -> list[str]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return [str(value)]
    forms = {str(value), f"{value:,}"}
    if isinstance(value, float) and value.is_integer():
        forms |= {str(int(value)), f"{int(value):,}"}
    return sorted(forms)


def value_on_page_check(subject, spec: dict) -> tuple[str, str, str]:
    """subject: the quoted value. spec: page (source text), fold_case (default
    False). Whitespace runs are collapsed on both sides before matching."""
    page = spec.get("page")
    if not isinstance(page, str) or not page.strip():
        return UNVERIFIABLE, "no_source", "the cited source is missing or empty"
    if subject is None or str(subject).strip() == "":
        return FAIL, "empty_value", "nothing was quoted"
    fold = bool(spec.get("fold_case", False))
    hay = _norm(page, fold)
    for form in _forms(subject):
        if _norm(form, fold) in hay:
            return PASS, "found", "the quoted value appears in the source"
    return FAIL, "not_on_page", "the quoted value does not appear in the cited source"


_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
        ast.Pow: operator.pow, ast.BitXor: operator.xor, ast.BitAnd: operator.and_,
        ast.BitOr: operator.or_, ast.LShift: operator.lshift, ast.RShift: operator.rshift}
_UNARY = {ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Invert: operator.invert,
          ast.Not: operator.not_}
_CMP = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
        ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}
_FUNCS = {"abs": abs, "min": min, "max": max, "sum": sum, "len": len, "round": round,
          "int": int, "float": float, "sorted": sorted}
_MAX_EXP = 64


def _eval(node, env: dict):
    if isinstance(node, ast.Expression):
        return _eval(node.body, env)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, bool, str)):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in env:
            raise NameError(f"unknown input {node.id!r}")
        return env[node.id]
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_eval(e, env) for e in node.elts]
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        left, right = _eval(node.left, env), _eval(node.right, env)
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_EXP:
            raise ValueError(f"exponent above {_MAX_EXP}")
        return _BIN[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand, env))
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in _CMP:
        return _CMP[type(node.ops[0])](_eval(node.left, env), _eval(node.comparators[0], env))
    if isinstance(node, ast.Subscript):
        return _eval(node.value, env)[_eval(node.slice, env)]
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in _FUNCS and not node.keywords):
        return _FUNCS[node.func.id](*[_eval(a, env) for a in node.args])
    raise ValueError(f"{type(node).__name__} is not allowed in a recompute expression")


def evaluate(expr: str, inputs: dict | None = None):
    """Evaluate an arithmetic expression over named inputs, nothing else."""
    return _eval(ast.parse(expr, mode="eval"), dict(inputs or {}))


def recompute_check(subject, spec: dict) -> tuple[str, str, str]:
    """subject: the claimed value. spec: expr, inputs, tolerance (default 0).
    A bool never agrees with a number (contract_checks.agrees)."""
    expr = spec.get("expr")
    if not isinstance(expr, str) or not expr.strip():
        return UNVERIFIABLE, "no_expression", "the spec gives no expression to recompute"
    try:
        derived = evaluate(expr, spec.get("inputs"))
    except (ValueError, NameError, TypeError, ZeroDivisionError, SyntaxError,
            IndexError, KeyError) as exc:
        return UNVERIFIABLE, "cannot_recompute", f"{type(exc).__name__}: {exc}"
    if agrees(subject, derived, float(spec.get("tolerance", 0))):
        return PASS, "agrees", "the claimed value matches the recomputation"
    return FAIL, "disagrees", "the claimed value does not match the recomputation"
