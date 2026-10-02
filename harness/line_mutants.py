"""line_mutants.py -- one-operator mutants for chosen lines of a Python file.

Each mutant replaces exactly one expression or statement, located by its AST
position, so every other byte of the file stays as it was. Lines with low
signal ("arid" code: imports, docstrings, logging and print calls, bare
strings) get no mutant, following Google's finding that suppressing them is
what makes surfaced mutants useful.

Operators: arithmetic swap, comparison boundary and negation, and/or swap,
`not` removal, boolean and integer constant change, `return X` to
`return None`, condition negation, and call-statement removal.
Standard library only.
"""
from __future__ import annotations

import ast
import random
from dataclasses import dataclass

_BIN = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Add, ast.Div: ast.Mult,
        ast.FloorDiv: ast.Mult, ast.Mod: ast.Mult}
_CMP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt,
        ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.In: ast.NotIn, ast.NotIn: ast.In,
        ast.Is: ast.IsNot, ast.IsNot: ast.Is}
_ARID_CALLS = ("log", "logger", "logging", "print", "warn", "warnings", "debug", "info")


@dataclass
class Mutant:
    path: str
    line: int
    operator: str
    original: str
    mutated: str
    source: str        # the whole mutated file


def _segment_span(lines, node):
    return node.lineno, node.col_offset, node.end_lineno, node.end_col_offset


def _replace(source: str, node, text: str) -> str:
    lines = source.splitlines(keepends=True)
    l0, c0, l1, c1 = _segment_span(lines, node)
    # col offsets are UTF-8 byte offsets; convert through bytes per line
    head = lines[l0 - 1].encode("utf-8")[:c0].decode("utf-8", "replace")
    tail = lines[l1 - 1].encode("utf-8")[c1:].decode("utf-8", "replace")
    return "".join(lines[:l0 - 1]) + head + text + tail + "".join(lines[l1:])


def _arid(node, parents) -> bool:
    for anc in [node, getattr(node, "value", None), *parents]:
        if isinstance(anc, (ast.Import, ast.ImportFrom)):
            return True
        if isinstance(anc, ast.Call):
            name = anc.func.attr if isinstance(anc.func, ast.Attribute) else \
                getattr(anc.func, "id", "")
            root = anc.func
            while isinstance(root, ast.Attribute):
                root = root.value
            rid = getattr(root, "id", "")
            if name.lower() in _ARID_CALLS or rid.lower() in _ARID_CALLS:
                return True
        if isinstance(anc, ast.Raise):
            return True
    return False


def _candidates(tree):
    """(node, operator, replacement_text) for every mutable node."""
    parents: dict = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    def chain(n):
        out = []
        while n in parents and not isinstance(n, ast.stmt):
            n = parents[n]
            out.append(n)
        return out

    for node in ast.walk(tree):
        if not hasattr(node, "lineno") or _arid(node, chain(node)):
            continue
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            new = ast.BinOp(node.left, _BIN[type(node.op)](), node.right)
            yield node, "arith", "(" + ast.unparse(new) + ")"
        elif isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in _CMP:
            new = ast.Compare(node.left, [_CMP[type(node.ops[0])]()], node.comparators)
            yield node, "compare", "(" + ast.unparse(new) + ")"
        elif isinstance(node, ast.BoolOp):
            new = ast.BoolOp(ast.Or() if isinstance(node.op, ast.And) else ast.And(), node.values)
            yield node, "boolop", "(" + ast.unparse(new) + ")"
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            yield node, "not-removed", "(" + ast.unparse(node.operand) + ")"
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            yield node, "constant", repr(not node.value)
        elif isinstance(node, ast.Constant) and type(node.value) is int:
            yield node, "constant", repr(node.value + 1)
        elif isinstance(node, ast.Return) and node.value is not None and not (
                isinstance(node.value, ast.Constant) and node.value.value is None):
            yield node, "return-none", "return None"
        elif isinstance(node, (ast.If, ast.While)):
            yield node.test, "negate-condition", "(not (" + ast.unparse(node.test) + "))"
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            yield node, "call-removed", "pass"


def mutants_for_lines(path: str, source: str, lines: set, rng: random.Random) -> list:
    """At most one mutant per requested line, the operator drawn by rng."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    docstrings = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(getattr(body[0], "value", None), ast.Constant) \
                and isinstance(body[0].value.value, str):
            docstrings.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
    by_line: dict = {}
    for node, op, text in _candidates(tree):
        if node.lineno in lines and node.lineno not in docstrings:
            by_line.setdefault(node.lineno, []).append((node, op, text))
    out = []
    src_lines = source.splitlines()
    for line in sorted(by_line):
        node, op, text = rng.choice(by_line[line])
        mutated = _replace(source, node, text)
        try:
            compile(mutated, path, "exec", dont_inherit=True)
        except (SyntaxError, ValueError):
            continue
        if mutated == source:
            continue
        new_line = mutated.splitlines()[line - 1] if line - 1 < len(mutated.splitlines()) else ""
        out.append(Mutant(path, line, op, src_lines[line - 1].strip(), new_line.strip(), mutated))
    return out
