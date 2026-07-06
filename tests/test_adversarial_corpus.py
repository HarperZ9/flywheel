"""adversarial corpus falsifier — the gate must be SOUND and NON-THEATRICAL.

Two obligations:
  SOUNDNESS  — the real closure (transitive_verdicts) refuses every false-accept
               attack (false_accepts == 0) and passes every control (no
               over-rejection).
  DISCRIMINATION — the corpus CATCHES deliberately weakened closures
               (false_accepts > 0), proving it asserts something. A corpus that
               passed a broken verifier would be theatre.
"""
import pytest

from harness.transitive_witness import transitive_verdicts, MATCH
from harness.adversarial_corpus import (
    corpus, run_corpus, naive_closure, depth_limited_closure, gate_report)

ATTACKS = corpus()
FALSE_ACCEPT = [a for a in ATTACKS if a.kind == "false-accept"]
CONTROLS = [a for a in ATTACKS if a.kind == "control"]


def test_real_closure_is_sound():
    r = run_corpus(transitive_verdicts)
    assert r["false_accepts"] == 0, f"false MATCH served: {r['false_accept_names']}"
    assert r["over_rejects"] == 0, f"over-rejected controls: {r['over_reject_names']}"
    assert "SOUND" in gate_report(r)


@pytest.mark.parametrize("attack", FALSE_ACCEPT, ids=lambda a: a.name)
def test_each_false_accept_attack_is_refused(attack):
    v = transitive_verdicts(attack.nodes)[attack.target]
    assert v != MATCH, f"{attack.name}: {attack.why} -> must not MATCH (got {v})"


@pytest.mark.parametrize("attack", CONTROLS, ids=lambda a: a.name)
def test_controls_are_conserved(attack):
    v = transitive_verdicts(attack.nodes)[attack.target]
    assert v == MATCH, f"{attack.name}: {attack.why} -> must MATCH (got {v})"


def test_corpus_catches_the_outcome_only_strawman():
    # the anti-theatre proof: a local-only closure MUST be caught.
    r = run_corpus(naive_closure)
    assert r["false_accepts"] > 0, "corpus fails to catch an outcome-only verifier -> theatrical"
    # it should be caught by the grounding-dependent attacks specifically
    assert "drifted_ancestor" in r["false_accept_names"]
    assert "no_receipt" in r["false_accept_names"]


def test_corpus_discriminates_by_depth():
    # a 1-hop-grounding closure catches the 1-hop drift but NOT the deep drift or
    # the cycle — proving the corpus tests depth, not just presence of a check.
    r = run_corpus(depth_limited_closure)
    assert "deep_drift_depth_evasion" in r["false_accept_names"], \
        "deep-drift attack must catch a depth-limited closure"
    assert "cycle_laundering" in r["false_accept_names"]
    # and the depth-limited closure correctly handles the 1-hop case (not a false
    # accept there), so the corpus isn't just rejecting every strawman blindly:
    assert "drifted_ancestor" not in r["false_accept_names"]


def test_gate_report_renders():
    assert "gate:" in gate_report(run_corpus(transitive_verdicts))
