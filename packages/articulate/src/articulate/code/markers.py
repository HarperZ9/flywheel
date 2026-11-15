"""articulate.code.markers -- skips, xfails, tolerances and swallowed exceptions.

The test-diff rules that read a marker or a keyword rather than an assertion: a
new skip or xfail, a widened tolerance, a broad `except` that swallows the act
step, and a whole-file skip. Each is "declared" when the change states a reason
next to it (a comment, or a skip conditioned on a platform or a missing
dependency). Standard library only.
"""
from __future__ import annotations

import ast
import re
from collections import Counter

REASON = re.compile(
    r"platform|win32|windows|linux|darwin|macos|posix|os\.name|version_info|"
    r"python ?3|importorskip|find_spec|which\(|not installed|missing|unavailable|"
    r"requires?|optional|has_|_available|available|no module|import", re.I)
_MODULE_SKIP = re.compile(r"pytest\.(skip|xfail|importorskip)\(")
_CHECK_LINE = re.compile(r"^\s*(assert\b|self\.assert|with pytest\.raises|pytest\.)")


def _comment_on(text) -> bool:
    if "#" not in text:
        return False
    return len(text.split("#", 1)[1].split()) >= 2


def commented(source_lines, line, reach=6) -> int:
    """Line number of a comment of two or more words on `line`, or above it
    across a run of comment and check lines (a block of edited asserts under one
    comment). 0 when there is none."""
    if 1 <= line <= len(source_lines) and _comment_on(source_lines[line - 1]):
        return line
    ln = line - 1
    while ln >= 1 and line - ln <= reach:
        text = source_lines[ln - 1]
        if text.strip().startswith("#"):
            if _comment_on(text):
                return ln
        elif not _CHECK_LINE.match(text):
            return 0
        ln -= 1
    return 0


def markers(name, t0, t1, path, lines1, finding) -> list:
    out = []
    old = Counter((m[0], m[3]) for m in t0.markers)
    for kind, line, conditional, text in t1.markers:
        if old[(kind, text)] > 0:
            old[(kind, text)] -= 1
            continue
        rule = "xfail-added" if "xfail" in kind.lower() or kind == "expectedFailure" \
            else "skip-added"
        reason = (conditional and REASON.search(text)) or kind == "importorskip"
        tier = "declared" if reason or commented(lines1, line) else "finding"
        out.append(finding("B2", rule, path, name, line, text[:120], tier))
    return out


def tolerances(name, t0, t1, path, lines1, finding) -> list:
    out = []
    old = {}
    for func, kw, value, _ in t0.tolerances:
        old.setdefault((func, kw), []).append(value)
    seen = Counter()
    for func, kw, value, line in t1.tolerances:
        key = (func, kw)
        values = old.get(key, [])
        index = seen[key]
        seen[key] += 1
        if index >= len(values):
            continue
        before = values[index]
        widened = value < before if kw == "places" else value > before
        if widened:
            tier = "declared" if commented(lines1, line) else "finding"
            out.append(finding("B2", "tolerance-widened", path, name, line,
                               f"{func} {kw} {before:g} -> {value:g}", tier))
    return out


def swallows(name, t0, t1, path, finding) -> list:
    if len(t1.swallows) > len(t0.swallows):
        return [finding("B2", "exception-swallowed", path, name, t1.swallows[-1],
                        "a broad except that does nothing was added")]
    return []


def _module_level(source) -> list:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    out = []
    for stmt in tree.body:
        text = " ".join(ast.unparse(stmt).split())
        targets = [t.id for t in getattr(stmt, "targets", []) if isinstance(t, ast.Name)]
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if "pytestmark" in targets or _MODULE_SKIP.search(text):
            out.append((text, stmt.lineno))
    return out


def module_skips(before, after, path, lines1, finding) -> list:
    """A whole file skipped: `pytestmark = ...skip` or a module-level skip call."""
    old = Counter(t for t, _ in _module_level(before))
    out = []
    for text, line in _module_level(after):
        if old[text] > 0:
            old[text] -= 1
            continue
        if "skip" not in text and "xfail" not in text:
            continue
        reason = REASON.search(text) and ("skipif" in text or "importorskip" in text
                                          or text.startswith("if "))
        tier = "declared" if reason or commented(lines1, line) else "finding"
        out.append(finding("B2", "skip-added", path, "<module>", line, text[:120], tier))
    return out
