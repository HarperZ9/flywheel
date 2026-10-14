"""externalization ablation falsifier — the ONE defensible claim, earned or dead.

The capstone's load-bearing test: does a NON-SELF-AUTHORED criterion catch a cheat
that a self-authored one accepts, with the refutation actually EXECUTING (not a
theatrical MATCH)? If yes, externalization does real work. If the external check
also accepted the cheat, the whole claim would be dead — so this test is the
make-or-break, not decoration.
"""
from harness.externalization_ablation import run_ablation, CHEAT, HONEST


def test_external_criterion_catches_cheat_selfauthored_accepts(tmp_path):
    r = run_ablation(tmp_path, candidate=CHEAT)
    # the producer's hand-picked criterion waves the cheat through...
    assert r["self_authored_verdict"] == "PASS"
    # ...the non-self-authored criterion catches it, and the refutation FIRES
    assert r["external_verdict"] == "FAIL"
    assert r["externalization_caught_cheat"] is True
    assert r["refutation_executed"] is True, "the refutation must EXECUTE, not be theatrical"


def test_honest_work_both_criteria_agree(tmp_path):
    # the honest bound: externalization only bites when there is a cheat. On correct
    # work the two criteria agree — no free lunch, no manufactured advantage.
    r = run_ablation(tmp_path, candidate=HONEST)
    assert r["self_authored_verdict"] == "PASS" and r["external_verdict"] == "PASS"
    assert r["externalization_caught_cheat"] is False


# Silent-zero guard. Before it, a criterion run that never executed a test read as a
# verdict: with pytest missing, both criteria read FAIL and the externalization
# dimension scored 0 with no error (checking-cost baseline finding #6, 2026-10-04).

import sys

import pytest

import harness.externalization_ablation as ea


def test_missing_pytest_raises_not_scores_zero(tmp_path, monkeypatch):
    # -S skips site-packages, so this interpreter cannot import pytest: the real
    # failure mode from the Linux CI run, reproduced without uninstalling anything.
    monkeypatch.setattr(ea, "PYTEST_CMD", [sys.executable, "-S", "-m", "pytest"])
    with pytest.raises(ea.PytestDidNotRun, match="no readable verdict"):
        ea.run_ablation(tmp_path, candidate=CHEAT)


def test_missing_pytest_fails_the_domain_sweep_loudly(tmp_path, monkeypatch):
    monkeypatch.setattr(ea, "PYTEST_CMD", [sys.executable, "-S", "-m", "pytest"])
    with pytest.raises(ea.PytestDidNotRun):
        ea.run_all_domains(tmp_path)


def test_zero_collected_tests_raise(tmp_path):
    with pytest.raises(ea.PytestDidNotRun, match="exit 5"):
        ea.run_ablation(tmp_path, candidate=CHEAT, self_test="x = 1\n")


def test_all_skipped_is_not_a_pass(tmp_path):
    skipped = ("import pytest\n"
               "@pytest.mark.skip(reason='planted')\n"
               "def test_a():\n    assert False\n")
    with pytest.raises(ea.PytestDidNotRun, match="skipped"):
        ea.run_ablation(tmp_path, candidate=CHEAT, self_test=skipped)


@pytest.mark.parametrize("rc,out,expected", [
    (0, "3 passed in 0.01s", True),
    (1, "1 failed, 2 passed in 0.02s", False),
])
def test_read_verdict_accepts_real_runs(rc, out, expected):
    assert ea._read_verdict(rc, out, "") is expected


@pytest.mark.parametrize("rc,out,err", [
    (1, "", "No module named pytest"),
    (5, "no tests ran in 0.00s", ""),
    (2, "1 error in 0.03s", ""),
    (0, "1 skipped in 0.01s", ""),
    (1, "1 failed, 1 error in 0.02s", ""),
])
def test_read_verdict_rejects_unreadable_runs(rc, out, err):
    with pytest.raises(ea.PytestDidNotRun):
        ea._read_verdict(rc, out, err)
