"""articulate.code.testdiff -- did this change make the tests check less? (B2 + B4)

Compares each Python test file before and after a change, test by test. B2
findings: a check deleted or replaced by a weaker form, a check made
conditional, a tolerance widened, a new skip or xfail, a broad `except` that
swallows the act step, an expected exception widened, a test deleted, a test
renamed so it no longer collects. B4 findings (see tautology.py) are checks
that cannot fail, reported only where this change introduced them.

Three tiers:
- "finding": the rule fired and nothing in the change explains it.
- "declared": the change states a reason (a declared test change, a comment on
  the changed line, a skip conditioned on a platform or missing dependency).
  The reason is shown, not verified.
- "advisory": the rule fired, but the change carries a structural explanation
  that ordinary commits have far more often than weakening ones (the same
  change edits source code, or a deleted test has a replacement). Advisory
  rows are shown for review and are not counted as findings.

Report-only by design. Static: nothing is imported or run.
"""
from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass

from .checkdiff import compare_checks
from .context import FileContext, bare, defined_symbols, is_test_path, world_for_file
from .markers import markers, module_skips, swallows, tolerances
from .pytests import inventory
from .tautology import tautologies

__all__ = ["Finding", "compare_file", "defined_symbols", "is_test_path", "apply_tiers"]

# Rules whose natural-commit precision does not survive a same-change source edit.
SOURCE_SENSITIVE = {"assertion-deleted", "assertion-weakened", "test-deleted"}


@dataclass
class Finding:
    check: str     # B2 or B4
    rule: str
    path: str
    test: str
    line: int
    detail: str
    tier: str = "finding"   # finding | declared | advisory


def _names_used(node) -> set:
    out = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            out.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            out.add(sub.attr)
    return out


def _moved(t0, world) -> bool:
    """The test, or every check it made, shows up elsewhere in the change."""
    if world.new_names[bare(t0.name)] or t0.body_dump in world.new_bodies:
        return True
    texts = Counter(c.text for c in t0.checks)
    return bool(texts) and all(world.after[t] >= world.before[t] for t in texts)


def _partner(t0, new, tests1):
    texts = Counter(c.text for c in t0.checks)
    return next((n for n in new if tests1[n].body_dump == t0.body_dump), None) \
        or next((n for n in new if texts and
                 Counter(c.text for c in tests1[n].checks) == texts), None)


def _unmatched(inv0, inv1, path, world) -> tuple:
    """Pair renamed tests; report deleted and no-longer-collected ones."""
    tests0, tests1 = inv0.tests(), inv1.tests()
    gone = [n for n in tests0 if n not in tests1]
    new = [n for n in tests1 if n not in tests0]
    pairs, out = [], []
    for name in gone:
        t0 = tests0[name]
        twin = next((f for f in inv1.functions.values()
                     if f.body_dump == t0.body_dump and f.name not in tests0), None)
        if twin is not None and not twin.collects:
            out.append(Finding("B2", "test-uncollected", path, name, twin.node.lineno,
                               f"renamed to {twin.name}, which pytest does not collect"))
            continue
        partner = _partner(t0, new, tests1)
        if partner is not None:
            new.remove(partner)
            pairs.append((name, partner))
            continue
        if _moved(t0, world):
            continue
        tier = "declared" if _names_used(t0.node) & world.removed_symbols else "finding"
        out.append(Finding("B2", "test-deleted", path, name, t0.node.lineno,
                           f"{len(t0.checks)} checks removed with the test", tier))
    return pairs, new, out


def compare_file(path, before, after, removed_symbols=frozenset(), world=None) -> "list | None":
    """Findings for one test file. `before` or `after` may be None (added or
    deleted file). Returns None when a side does not parse. `world` is the
    change-set context (context.build_world); without it the file stands alone."""
    inv0 = inventory(before) if before is not None else inventory("")
    inv1 = inventory(after) if after is not None else inventory("")
    if inv0 is None or inv1 is None:
        return None
    world = world or world_for_file(path, before, after, removed_symbols)
    ctx = FileContext(world, (before or "").splitlines(), (after or "").splitlines())
    tests0, tests1 = inv0.tests(), inv1.tests()
    pairs, new, out = _unmatched(inv0, inv1, path, world)
    pairs += [(n, n) for n in tests0 if n in tests1]
    for old_name, new_name in pairs:
        t0, t1 = tests0[old_name], tests1[new_name]
        out += compare_checks(new_name, t0, t1, inv0, inv1, path, ctx, Finding)
        out += markers(new_name, t0, t1, path, ctx.lines1, Finding)
        out += tolerances(new_name, t0, t1, path, ctx.lines1, Finding)
        out += swallows(new_name, t0, t1, path, Finding)
        if t0.body_dump != t1.body_dump:
            out += _b4(new_name, t1, inv1, path, ctx.lines1, (t0, inv0, ctx.lines0))
    for name in new:
        out += _b4(name, tests1[name], inv1, path, ctx.lines1)
    out += module_skips(before or "", after or "", path, ctx.lines1, Finding)
    return apply_tiers(out, world)


def _line_key(lines, rule, line) -> tuple:
    text = lines[line - 1].strip() if 1 <= line <= len(lines) else ""
    return (rule, text)


def _b4(name, facts, inv, path, lines, old=None) -> list:
    """Tautologies in a new or edited test, minus any the old version already had."""
    seen = Counter()
    if old is not None:
        facts0, inv0, lines0 = old
        seen.update(_line_key(lines0, r, ln) for r, ln, _ in tautologies(facts0, inv0.helpers))
    out = []
    for rule, line, detail in tautologies(facts, inv.helpers):
        key = _line_key(lines, rule, line)
        if seen[key] > 0:
            seen[key] -= 1
            continue
        out.append(Finding("B4", rule, path, name, line, detail))
    return out


def apply_tiers(findings, world) -> list:
    """Move source-sensitive findings to advisory when the change explains them."""
    for item in findings:
        if item.tier != "finding" or item.rule not in SOURCE_SENSITIVE:
            continue
        if world.source_changed:
            item.tier, item.detail = "advisory", item.detail + "; the change also edits source"
        elif item.rule == "test-deleted" and world.tests_added:
            item.tier, item.detail = "advisory", item.detail + "; the change adds other tests"
    return findings
