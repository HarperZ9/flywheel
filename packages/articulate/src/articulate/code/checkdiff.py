"""articulate.code.checkdiff -- did one test's own checks get fewer or weaker?

Compares the checks of one test before and after a change. Counts are
parametrize-aware: a test that runs N parameter rows counts each check N times,
so folding three asserts into one parametrized assert over three rows is not a
deletion. A check whose text still appears somewhere in the change's test files
as often as before has moved, not gone.

Two softenings, both general:
- A drop is "advisory" when the test now calls a helper or checker it did not
  call before. The checks moved somewhere this analyzer counts only roughly.
- A drop is "declared" when a new comment sits on or just above a new check,
  the form a reviewer reads as a stated reason.

A check that was unconditional and now runs only under an `if` is its own
finding (the guard can make it never run), unless the guard names a platform or
a missing dependency. Standard library only.
"""
from __future__ import annotations

from collections import Counter

from .markers import REASON, commented


def cumulative(facts, helpers) -> list:
    checks = list(facts.checks)
    for name in facts.helper_calls:
        checks += helpers.get(name, [])
    rows = max(1, getattr(facts, "param_cases", 1))
    return [rows * sum(1 for c in checks if c.strength >= s) for s in (1, 2, 3)]


def _credit_moved(t0, t1, world, c1) -> None:
    """Add back checks that left this test but survive elsewhere in the change."""
    removed = Counter(c.text for c in t0.checks) - Counter(c.text for c in t1.checks)
    by_text = {c.text: c for c in t0.checks}
    rows = max(1, getattr(t1, "param_cases", 1))
    for text, n in removed.items():
        if world.after[text] >= world.before[text]:
            for i in range(3):
                if by_text[text].strength >= i + 1:
                    c1[i] += n * rows


def _new_helper(t0, t1) -> bool:
    return bool(set(t1.helper_calls) - set(t0.helper_calls)) or \
        (t1.calls_checker and not t0.calls_checker)


def _stated_reason(t0, t1, lines0, lines1) -> bool:
    """A comment that is new in this change, on or above a check that is new."""
    old_texts = {c.text for c in t0.checks}
    old_lines = {ln.strip() for ln in lines0}
    for check in t1.checks:
        if check.text in old_texts:
            continue
        at = commented(lines1, check.line)
        if at and lines1[at - 1].strip() not in old_lines:
            return True
    return False


def compare_checks(name, t0, t1, inv0, inv1, path, ctx, finding) -> list:
    c0, c1 = cumulative(t0, inv0.helpers), cumulative(t1, inv1.helpers)
    _credit_moved(t0, t1, ctx.world, c1)
    line = t1.node.lineno
    if c1[0] < c0[0]:
        out = [finding("B2", "assertion-deleted", path, name, line,
                       f"checks {c0[0]} -> {c1[0]}")]
    elif c1[2] < c0[2] or c1[1] < c0[1]:
        out = [finding("B2", _weak_rule(t0, t1), path, name, line,
                       f"strong checks {c0[2]} -> {c1[2]}, narrowing {c0[1]} -> {c1[1]}")]
    else:
        out = subject_downgrades(name, t0, t1, path, finding)
    for item in out:
        if _new_helper(t0, t1):
            item.tier, item.detail = "advisory", item.detail + "; checks moved into a helper"
        elif _stated_reason(t0, t1, ctx.lines0, ctx.lines1):
            item.tier = "declared"
    return out + made_conditional(name, t0, t1, path, finding)


def _weak_rule(t0, t1) -> str:
    raises0 = max((c.strength for c in t0.checks if c.kind == "raises"), default=0)
    raises1 = max((c.strength for c in t1.checks if c.kind == "raises"), default=0)
    if raises1 and raises1 < raises0:
        return "raises-widened"
    return "assertion-weakened"


def subject_downgrades(name, t0, t1, path, finding) -> list:
    """Same count, but a subject's check got weaker: `x == 1` became `x is not None`."""
    best0, best1 = {}, {}
    for facts, best in ((t0, best0), (t1, best1)):
        for c in facts.checks:
            if c.subject:
                best[c.subject] = max(best.get(c.subject, 0), c.strength)
    for subject, s0 in best0.items():
        s1 = best1.get(subject)
        if s1 is not None and s1 < s0:
            return [finding("B2", "assertion-weakened", path, name, t1.node.lineno,
                            f"check on {subject[:60]} strength {s0} -> {s1}")]
    return []


def made_conditional(name, t0, t1, path, finding) -> list:
    """A check that always ran before and now runs only when an `if` holds."""
    always = {c.text for c in t0.checks if not c.cond}
    still = {c.text for c in t1.checks if not c.cond}
    out = []
    for check in t1.checks:
        if check.cond and check.text in always and check.text not in still:
            tier = "declared" if REASON.search(check.cond) else "finding"
            out.append(finding("B2", "assertion-made-conditional", path, name, check.line,
                               f"now runs only if {check.cond[:80]}", tier))
            still.add(check.text)
    return out
