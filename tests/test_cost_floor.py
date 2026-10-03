"""Cost receipts against the hardware floor.

Success criteria:
- known answer: a 14.77B model with an 8.988 GB weight file on an RTX 4090
  (1008 GB/s, 330.3 dense FP16 TFLOPS) has a decode floor of 8.917 ms per token,
  memory-bound, and a 300-token prefill floor of 26.83 ms, compute-bound;
- batching moves decode from memory-bound to compute-bound once the batch's
  arithmetic outweighs one read of the weights (between 64 and 128 sequences);
- paired mutation: a floor that drops the memory limit gives a decode floor
  under 0.1 ms, and the known-answer check rejects it;
- every receipt carries measured time, floor, ratio, phase bounds, the hardware
  source and a does_not_prove line; bad inputs raise;
- search: with `hardware` set, the search stage carries one receipt per timed
  candidate and a summary; candidates without provider token counts are counted
  as untimed; without `hardware` the payload has no cost section.
"""
from __future__ import annotations

import pytest

from harness import cost_floor
from harness.cost_floor import HARDWARE, ModelProfile, floor_seconds, receipt, summarize

M14 = ModelProfile(params=14_770_033_664, weight_bytes=8_988_111_146)
GPU = HARDWARE["rtx-4090"]


def _known_answer() -> None:
    f = floor_seconds(300, 100, M14, GPU)
    assert f["decode_bound"] == "memory" and f["prefill_bound"] == "compute"
    assert f["decode_s"] / 100 == pytest.approx(8.988111146 / 1008, rel=1e-6)
    assert f["prefill_s"] == pytest.approx(2 * 14.770033664e9 * 300 / 330.3e12, rel=1e-6)


def test_known_answer_14b_on_4090():
    _known_answer()
    assert floor_seconds(0, 1, M14, GPU)["decode_s"] == pytest.approx(0.008917, abs=1e-6)


def test_batching_flips_decode_to_compute_bound():
    assert floor_seconds(0, 10, M14, GPU, batch=64)["decode_bound"] == "memory"
    assert floor_seconds(0, 10, M14, GPU, batch=128)["decode_bound"] == "compute"


def test_paired_mutation_floor_without_memory_limit_is_caught(monkeypatch):
    def compute_only(flops, bytes_read, hw):
        return flops / (hw.peak_tflops * 1e12), "compute"
    monkeypatch.setattr(cost_floor, "_phase_floor", compute_only)
    assert floor_seconds(0, 1, M14, GPU)["decode_s"] < 1e-4
    with pytest.raises(AssertionError):
        _known_answer()


def test_receipt_fields_and_ratio():
    r = receipt(2.0, 300, 100, M14, "rtx-4090")
    assert r["schema"] == "flywheel.cost-floor/v1"
    assert r["ratio"] == pytest.approx(2.0 / r["floor_s"], rel=1e-3)
    assert r["hardware"]["source"].startswith("NVIDIA Ada GPU Architecture whitepaper")
    assert r["phases"]["decode_bound"] == "memory" and "does not show" in r["does_not_prove"]


def test_bad_inputs_raise():
    with pytest.raises(ValueError):
        floor_seconds(-1, 1, M14, GPU)
    with pytest.raises(ValueError):
        floor_seconds(1, 1, M14, GPU, batch=0)
    with pytest.raises(KeyError):
        receipt(1.0, 1, 1, M14, "abacus")


def test_summary_counts_calls_below_floor():
    rs = [receipt(t, 10, 10, M14, GPU) for t in (1.0, 2.0, 0.0001)]
    s = summarize(rs)
    assert s["calls"] == 3 and s["below_floor"] == 1 and s["ratio_median"] > 1


class Timed:
    model_ref = "stub"

    def __init__(self, usage):
        self.usage = usage

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        from harness.proposer import ProposerOutput, prompt_hash
        return ProposerOutput(text="x", model_ref="stub", seed=seed,
                              prompt_hash=prompt_hash(prompt), cache="stub", usage=self.usage)


class Pass:
    oracle_type = "fn"

    def verify(self, candidate, task):
        from harness.oracle import OracleResult
        return OracleResult(passed=True, cmd="fn", output_hash="h", stdout_excerpt="", rc=0)


def _payload(cfg, usage):
    from harness.chain import chain_to_dicts
    from harness.search_stage import run_search_stage
    from harness.task import Task
    task = Task(task_id="t", prompt="p", oracle="fn", oracle_cmd="fn", workdir=".",
                candidate_path="s.py")
    chain = []
    run_search_stage(task, "p", Timed(usage), Pass(), cfg, chain)
    return next(s for s in chain_to_dicts(chain) if s["stage"] == "search")["payload"]


def test_search_stage_carries_cost_receipts():
    from harness.eval import ArmConfig
    cfg = ArmConfig(name="v", n_candidates=4, hardware="rtx-4090",
                    model_profile={"params": M14.params, "weight_bytes": M14.weight_bytes})
    p = _payload(cfg, {"prompt": 50, "completion": 20, "total": 70})
    assert len(p["cost_floor"]["receipts"]) == 4 and p["cost_floor"]["untimed_candidates"] == 0
    assert p["cost_floor"]["summary"]["calls"] == 4


def test_search_stage_counts_untimed_and_stays_off_by_default():
    from harness.eval import ArmConfig
    cfg = ArmConfig(name="v", n_candidates=4, hardware="rtx-4090",
                    model_profile={"params": 1, "weight_bytes": 1})
    assert _payload(cfg, None)["cost_floor"]["untimed_candidates"] == 4
    assert "cost_floor" not in _payload(ArmConfig(name="v", n_candidates=4), None)
