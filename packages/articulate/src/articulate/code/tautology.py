"""articulate.code.tautology -- checks in a test that cannot fail (check B4).

The cheap subset only: `assert True`, a value compared with itself (directly or
through a local name), the code's own output used as its expected value, an
assertion whose only subject is a mock the test configured, a test with no check
at all, and a test whose only checks are bare `assert_called` calls.

Static and approximate. A name is resolved through single assignments inside the
same test, at most three hops; nothing outside the test body is resolved, so a
tautology spread across fixtures is not seen. Standard library only.
"""
from __future__ import annotations

import ast
import builtins
import re

from .strength import call_name, dotted, norm

_EXPECT_NAME = re.compile(r"expect|golden|snapshot|want|baseline|reference", re.I)
_SELF_OPS = (ast.Eq, ast.Is, ast.GtE, ast.LtE)
_EQ_UNITTEST = {"assertEqual", "assertEquals", "assertIs", "assertCountEqual",
                "assertListEqual", "assertDictEqual", "assertSequenceEqual"}
_BUILTINS = set(dir(builtins))


def _assignments(func) -> dict:
    """Names assigned exactly once by a plain `name = value` in the test."""
    seen, out = {}, {}
    for node in ast.walk(func):
        targets = []
        if isinstance(node, ast.Assign):
            targets = [(t, node.value) for t in node.targets]
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and node.value is not None:
            targets = [(node.target, node.value if isinstance(node, ast.AnnAssign) else None)]
        bound = []
        if isinstance(node, (ast.For, ast.AsyncFor, ast.NamedExpr, ast.comprehension)):
            bound = [node.target]
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            bound = [i.optional_vars for i in node.items if i.optional_vars is not None]
        for target in bound:
            for sub in ast.walk(target):
                if isinstance(sub, ast.Name):
                    seen[sub.id] = seen.get(sub.id, 0) + 2
        for target, value in targets:
            if isinstance(target, ast.Name):
                seen[target.id] = seen.get(target.id, 0) + 1
                out[target.id] = value
            else:
                for sub in ast.walk(target):
                    if isinstance(sub, ast.Name):
                        seen[sub.id] = seen.get(sub.id, 0) + 2
    for arg in func.args.args + func.args.kwonlyargs:
        seen[arg.arg] = seen.get(arg.arg, 0) + 2
    return {k: v for k, v in out.items() if seen.get(k) == 1 and v is not None}


_MUTABLE = (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)
_MUTABLE_CALLS = {"list", "dict", "set", "bytearray", "deque", "defaultdict", "Counter"}


def _mutable(value) -> bool:
    """A container the test can fill later (`calls = []`, then a fake appends)."""
    if isinstance(value, _MUTABLE):
        return True
    return isinstance(value, ast.Call) and call_name(value.func) in _MUTABLE_CALLS


def _resolve(node, assigned: dict, depth: int = 3, used=None):
    if depth and isinstance(node, ast.Name) and node.id in assigned             and not _mutable(assigned[node.id]):
        if used is not None:
            used.append(assigned[node.id])
        return _resolve(assigned[node.id], assigned, depth - 1, used)
    return node


def _quiet_between(func, values, line) -> bool:
    """No statement with a call runs between the first resolved assignment and
    the check, apart from those assignments. `before = snap(); act();
    assert snap() == before` is an unchanged-state check, not a tautology."""
    if not values:
        return True
    first = min(v.lineno for v in values)
    ids = {id(v) for v in values}
    for node in ast.walk(func):
        if not isinstance(node, ast.stmt) or not first <= node.lineno < line:
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and id(node.value) in ids:
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if _has_call(node) and node.lineno >= first and not _encloses(node, line):
            return False
    return True


def _encloses(node, line) -> bool:
    end = getattr(node, "end_lineno", node.lineno)
    return node.lineno < line <= end


def _has_call(node) -> bool:
    return any(isinstance(n, ast.Call) for n in ast.walk(node))


def _roots(node) -> set:
    out = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id not in _BUILTINS:
            out.add(sub.id)
    return out


def _pairs(func):
    """Every (left, right, line) pair an equality-style check compares."""
    for node in ast.walk(func):
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare) \
                and len(node.test.ops) == 1 and isinstance(node.test.ops[0], _SELF_OPS):
            yield node.test.left, node.test.comparators[0], node.lineno
        elif isinstance(node, ast.Call) and call_name(node.func) in _EQ_UNITTEST \
                and dotted(node.func).startswith("self.") and len(node.args) >= 2:
            yield node.args[0], node.args[1], node.lineno


def _self_compare(func, assigned) -> list:
    out = []
    for left, right, line in _pairs(func):
        if norm(left) == norm(right):
            out.append(("self-compare", line, "a value compared with itself"))
            continue
        used = []
        rl, rr = _resolve(left, assigned, used=used), _resolve(right, assigned, used=used)
        if norm(rl) != norm(rr):
            continue
        if not _has_call(rl):
            out.append(("self-compare", line, "both sides resolve to the same constant"))
        elif _direct_or_expected(left, right) and _quiet_between(func, used, line):
            out.append(("snapshot-self", line,
                        "the expected value is the code's own output, with no other oracle"))
    return out


def _direct_or_expected(left, right) -> bool:
    for side in (left, right):
        if isinstance(side, ast.Call):
            return True
        if isinstance(side, ast.Name) and _EXPECT_NAME.search(side.id):
            return True
    return False


def _mock_derived(facts, assigned) -> set:
    mocks = set(facts.mocks)
    for _ in range(3):
        for name, value in assigned.items():
            roots = _roots(value)
            if name not in mocks and roots and roots <= mocks:
                mocks.add(name)
    return mocks


def _mock_only(func, direct: set, mocks: set) -> list:
    """An assert whose every name is a mock, or a value read off one, and which
    reads a configured value (`return_value`, a call on the mock, or a name
    assigned from one). `assert m.called` and `m.call_count == 2` are not this:
    they check that the code under test used the mock."""
    out = []
    if not mocks:
        return out
    for node in ast.walk(func):
        if not isinstance(node, ast.Assert):
            continue
        roots = _roots(node.test)
        reads_value = any(
            (isinstance(sub, ast.Attribute) and sub.attr == "return_value")
            or (isinstance(sub, ast.Call) and _roots(sub.func) and _roots(sub.func) <= mocks)
            for sub in ast.walk(node.test))
        if roots and roots <= mocks and (reads_value or roots - direct):
            out.append(("mock-only", node.lineno,
                        "the assertion checks only a mock the test configured"))
        elif _compares_mock_call(node.test, direct):
            out.append(("mock-only", node.lineno,
                        "the compared value is what a mock the test configured returns"))
    return out


def _compares_mock_call(test, direct: set) -> bool:
    """`fake = Mock(return_value=X); assert fake(row) == X`: a side of the
    comparison is a direct call of a mock this test made."""
    if not isinstance(test, ast.Compare):
        return False
    return any(isinstance(side, ast.Call) and isinstance(side.func, ast.Name)
               and side.func.id in direct for side in [test.left, *test.comparators])


def tautologies(facts, helper_checks: dict) -> list:
    """B4 findings for one test: (rule, line, detail) tuples."""
    func = facts.node
    assigned = _assignments(func)
    out = [("assert-true", c.line, "a check that cannot fail")
           for c in facts.checks if c.strength == 0]
    out += _self_compare(func, assigned)
    out += _mock_only(func, set(facts.mocks), _mock_derived(facts, assigned))
    helper = [c for name in facts.helper_calls for c in helper_checks.get(name, [])]
    every = facts.checks + helper
    if not every and not facts.calls_checker:
        out.append(("no-assertion", func.lineno, "the test checks nothing it runs"))
    elif every and all(c.kind == "mock" and c.strength == 1 for c in every):
        out.append(("mock-called-only", func.lineno,
                    "the only check is that a mock was called, with no argument check"))
    seen, unique = set(), []
    for item in out:
        if (item[0], item[1]) not in seen:
            seen.add((item[0], item[1]))
            unique.append(item)
    return unique
