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
