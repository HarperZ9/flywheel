"""Falsifier for the verified selection component (harness/selector.py).

The component must: prefer the external oracle when present (highest trust), fall
back to deterministic behavioral consensus with an honest confidence gate, apply
the voice-cap gate on correlated oracle failure, and emit a re-checkable receipt.
No learned model may decide.
"""
import sys
from types import SimpleNamespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import glob
import os
import tempfile
import time

import pytest

from harness.selector import (
    select, consensus_select, oracle_select, infer_param_types,
    SelectionReceipt, max_correlation, verify_selection,
    _signature, battery, _productive, fn_name, fn_arity,
)
from harness.workspace_lens import NullLens, AlwaysCautionLens, NO_CAUTION

GOOD = "def f(a):\n    return a + 1\n"
GOOD2 = "def f(a):\n    return 1 + a\n"      # same behavior, same token set (corr 1.0)
# textually DIVERSE but behaviorally identical -- genuine independent agreement,
# the only thing that should earn a confident consensus PASS.
GOOD_B = "def f(a):\n    total = a\n    total = total + 1\n    return total\n"
GOOD_C = "def f(a):\n    return sum((a, 1))\n"
WRONG = "def f(a):\n    return a - 1\n"
WRONG2 = "def f(a):\n    return a * 2\n"
SIG = "def f(a):\n    return a + 1\n"


class FakeOracle:
    """Passes iff the candidate contains a marker. Ignores the task."""
    def __init__(self, marker="+ 1"):
        self.marker = marker

    def verify(self, candidate, task):
        return SimpleNamespace(passed=self.marker in candidate)


DUMMY_TASK = SimpleNamespace(prompt="", max_new_tokens=64, system="")


def test_oracle_path_accepts_passing_candidate():
    res = select([WRONG, GOOD, WRONG2], task=DUMMY_TASK, oracle=FakeOracle())
    assert res.receipt.method == "oracle"
    assert res.receipt.verdict == "PASS"
    assert res.receipt.selected_index == 1
    assert res.text == GOOD
    assert res.receipt.oracle_pass_vector == [False, True, False]


def test_oracle_path_no_pass_diverse_is_pass_none():
    res = select([WRONG, WRONG2], task=DUMMY_TASK, oracle=FakeOracle())
    assert res.receipt.method == "oracle"
    assert res.receipt.verdict == "PASS_NONE"
    assert res.text is None


def test_oracle_path_no_pass_correlated_is_unverifiable():
    # wrong-attractor convergence: samples collapse to the SAME wrong answer.
    # High correlation + no pass -> voice-cap gate refuses a confident FAIL.
    w = "def f(a):\n    return a - 1\n"
    res = select([w, w, w], task=DUMMY_TASK, oracle=FakeOracle())
    assert res.receipt.verdict == "UNVERIFIABLE"
    assert res.receipt.correlation >= 0.85


def test_consensus_high_confidence_passes():
    # three textually-diverse but behaviorally-identical correct candidates +
    # one wrong -> independent agreement -> CONSENSUS_PASS (agreement, not
    # oracle-verified -- a distinct token from the oracle path's PASS)
    res = select([WRONG, GOOD, GOOD_B, GOOD_C], solution_sig=SIG)
    assert res.receipt.method == "consensus"
    assert res.receipt.verdict == "CONSENSUS_PASS"
    assert res.receipt.verdict != "PASS"        # never conflated with oracle-verified
    assert res.receipt.confidence >= 0.5
    assert res.receipt.correlation < 0.85
    assert res.receipt.selected_index in (1, 2, 3)


def test_wrong_agreeing_majority_is_gated():
    # THE confound: 4 byte-identical candidates sharing a bug agree perfectly
    # (confidence 1.0) but are near-identical (corr 1.0) -> NOT a confident PASS.
    buggy = "def f(a):\n    return a - 1\n"
    res = select([buggy, buggy, buggy, buggy], solution_sig=SIG)
    assert res.receipt.verdict == "LOW_CONFIDENCE"
    assert res.receipt.correlation >= 0.85
    assert res.text is not None      # still returns a best-effort candidate...
    # ...but the verdict tells the caller not to trust it as an accept


def test_consensus_tie_is_gated():
    # a 2-2 split into two EQUAL productive clusters (each pair agrees internally,
    # textually diverse) -> the tie-break would otherwise decide by array
    # position -> ambiguous -> LOW_CONFIDENCE
    wrong_a = "def f(a):\n    return a - 1\n"
    wrong_b = "def f(a):\n    return a + (-1)\n"   # same behavior as wrong_a, different text
    res = select([GOOD, GOOD_B, wrong_a, wrong_b], solution_sig=SIG)
    assert res.receipt.verdict == "LOW_CONFIDENCE"
    assert res.receipt.runner_up_confidence >= res.receipt.confidence


def test_consensus_low_confidence_flags():
    # four distinct behaviors -> best cluster is a singleton -> low confidence
    c = ["def f(a):\n    return a + 1\n",
         "def f(a):\n    return a - 1\n",
         "def f(a):\n    return a * 2\n",
         "def f(a):\n    return a * a\n"]
    res = select(c, solution_sig=SIG)
    assert res.receipt.method == "consensus"
    assert res.receipt.verdict == "LOW_CONFIDENCE"
    assert res.receipt.confidence < 0.5


def test_empty_candidates_unverifiable():
    res = select([], solution_sig=SIG)
    assert res.receipt.verdict == "UNVERIFIABLE"
    assert res.text is None


def test_receipt_has_candidate_hashes():
    res = select([WRONG, GOOD, GOOD2], task=DUMMY_TASK, oracle=FakeOracle())
    assert len(res.receipt.candidate_hashes) == 3
    d = res.receipt.to_dict()
    assert d["schema"] == "flywheel.selection-receipt/v1"
    assert d["method"] == "oracle"


def test_receipt_battery_hash_on_consensus():
    res = select([WRONG, GOOD, GOOD2, GOOD2], solution_sig=SIG)
    assert res.receipt.battery_hash is not None
    assert res.receipt.oracle_pass_vector is None


def test_oracle_beats_consensus_when_both_available():
    # even with a strong wrong-consensus majority, the oracle decides
    res = select([WRONG, WRONG, WRONG, GOOD], solution_sig=SIG,
                 task=DUMMY_TASK, oracle=FakeOracle())
    assert res.receipt.method == "oracle"
    assert res.text == GOOD


def test_no_learned_model_in_path(tmp_path):
    # the selector must reach a decision with only an oracle or deterministic
    # clustering -- re-running consensus on the same pool is deterministic
    a = consensus_select([WRONG, GOOD, GOOD2, GOOD2], "f", 1, tmp_path / "a")
    b = consensus_select([WRONG, GOOD, GOOD2, GOOD2], "f", 1, tmp_path / "b")
    assert a == b  # deterministic selection, no learned/random component


def test_max_correlation_bounds():
    assert max_correlation([GOOD]) == 0.0
    assert 0.0 <= max_correlation([GOOD, WRONG]) <= 1.0
    assert max_correlation([GOOD, GOOD]) == 1.0


def test_consensus_receipt_carries_recheck_params():
    res = select([WRONG, GOOD, GOOD_B, GOOD_C], solution_sig=SIG)
    r = res.receipt
    assert r.fn == "f"
    assert r.arity == 1
    assert r.param_types is not None
    assert r.battery_hash is not None
    d = r.to_dict()
    assert set(["fn", "arity", "param_types", "task_id", "runner_up_confidence"]) <= set(d)


def test_verify_selection_match():
    cands = [WRONG, GOOD, GOOD_B, GOOD_C]
    res = select(cands, solution_sig=SIG)
    assert verify_selection(res.receipt, cands, solution_sig=SIG) == "MATCH"


def test_verify_selection_unverifiable_on_tampered_candidates():
    cands = [WRONG, GOOD, GOOD_B, GOOD_C]
    res = select(cands, solution_sig=SIG)
    tampered = [WRONG2, GOOD, GOOD_B, GOOD_C]   # candidate 0 swapped
    assert verify_selection(res.receipt, tampered, solution_sig=SIG) == "UNVERIFIABLE"


def test_verify_selection_drift_on_wrong_index():
    cands = [WRONG, GOOD, GOOD_B, GOOD_C]
    res = select(cands, solution_sig=SIG)
    res.receipt.selected_index = (res.receipt.selected_index + 1) % 4   # tamper
    assert verify_selection(res.receipt, cands, solution_sig=SIG) == "DRIFT"


# --- hardening: every input/output/seam traced -------------------------------

class RaisingOracle:
    def verify(self, candidate, task):
        raise RuntimeError("oracle exploded")


def test_oracle_with_no_task_raises_loud():
    with pytest.raises(ValueError):
        select([GOOD, WRONG], oracle=FakeOracle())   # oracle but task=None


def test_task_without_oracle_is_fine_consensus():
    res = select([GOOD, GOOD_B, GOOD_C, WRONG], task=DUMMY_TASK, solution_sig=SIG)
    assert res.receipt.method == "consensus"        # task-only -> consensus, no raise


def test_raising_oracle_never_crashes_selection():
    res = select([GOOD, WRONG], task=DUMMY_TASK, oracle=RaisingOracle())
    assert res.receipt.method == "oracle"
    assert res.receipt.selected_index == -1          # nothing "passed", no crash


def test_non_string_candidates_coerced_not_crash():
    res = select([None, 123, GOOD, GOOD_B], solution_sig=SIG)
    assert res.receipt.candidates_used == 4
    assert len(res.receipt.candidate_hashes) == 4    # None/int coerced, no crash


def test_single_candidate_is_not_consensus():
    res = select([GOOD], solution_sig=SIG)            # one candidate = single-shot
    assert res.receipt.verdict == "LOW_CONFIDENCE"


def test_no_scratch_dir_leak():
    tmp = tempfile.gettempdir()
    before = len(glob.glob(os.path.join(tmp, "sel_cons_*")))
    for _ in range(3):
        select([GOOD, GOOD_B, GOOD_C, WRONG], solution_sig=SIG)
    after = len(glob.glob(os.path.join(tmp, "sel_cons_*")))
    assert after <= before                            # scratch dirs cleaned each call


def test_hostile_candidate_signature_is_bounded(tmp_path):
    hostile = "def f(a):\n    while True:\n        pass\n"
    t0 = time.monotonic()
    sig = _signature(hostile, "f", battery(1)[:3], tmp_path / "h", 0,
                     slot_timeout=1, backstop=6)
    elapsed = time.monotonic() - t0
    assert elapsed < 15                               # per-slot + backstop bound it
    assert not _productive(sig)                       # a hang never "agrees"


def test_empty_string_candidates_unrunnable_not_crash():
    res = select(["", "", GOOD, GOOD_B], solution_sig=SIG)
    assert res.receipt.candidates_used == 4           # empty strings -> UNRUNNABLE


# --- closure-review seams: solution_sig, verifier consistency, bounds, entry pt

def test_solution_sig_none_does_not_crash():
    res = select([GOOD, GOOD_B, GOOD_C, WRONG], solution_sig=None)  # None -> degrade, not crash
    assert res.receipt.method == "consensus"


def test_solution_sig_nullbyte_does_not_crash():
    res = select([GOOD, WRONG], solution_sig="def f(a):\x00 return a\n")
    assert res.receipt.method == "consensus"


def test_verify_selection_requires_matching_verifier():
    # an oracle-method receipt cannot be re-checked without an oracle
    cands = [WRONG, GOOD]
    ores = select(cands, task=DUMMY_TASK, oracle=FakeOracle())
    assert verify_selection(ores.receipt, cands, solution_sig=SIG) == "UNVERIFIABLE"
    # a consensus-method receipt must not be re-checked via an oracle
    cres = select([GOOD, GOOD_B, GOOD_C, WRONG], solution_sig=SIG)
    assert verify_selection(cres.receipt, [GOOD, GOOD_B, GOOD_C, WRONG],
                            solution_sig=SIG, task=DUMMY_TASK, oracle=FakeOracle()) == "UNVERIFIABLE"


def test_confidence_threshold_out_of_bounds_raises():
    for bad in (0.0, -0.1, 1.5):
        with pytest.raises(ValueError):
            select([GOOD, GOOD_B], solution_sig=SIG, confidence_threshold=bad)


def test_entry_point_resolves_past_helper_def():
    # a helper is defined first; entry_point must pick the real entry function
    sol = "def _helper(x, y, z):\n    return 0\n\ndef solve(a):\n    return a + 1\n"
    assert fn_name(sol) == "_helper"                 # default: first def
    assert fn_name(sol, "solve") == "solve"          # explicit entry point
    assert fn_arity(sol, "solve") == 1


# --- workspace advisory: DEMOTE-ONLY, C2-safe --------------------------------

def test_workspace_lens_demotes_consensus_pass():
    # a consensus that would PASS is demoted to LOW_CONFIDENCE by a cautioning lens
    base = select([WRONG, GOOD, GOOD_B, GOOD_C], solution_sig=SIG)
    assert base.receipt.verdict == "CONSENSUS_PASS"
    demoted = select([WRONG, GOOD, GOOD_B, GOOD_C], solution_sig=SIG,
                     workspace_lens=AlwaysCautionLens(reason="looks wrong"))
    assert demoted.receipt.verdict == "LOW_CONFIDENCE"
    assert demoted.receipt.workspace_caution is not None


def test_null_lens_is_byte_identical_noop():
    a = select([WRONG, GOOD, GOOD_B, GOOD_C], solution_sig=SIG)
    b = select([WRONG, GOOD, GOOD_B, GOOD_C], solution_sig=SIG, workspace_lens=NullLens())
    assert a.receipt.verdict == b.receipt.verdict == "CONSENSUS_PASS"
    assert b.receipt.workspace_caution is None


def test_workspace_lens_never_touches_oracle_pass():
    # a cautioning lens must NOT demote an oracle-VERIFIED PASS (oracle is authority)
    res = select([WRONG, GOOD], task=DUMMY_TASK, oracle=FakeOracle(),
                 workspace_lens=AlwaysCautionLens())
    assert res.receipt.method == "oracle"
    assert res.receipt.verdict == "PASS"             # untouched by the advisory
    assert res.receipt.workspace_caution is None


def test_workspace_lens_never_promotes():
    # a low-confidence consensus stays low even with a (demote=False) lens
    lowconf = ["def f(a):\n    return a + 1\n", "def f(a):\n    return a - 1\n",
               "def f(a):\n    return a * 2\n", "def f(a):\n    return a * a\n"]
    res = select(lowconf, solution_sig=SIG, workspace_lens=NullLens())
    assert res.receipt.verdict == "LOW_CONFIDENCE"   # never promoted to an accept


def test_broken_lens_never_breaks_selection():
    class BoomLens:
        def caution(self, candidate, *, solution_sig="", task=None):
            raise RuntimeError("lens exploded")
    res = select([WRONG, GOOD, GOOD_B, GOOD_C], solution_sig=SIG, workspace_lens=BoomLens())
    assert res.receipt.verdict == "CONSENSUS_PASS"   # a throwing lens is ignored, no crash
