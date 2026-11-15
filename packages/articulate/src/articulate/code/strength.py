"""articulate.code.strength -- how much one check in a test pins down.

Shared vocabulary for the test-diff analyzer: the assertion forms it knows, and a
coarse strength for each. 3 pins a value, 2 narrows it, 1 only says something exists
or is truthy, 0 cannot fail. Standard library only.
"""
from __future__ import annotations

import ast

STRONG_UNITTEST = {
    "assertEqual", "assertEquals", "assertNotEqual", "assertListEqual",
    "assertDictEqual", "assertTupleEqual", "assertSetEqual", "assertSequenceEqual",
    "assertMultiLineEqual", "assertCountEqual", "assertAlmostEqual",
    "assertNotAlmostEqual", "assertGreater", "assertGreaterEqual", "assertLess",
    "assertLessEqual", "assertRegex", "assertNotRegex", "assertIs", "assertIsNone",
    "assertRaisesRegex", "assertWarnsRegex", "assertDictContainsSubset"}
MEDIUM_UNITTEST = {"assertIn", "assertNotIn", "assertIsNot", "assertRaises",
                   "assertWarns", "assertLogs", "assertNoLogs"}
WEAK_UNITTEST = {"assertIsNotNone", "assertIsInstance", "assertNotIsInstance"}
TRUTH_UNITTEST = {"assertTrue", "assertFalse", "assert_"}
MOCK_STRONG = {"assert_called_with", "assert_called_once_with", "assert_any_call",
               "assert_has_calls", "assert_awaited_with", "assert_awaited_once_with",
               "assert_any_await", "assert_has_awaits"}
MOCK_MEDIUM = {"assert_not_called", "assert_not_awaited"}
MOCK_WEAK = {"assert_called", "assert_called_once", "assert_awaited",
             "assert_awaited_once"}
BROAD_EXC = {"Exception", "BaseException"}
MOCK_FACTORIES = ("Mock", "MagicMock", "AsyncMock", "NonCallableMock",
                  "NonCallableMagicMock", "create_autospec", "patch", "patch.object")
TOLERANCE_KW = {"rel", "abs", "rel_tol", "abs_tol", "rtol", "atol", "places", "delta"}
CHECKER_PREFIXES = ("assert", "check", "verify", "expect", "validate", "must", "ensure")


def norm(node) -> str:
    try:
        return " ".join(ast.unparse(node).split())
    except Exception:  # noqa: BLE001 -- unparse of exotic nodes
        return ast.dump(node)


def call_name(func) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def dotted(func) -> str:
    parts = []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if isinstance(func, ast.Name):
        parts.append(func.id)
    return ".".join(reversed(parts))


def compare_strength(test) -> int:
    """Strength of the expression an `assert` checks."""
    if isinstance(test, ast.Constant):
        return 0 if test.value else 3
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return 1 if not isinstance(test.operand, ast.Compare) else compare_strength(test.operand)
    if isinstance(test, ast.BoolOp):
        parts = [compare_strength(v) for v in test.values]
        return min(parts) if isinstance(test.op, ast.And) else 1
    if isinstance(test, ast.Compare):
        op, right = test.ops[0], test.comparators[0]
        if isinstance(op, ast.IsNot) and isinstance(right, ast.Constant) and right.value is None:
            return 1
        if isinstance(op, (ast.In, ast.NotIn)):
            return 2
        if isinstance(op, ast.NotEq):
            return 2
        return 3
    if isinstance(test, ast.Call):
        name = call_name(test.func)
        if name in ("all", "any"):
            return 2
        return 1
    return 1


def exc_names(node) -> list:
    if isinstance(node, ast.Tuple):
        return [n for e in node.elts for n in exc_names(e)]
    return [call_name(node) or norm(node)]


def raises_strength(call: ast.Call) -> int:
    if not call.args:
        return 1
    names = exc_names(call.args[0])
    if any(n in BROAD_EXC for n in names):
        return 1
    has_match = any(k.arg == "match" for k in call.keywords) or len(call.args) > 1 \
        and call_name(call.func) == "assertRaisesRegex"
    return 3 if has_match else 2


def num(node):
    try:
        value = ast.literal_eval(node)
    except Exception:  # noqa: BLE001 -- non-literal tolerance
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            try:
                return float(ast.literal_eval(node.left)) ** float(ast.literal_eval(node.right))
            except Exception:  # noqa: BLE001
                return None
        return None
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def is_mock_factory(call) -> bool:
    if not isinstance(call, ast.Call):
        return False
    dname = dotted(call.func)
    return any(dname == f or dname.endswith("." + f) for f in MOCK_FACTORIES)
