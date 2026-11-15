"""articulate.code.pytests -- an inventory of what each Python test checks.

One `ast` pass over a test module. For every collected test function it records
the checks it makes, each with a strength, plus its skip and xfail markers, its
tolerances, its broad exception handlers and the mocks it configures. Assertions
inside a module-level helper the test calls count through the helper, one call
level deep, so moving an assertion into a helper is not a deletion.

Strength is a coarse order: 3 pins a value (`==`, ordering, a specific expected
exception, a mock call with arguments), 2 narrows it (`in`, `not_called`, a
specific exception without `match`), 1 only says something exists or is truthy
(`is not None`, `isinstance`, bare truthiness, a broad `Exception`, a mock call
with no argument check). Strength 0 is a check that cannot fail.

Standard library only. Nothing here imports or runs the code under test.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from functools import lru_cache

from .strength import (BROAD_EXC, CHECKER_PREFIXES, MEDIUM_UNITTEST, MOCK_MEDIUM,
                       MOCK_STRONG, MOCK_WEAK, STRONG_UNITTEST, TOLERANCE_KW,
                       TRUTH_UNITTEST, WEAK_UNITTEST, call_name, compare_strength,
                       dotted, exc_names, is_mock_factory, norm, num, raises_strength)


@dataclass
class Check:
    kind: str          # assert, unittest, raises, mock, fail
    strength: int
    text: str          # normalized source of the checked expression
    line: int
    subject: str = ""  # left-hand side, used to pair a replacement
    cond: str = ""     # the enclosing `if` tests, when the check is conditional


@dataclass
class FuncFacts:
    name: str          # Class::method or function name
    node: ast.AST
    collects: bool
    checks: list = field(default_factory=list)
    markers: list = field(default_factory=list)    # (kind, line, conditional, text)
    tolerances: list = field(default_factory=list)  # (func, kw, value, line)
    swallows: list = field(default_factory=list)    # lines of broad except: pass
    helper_calls: list = field(default_factory=list)
    calls_checker: bool = False
    body_dump: str = ""
    mocks: set = field(default_factory=set)
    params: list = field(default_factory=list)
    patch_decorators: int = 0
    param_cases: int = 1    # rows a literal @pytest.mark.parametrize expands to


class _Walker(ast.NodeVisitor):
    """Collect checks, markers, tolerances and swallowed exceptions in one test."""

    def __init__(self, facts: FuncFacts, helpers: set):
        self.facts, self.helpers = facts, helpers
        self.mocks: set = set()
        self.branch_depth = 0
        self.conds: list = []

    def visit_If(self, node):
        self.visit(node.test)
        self.branch_depth += 1
        self.conds.append(norm(node.test))
        for stmt in node.body + node.orelse:
            self.visit(stmt)
        self.conds.pop()
        self.branch_depth -= 1

    def _add(self, kind, strength, text, node, subject=""):
        self.facts.checks.append(Check(kind, strength, text, node.lineno, subject,
                                       " and ".join(self.conds)))

    def visit_Assert(self, node):
        subject = norm(node.test.left) if isinstance(node.test, ast.Compare) else norm(node.test)
        self._add("assert", compare_strength(node.test), norm(node.test), node, subject)
        self._abs_bounds(node.test)
        self.generic_visit(node)

    def _abs_bounds(self, test):
        """`abs(a - b) < tol` is a tolerance too."""
        for sub in ast.walk(test):
            if isinstance(sub, ast.Compare) and len(sub.ops) == 1                     and isinstance(sub.ops[0], (ast.Lt, ast.LtE))                     and isinstance(sub.left, ast.Call) and call_name(sub.left.func) == "abs":
                value = num(sub.comparators[0])
                if value is not None:
                    self.facts.tolerances.append(("abs", "bound", value, sub.lineno))

    def visit_Raise(self, node):
        if node.exc is not None and call_name(getattr(node.exc, "func", node.exc)) == "AssertionError":
            self._add("fail", 2, "raise AssertionError", node)
        self.generic_visit(node)

    def visit_With(self, node):
        for item in node.items:
            ctx = item.context_expr
            if isinstance(ctx, ast.Call) and call_name(ctx.func) in ("raises", "assertRaises",
                                                                    "assertRaisesRegex"):
                self._add("raises", raises_strength(ctx), norm(ctx), node, "raises")
            if isinstance(ctx, ast.Call) and is_mock_factory(ctx) and item.optional_vars is not None:
                self.mocks.add(norm(item.optional_vars))
        self.generic_visit(node)

    visit_AsyncWith = visit_With

    def visit_Assign(self, node):
        if is_mock_factory(node.value):
            for target in node.targets:
                self.mocks.add(norm(target))
        self.generic_visit(node)

    def visit_Try(self, node):
        guards_checks = any(_is_check_stmt(sub) for stmt in node.body for sub in ast.walk(stmt))
        for handler in node.handlers:
            names = exc_names(handler.type) if handler.type is not None else []
            broad = handler.type is None or any(n in BROAD_EXC for n in names)
            quiet = all(isinstance(s, (ast.Pass, ast.Continue)) or
                        (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
                        for s in handler.body)
            eats_assert = (broad or "AssertionError" in names) and guards_checks                 and not any(_is_check_stmt(sub) or isinstance(sub, ast.Raise)
                            for stmt in handler.body for sub in ast.walk(stmt))
            if (broad and quiet) or eats_assert:
                self.facts.swallows.append(handler.lineno)
        self.generic_visit(node)

    visit_TryStar = visit_Try

    def visit_Call(self, node):
        name, dname = call_name(node.func), dotted(node.func)
        if name in ("raises",) and dname.startswith("pytest") and node.args and len(node.args) > 1:
            self._add("raises", raises_strength(node), norm(node), node, "raises")
        elif name in STRONG_UNITTEST | MEDIUM_UNITTEST | WEAK_UNITTEST | TRUTH_UNITTEST \
                and dname.startswith("self."):
            self._unittest(name, node)
        elif name in MOCK_STRONG | MOCK_MEDIUM | MOCK_WEAK:
            strength = 3 if name in MOCK_STRONG else 2 if name in MOCK_MEDIUM else 1
            self._add("mock", strength, norm(node), node, norm(node.func.value)
                      if isinstance(node.func, ast.Attribute) else "")
        elif dname in ("pytest.fail", "self.fail"):
            self._add("fail", 2, dname, node)
        elif dname in ("pytest.skip", "pytest.xfail", "pytest.importorskip"):
            conditional = name == "importorskip" or self.branch_depth > 0
            self.facts.markers.append((name, node.lineno, conditional, norm(node)))
        elif dname in ("pytest.approx", "approx", "math.isclose", "isclose") \
                or name in ("assert_allclose", "allclose", "isclose", "approx",
                            "assertAlmostEqual", "assert_almost_equal"):
            self._tolerance(name, node)
        if isinstance(node.func, ast.Name) and node.func.id in self.helpers:
            self.facts.helper_calls.append(node.func.id)
        if name.lower().startswith(CHECKER_PREFIXES) and not dname.startswith("self.assert"):
            self.facts.calls_checker = True
        self.generic_visit(node)

    def _unittest(self, name, node):
        args = node.args
        if name in TRUTH_UNITTEST:
            strength = compare_strength(args[0]) if args else 1
            strength = min(strength, 1) if not (args and isinstance(args[0], ast.Compare)) else strength
            if args and isinstance(args[0], ast.Constant):
                strength = 0 if args[0].value else 3
        elif name in ("assertRaises", "assertRaisesRegex"):
            strength = raises_strength(node)
        elif name in STRONG_UNITTEST:
            strength = 3
        elif name in MEDIUM_UNITTEST:
            strength = 2
        else:
            strength = 1
        subject = norm(args[0]) if args else ""
        text = name + "(" + ", ".join(norm(a) for a in args) + ")"
        self._add("unittest", strength, text, node, subject)
        if name in ("assertAlmostEqual", "assertNotAlmostEqual"):
            self._tolerance(name, node)

    def _tolerance(self, name, node):
        for kw in node.keywords:
            if kw.arg in TOLERANCE_KW:
                value = num(kw.value)
                if value is not None:
                    self.facts.tolerances.append((name, kw.arg, value, node.lineno))
        if name == "approx" and not any(k.arg in ("rel", "abs") for k in node.keywords):
            if len(node.args) < 2:
                self.facts.tolerances.append(("approx", "rel", 1e-6, node.lineno))


def _is_check_stmt(node) -> bool:
    """An assert, or a call that fails the test (`self.assertX`, `pytest.fail`)."""
    if isinstance(node, ast.Assert):
        return True
    if isinstance(node, ast.Call):
        dname = dotted(node.func)
        return dname.startswith("self.assert") or dname in ("pytest.fail", "self.fail")
    return False


def _markers(func) -> list:
    out = []
    for dec in func.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        dname, name = dotted(target), call_name(target)
        if name in ("skip", "skipif", "xfail", "skipIf", "skipUnless", "expectedFailure") \
                and ("mark" in dname or "unittest" in dname or dname == name):
            conditional = name in ("skipif", "skipIf", "skipUnless") or \
                (name == "xfail" and isinstance(dec, ast.Call) and bool(dec.args))
            out.append((name, dec.lineno, conditional, norm(dec)))
    return out


def _param_cases(func) -> int:
    """Rows a test runs: the product of each literal parametrize list's length."""
    total = 1
    for dec in func.decorator_list:
        if isinstance(dec, ast.Call) and call_name(dec.func) == "parametrize"                 and len(dec.args) >= 2 and isinstance(dec.args[1], (ast.List, ast.Tuple)):
            total *= max(1, len(dec.args[1].elts))
    return total


def _collects(name: str, cls) -> bool:
    if not name.startswith("test"):
        return False
    if cls is None:
        return True
    bases = {norm(b) for b in cls.bases}
    return cls.name.startswith("Test") or any(b.endswith("TestCase") for b in bases)


def _body_dump(func) -> str:
    return "\n".join(ast.dump(stmt) for stmt in func.body)


def module_helpers(tree) -> dict:
    """Module-level non-test functions, by name."""
    return {n.name: n for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not n.name.startswith("test")}


def _facts_for(func, cls, helpers) -> FuncFacts:
    name = f"{cls.name}::{func.name}" if cls is not None else func.name
    facts = FuncFacts(name, func, _collects(func.name, cls))
    facts.markers = _markers(func) + (_markers(cls) if cls is not None else [])
    walker = _Walker(facts, set(helpers))
    for stmt in func.body:
        walker.visit(stmt)
    facts.params = [a.arg for a in func.args.args]
    facts.patch_decorators = sum(1 for d in func.decorator_list if is_mock_factory(d))
    first = 1 if facts.params[:1] == ["self"] else 0
    facts.mocks = walker.mocks | set(facts.params[first:first + facts.patch_decorators])
    facts.body_dump = _body_dump(func)
    facts.param_cases = _param_cases(func)
    return facts


@dataclass
class Inventory:
    functions: dict   # name -> FuncFacts, every function and method
    helpers: dict     # module-level non-test function name -> its own checks

    def tests(self) -> dict:
        return {k: v for k, v in self.functions.items() if v.collects}


@lru_cache(maxsize=32)
def inventory(source: str) -> "Inventory | None":
    """Facts for every function in a test module. None when it does not parse.
    Cached by source text: the change-set pass and the per-file pass read the
    same files. Callers treat the result as read-only."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    helper_nodes = module_helpers(tree)
    functions = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions[node.name] = _facts_for(node, None, helper_nodes)
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    facts = _facts_for(item, node, helper_nodes)
                    functions[facts.name] = facts
    helpers = {name: functions[name].checks for name in helper_nodes}
    return Inventory(functions, helpers)
