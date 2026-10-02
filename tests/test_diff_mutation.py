"""Diff-scoped mutation: only the change's lines are mutated, only the tests that
reach a line run against its mutant, and survivors are named. There is no score
field to optimize."""
import random
import subprocess
import textwrap

import pytest

from harness.line_mutants import mutants_for_lines
from harness.suite_audit import audit_suite_diff

OLD = "def clamp(x, lo, hi):\n    return x\n"
NEW = textwrap.dedent("""
    import logging

    LOG = logging.getLogger(__name__)


    def clamp(x, lo, hi):
        LOG.debug("clamp %s", x)
        if x < lo:
            return lo
        if x > hi:
            return hi
        return x
""").lstrip()


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _repo(tmp_path, test_text):
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    (repo / "calc.py").write_text(OLD, encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_calc.py").write_text("def test_placeholder():\n    pass\n",
                                                 encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    (repo / "calc.py").write_text(NEW, encoding="utf-8")
    (repo / "tests" / "test_calc.py").write_text(textwrap.dedent(test_text), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "head")
    return repo


STRONG = """
    from calc import clamp

    def test_clamps_both_ends():
        assert clamp(-5, 0, 10) == 0
        assert clamp(0, 0, 10) == 0
        assert clamp(10, 0, 10) == 10
        assert clamp(15, 0, 10) == 10
        assert clamp(5, 0, 10) == 5
"""
WEAK = """
    from calc import clamp

    def test_runs():
        assert clamp(5, 0, 10) is not None
"""


# Each audit runs pytest once per mutant, so these get more than the suite's
# 60 s default under a loaded machine.
@pytest.mark.timeout(300)
def test_a_weak_test_leaves_named_survivors_on_changed_lines(tmp_path):
    weak = audit_suite_diff(_repo(tmp_path, WEAK), "HEAD~1", "HEAD", seed=3)
    assert weak["schema"] == "flywheel.suite-audit-diff/v1"
    assert weak["status"] == "complete" and weak["selection"] == "coverage"
    assert [(s["line"], s["mutant"]) for s in weak["survivors"]] ==         [(10, "if (x >= hi):"), (8, "if (not (x < lo)):")]
    assert "kill_rate" not in weak and "score" not in weak
    assert weak["seed"] == 3 and weak["does_not_prove"]


@pytest.mark.timeout(300)
def test_a_strong_test_kills_every_mutant_but_the_equivalent_one(tmp_path):
    strong = audit_suite_diff(_repo(tmp_path, STRONG), "HEAD~1", "HEAD", seed=3)
    # x > hi -> x >= hi is an equivalent mutant for clamp (at x == hi both return
    # hi), so no test can kill it. It surfaces as a prompt for a reviewer to
    # dismiss; this is why survivors are never turned into a score.
    assert [(s["line"], s["mutant"]) for s in strong["survivors"]] == [(10, "if (x >= hi):")]
    assert strong["killed"] == strong["run"] - 1 > 0


@pytest.mark.timeout(300)
def test_the_seed_replays_the_same_mutants(tmp_path):
    repo = _repo(tmp_path, WEAK)
    a = audit_suite_diff(repo, "HEAD~1", "HEAD", seed=11)
    b = audit_suite_diff(repo, "HEAD~1", "HEAD", seed=11)
    assert [(s["line"], s["mutant"]) for s in a["survivors"]] == \
        [(s["line"], s["mutant"]) for s in b["survivors"]]


def test_a_budget_of_zero_reports_a_partial_run(tmp_path):
    receipt = audit_suite_diff(_repo(tmp_path, STRONG), "HEAD~1", "HEAD", seed=1,
                               budget_seconds=0)
    assert receipt["status"] == "partial"
    assert receipt["run"] == 0 and receipt["skipped_for_budget"] == receipt["planned"] > 0


@pytest.mark.timeout(300)
def test_lines_no_test_reaches_are_not_covered_not_survivors(tmp_path):
    test_text = "from calc import clamp\n\ndef test_low():\n    assert clamp(-1, 0, 10) == 0\n"
    receipt = audit_suite_diff(_repo(tmp_path, test_text), "HEAD~1", "HEAD", seed=5)
    if receipt["selection"] == "coverage":
        lines = {row["line"] for row in receipt["not_covered"]}
        assert lines & {10, 11}, "the x > hi branch is never reached by test_low"
        assert not {s["line"] for s in receipt["survivors"]} & {10, 11}


def test_only_changed_non_arid_lines_get_one_mutant_each():
    lines = set(range(1, 13))
    mutants = mutants_for_lines("calc.py", NEW, lines, random.Random(0))
    got = {m.line for m in mutants}
    assert got == {8, 9, 10, 11, 12}
    assert 7 not in got, "a logging call is arid"
    assert len(mutants) == len(got)
    for m in mutants:
        assert m.source != NEW
        assert NEW.splitlines()[:m.line - 1] == m.source.splitlines()[:m.line - 1]
