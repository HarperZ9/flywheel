"""The Lean proof on the lane's path, beside the check it repeats.

The report and the proof are two readings of one answer, built from different
code. What this file pins is which way each disagreement falls: a kernel that
refused an obligation the check passed holds the answer, and a kernel that was
never installed does not.
"""
import json
import shutil

import pytest

from harness.contract_stage import holds, stage_payload, validate_output
from harness.contract_terms import CRITICAL, RELEASE
from harness.output_contract import RECOMPUTE, new_contract
from harness.verdict import Verdict

CONTRACT = new_contract([{"name": "tax", "authority": RECOMPUTE,
                          "source": "table:2026", "criticality": CRITICAL}])
AUTHORITIES = {"table:2026": lambda _a: 4169.0}


GOOD = json.dumps({"tax": {"value": 4169.0, "source": "table:2026"}})


def test_a_lane_writes_the_proof_without_running_anything(tmp_path):
    """Running Lean is running a program. A lane asks for that the same way it
    asks for a command authority, so writing the file does not run it."""
    lean = tmp_path / "Answer.lean"
    report = validate_output(GOOD, CONTRACT, AUTHORITIES, write=False,
                             proof=lean)
    assert "#print axioms confirmed" in lean.read_text(encoding="utf-8")
    assert report["proof"]["verdict"] == Verdict.UNVERIFIABLE.value
    assert not holds(report)


def test_a_kernel_that_refused_holds_an_answer_the_check_passed():
    """The two readings disagreeing is the finding the second one exists to
    produce, and a lane does not accept while it is open."""
    report = {"release": RELEASE,
              "proof": {"verdict": Verdict.FAIL.value, "axioms": ["sorryAx"]}}
    assert holds(report)


def test_a_proof_nobody_could_run_does_not_hold_the_answer():
    """Lean not being installed is a fact about the machine. It cannot make a
    checked answer into a held one."""
    report = {"release": RELEASE,
              "proof": {"verdict": Verdict.UNVERIFIABLE.value, "axioms": []}}
    assert not holds(report)


def test_a_relation_the_emitter_will_not_read_is_unverified_not_a_hold(tmp_path):
    """That is an authoring error in the contract. Holding the answer over it
    would report a defect in the document as a defect in the work."""
    report = validate_output(GOOD, CONTRACT, AUTHORITIES, write=False,
                             proof=tmp_path / "A.lean",
                             relations=["tax * tax > 0"])
    assert report["proof"]["verdict"] == Verdict.UNVERIFIABLE.value
    assert not holds(report)


def test_the_chain_payload_carries_the_axiom_list_and_not_the_prose():
    report = dict(validate_output(GOOD, CONTRACT, AUTHORITIES, write=False),
                  proof={"verdict": Verdict.PASS.value, "checker": "lean 4.33.1",
                         "axioms": ["Decided", "tax_decided"],
                         "reason": "every obligation closed"})
    payload = stage_payload(report)
    assert payload["proof"]["axioms"] == ["Decided", "tax_decided"]
    assert "every obligation closed" not in json.dumps(payload)


@pytest.mark.skipif(shutil.which("lean") is None, reason="lean is not installed")
def test_a_lane_that_asked_for_the_kernel_gets_the_kernel(tmp_path):
    report = validate_output(GOOD, CONTRACT, AUTHORITIES, write=False,
                             proof=tmp_path / "Answer.lean", verify_proof=True,
                             relations=["0 <= tax"])
    assert report["proof"]["verdict"] == Verdict.PASS.value, report["proof"]["reason"]
    assert "tax_decided" in report["proof"]["axioms"]
    assert not holds(report)
