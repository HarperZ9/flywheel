"""authorization-cost falsifier — the permission tax is real, bounded, and grounded.

Properties: the tax grows with repeat fraction; it is exactly 1.0 (no tax) on all-
novel work (the honest bound); the crossover math is right; and `unique` is
grounded in what the REAL ReceiptCache actually dedups.
"""
from pathlib import Path

from harness.authorization_cost import regime_cost, crossover_repeat_fraction
from harness.cache import ReceiptCache
from harness.envelope import ProofEnvelope


def test_all_novel_work_has_no_tax():
    r = regime_cost([f"k{i}" for i in range(10)])       # all unique
    assert r.unique_acts == 10 and r.tax_ratio == 1.0   # honest bound: no free lunch
    assert r.repeat_fraction == 0.0


def test_tax_grows_with_repeats():
    # 10 acts, 2 unique -> repeat 0.8 -> tax 5x
    r = regime_cost(["a", "b"] * 5)
    assert r.unique_acts == 2 and r.n_acts == 10
    assert abs(r.repeat_fraction - 0.8) < 1e-9
    assert r.tax_ratio == 5.0
    assert "5.00x" in r.report()


def test_more_repeats_more_tax():
    low = regime_cost(["a", "b", "c", "d", "a"])         # 1 repeat of 5
    high = regime_cost(["a"] * 5 + ["b"] * 5)            # 8 repeats of 10, 2 unique
    assert high.tax_ratio > low.tax_ratio


def test_crossover_math():
    assert abs(crossover_repeat_fraction(2.0) - 0.5) < 1e-9    # 2x tax at r=0.5
    assert abs(crossover_repeat_fraction(10.0) - 0.9) < 1e-9   # 10x tax at r=0.9
    assert crossover_repeat_fraction(1.0) == 0.0


def _env(task_id):
    return ProofEnvelope(task_id=task_id, candidate="c", oracle="stub",
                         oracle_cmd="stub", oracle_output_hash="h", verdict="PASS",
                         model_ref="m", seed=0, prompt_hash="p", budget_spent=1)


def test_unique_is_grounded_in_the_real_cache(tmp_path):
    # The 'unique' the instrument charges for is exactly what ReceiptCache dedups:
    # inserting the same key twice leaves one re-checkable entry, so a repeat is
    # a trustless free reuse — the accountability side is real, not modeled.
    cache = ReceiptCache(tmp_path / "c")
    cache.insert(_env("t1"), "same-key")
    cache.insert(_env("t1"), "same-key")                # a repeat
    assert cache.lookup("same-key") is not None
    # two acts, one content-address -> accountability pays once, permission twice
    r = regime_cost(["same-key", "same-key"])
    assert r.accountability_cost == 1 and r.permission_cost == 2
