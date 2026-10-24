"""Harness-edit receipts: seal, digests, diff, and decision re-derivation."""
import pytest

from harness import self_improve_bench as bench
from harness.evidence_json import canonical_sha256
from harness.self_improve_adapters import CallableExecutor, ContrastSelector
from harness.self_improve_bench_agents import ScriptedEditor
from harness.self_improve_gate import HeldOutGate
from harness.self_improve_loop import run_task
from harness.self_improve_receipt import build_edit_receipt, verify_edit_receipt
from harness.self_improve_stream import _ungated


@pytest.fixture
def made():
    ex = CallableExecutor(bench.execute)
    gate = HeldOutGate(bench.make_split("gate", 12, 101), bench.grade, ex)
    run = run_task(bench.make_split("stream", 1, 101)[0], mode="parallel", k=2,
                   incumbent=bench.base_tree(), executor=ex, editor=ScriptedEditor(seed=101),
                   selector=ContrastSelector(bench.contrast_score))
    parent, candidate = bench.base_tree(), bench.make_tree(bench.GOOD)
    result = gate.review(parent, candidate)
    receipt = build_edit_receipt(parent=parent, candidate=candidate, run=run, gate=result)
    return parent, result, receipt


def _reseal(receipt):
    body = {k: v for k, v in receipt.items() if k != "seal_sha256"}
    return {**body, "seal_sha256": canonical_sha256(body)}


def test_receipt_carries_diff_contrast_and_interval(made):
    parent, result, receipt = made
    assert receipt["decision"] == "ADOPT"
    assert receipt["diff"].startswith("--- a/scripts/summarize.py")
    assert receipt["contrast"]["chosen"] in receipt["contrast"]["finals"]
    assert receipt["heldout"]["interval"][0] >= 0 and receipt["scope"]
    check = verify_edit_receipt(receipt, parent=parent, adopted=result["tree"])
    assert check["verdict"] == "MATCH"


def test_any_edit_breaks_the_seal(made):
    _, _, receipt = made
    assert verify_edit_receipt({**receipt, "reason": "x"})["verdict"] == "TAMPERED"


def test_wrong_trees_are_caught(made):
    parent, result, receipt = made
    assert verify_edit_receipt(receipt, parent=bench.make_tree({"dedupe"}))["verdict"] \
        == "TAMPERED"
    assert verify_edit_receipt(receipt, adopted=parent)["verdict"] == "TAMPERED"


def test_resealed_but_unsupported_decision_is_inconsistent(made):
    _, _, receipt = made
    bad = _reseal({**receipt, "heldout": {**receipt["heldout"], "point": -0.5}})
    assert verify_edit_receipt(bad)["verdict"] == "INCONSISTENT"
    dropped = _reseal({**receipt, "attribution": [{**a, "kept": False}
                                                  for a in receipt["attribution"]]})
    assert verify_edit_receipt(dropped)["verdict"] == "INCONSISTENT"


def test_ungated_receipt_is_inconsistent(made):
    parent, _, receipt = made
    gate = _ungated(parent, bench.make_tree({"check_pass", "abs"}))
    run = type("R", (), {"task_id": "t", "mode": "parallel", "k": 1, "finals": ["agg1"],
                         "chosen": "agg1", "why": "", "scores": {}, "stages": [],
                         "budget": {}})()
    r = build_edit_receipt(parent=parent, candidate=gate["tree"], run=run, gate=gate)
    assert verify_edit_receipt(r)["verdict"] == "INCONSISTENT"


def test_unknown_schema(made):
    _, _, receipt = made
    assert verify_edit_receipt({**receipt, "schema": "x"})["verdict"] == "TAMPERED"
