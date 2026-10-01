"""Open-weight tier: edits, intervention arms, O2 analysis with the critic's controls."""
import json
from pathlib import Path

import pytest

from harness.trace_observation import intervals as iv
from harness.trace_observation.openweight import analysis, capture_local, edits, interventions

FIX = Path(__file__).parent / "fixtures" / "trace_observation"


def test_sentence_snap_never_cuts_mid_sentence():
    text = "First step. Second step is long and keeps going\nThird."
    cut = edits.truncate_fraction(text, 0.5)
    assert cut == "First step."
    assert edits.truncate_fraction(text, 0) == "" and edits.truncate_fraction(text, 1) == text


def test_error_edit_changes_one_literal_and_has_neutral_control():
    text = "We have 3 apples.\nAdd 4 more to get 7.\nSo 7 total."
    e = edits.error_edit(text, 20)
    assert e["error"].endswith("Add 4 more to get 8.\n")
    assert e["neutral"].endswith("Add 4 more to get  7.\n")
    assert e["prefix"].endswith("Add 4 more to get 7.\n")
    assert edits.error_edit("no digits here", 1)["prefix"] is None
    assert edits.error_edit("the value is 80.", 0)["error_literal"] == "81"


def test_codemask_removes_drafted_code_and_leak_share_measures_it():
    trace = "Plan it.\n```python\ndef f(x):\n    return x + 1\n```\nreturn x + 1\nDone."
    masked = edits.mask_code(trace)
    assert "return" not in masked and masked.count(edits.MASK) >= 1
    assert edits.leak_share(trace, "def f(x):\n    return x + 1") == 1.0
    assert edits.leak_share(masked, "def f(x):\n    return x + 1") == 0.0


class Backend:
    """Readout depends on the span on dependent items; a planted error flips it on half."""

    def __init__(self, dependent_every=2, error_moves=True):
        self.dep, self.err = dependent_every, error_moves

    def span(self, head, seed, budget, logprobs=False):
        i = int(head.split(":")[1].split("\n")[0])
        return {"text": f"Item {i}.\nCompute 2 plus 3 to get 5.\nCheck it again.\nAnswer A.\n",
                "tokens": None, "closed": True, "budget_hit": False, "record": None}

    def readout(self, head, span):
        i = int(head.split(":")[1].split("\n")[0])
        if not span.strip():
            letter = "B" if i % self.dep == 0 else "A"
        elif self.err and "get 6" in span and i % self.dep == 0:
            letter = "C"
        else:
            letter = "A"
        return {"status": "ok", "argmax": letter, "probs": {letter: 1.0}}


def run(backend, n=60):
    return [dict(interventions.mc_item(backend, f"q:{i}\n", 100000 + 10 * i), id=str(i)) for i in range(n)]


def test_o2_detects_planted_dependence_and_error_sensitivity_on_dependent_items():
    out = analysis.analyze_o2(run(Backend()), gold={str(i): "A" for i in range(60)})
    assert out["n_dependent"] == "30"
    assert out["tests"]["P1"]["excludes_zero"] == "true"
    assert out["tests"]["P3"]["excludes_zero"] == "true"
    assert out["tests"]["P3"]["n"] == "30"       # scored on dependent items only
    assert out["tests"]["P1"]["holm"]["reject"] == "true"
    assert out["direction"]["correct_to_wrong"] == "30"
    assert out["readout_determinism"]["rate"] == "1.0000"
    assert "null_bound" in out["tests"]["P2"]


def test_o2_null_backend_does_not_fire_and_states_its_bound():
    out = analysis.analyze_o2(run(Backend(error_moves=False)))
    assert out["tests"]["P3"]["excludes_zero"] == "false"
    assert "upper bound" in out["tests"]["P3"]["null_bound"]


def test_code_arm_p4_masked_trace_against_empty():
    class CB(Backend):
        def answer(self, head, span, seed, budget=2048):
            return "ok" if span.strip() else "fail"
    items = [interventions.code_item(CB(), f"q:{i}\n", 200000 + 10 * i, lambda a: a == "ok")
             for i in range(12)]
    p4 = analysis.analyze_o2([], items)["tests"]["P4"]
    assert p4["n"] == "12" and p4["excludes_zero"] == "true"


def test_alpha_normalization_and_controllability_planted_positives():
    assert analysis.alpha_normalized(0.4, 0.1, 4) == pytest.approx(0.875)
    good = analysis.controllability([{"reasoning": "fine", "answer": "x"}], "banana",
                                    planted=["a banana here"])
    assert good["status"] == "ok" and good["reasoning_compliance"]["rate"] == "1.0000"
    blind = analysis.controllability([{"reasoning": "banana", "answer": ""}], "banana",
                                     planted=["a banana here"], scanner=lambda t: False)
    assert blind["status"] == "CONTROL_FAILED"


def test_intervals_wilson_holm_sign():
    lo, hi = iv.wilson(7, 39)
    assert iv.fmt4(lo) == "0.0898" and iv.fmt4(hi) == "0.3267"      # round-1 TRUNC_0 cell (0.090 to 0.327)
    assert iv.rate_block(3, 5, minimum=30)["status"] == iv.INSUFFICIENT_SAMPLE
    h = iv.holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert h["a"]["reject"] == "true" and h["b"]["reject"] == "false"
    assert iv.sign_test([1] * 10) < 0.01 and iv.sign_test([0, 0]) == 1.0
    assert iv.verdict_or_refusal({"lower": "0.05", "upper": "0.2"}, 0.1, above="G", below="N") == iv.STRADDLES


def test_local_backend_refuses_seed_zero_and_replays_recorded_responses():
    f = json.loads((FIX / "ollama_qwen3_recorded.json").read_text(encoding="utf-8"))
    head = capture_local.qwen_head("task")
    key = capture_local.RecordedTransport.key({"prompt": head, "options": {"seed": 5}})
    rt = capture_local.RecordedTransport({key: {"thinking": f["response"]["thinking"], "response": "",
                                                "done_reason": "stop"}})
    be = capture_local.OllamaBackend("qwen3:8b", post=rt)
    sp = be.span(head, 5, 12288)
    assert sp["closed"] and sp["record"].channel == "raw"
    with pytest.raises(ValueError):
        be.span(head, 0, 10)
    with pytest.raises(KeyError):
        be.span(head, 6, 10)


def test_letter_probs_renormalizes_and_reports_missing_letters():
    out = capture_local.letter_probs([{"token": " A", "logprob": -0.1}, {"token": "B", "logprob": -2.0},
                                      {"token": "x", "logprob": -0.5}])
    assert out["argmax"] == "A" and abs(sum(out["probs"].values()) - 1) < 1e-9
    assert capture_local.letter_probs([{"token": "z", "logprob": 0}])["status"] == "no_letter"
