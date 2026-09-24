"""Split-conformal LAC sets: finite-sample rank, set membership, coverage.

The coverage test carries two controls that must fail the same check: a
quantile fitted at the wrong level, and test draws from a shifted
distribution. Without them a coverage assertion could pass on a broken
quantile or on sets that admit every label.
"""
import math
import random

import pytest

from harness import conformal

ALPHA = 0.1
N_DRAWS = 2000


def _draw(rng: random.Random, signal: float = 1.5, classes: int = 4) -> dict:
    target = rng.randrange(classes)
    logits = [rng.gauss(0.0, 1.0) + (signal if i == target else 0.0) for i in range(classes)]
    peak = max(logits)
    weights = [math.exp(z - peak) for z in logits]
    total = sum(weights)
    return {"probabilities": {f"c{i}": w / total for i, w in enumerate(weights)},
            "target": f"c{target}"}


def _draws(seed: int, n: int = N_DRAWS, signal: float = 1.5) -> list:
    rng = random.Random(seed)
    return [_draw(rng, signal) for _ in range(n)]


def test_quantile_is_the_finite_sample_rank():
    scores = [round(0.05 * i, 2) for i in range(19, 0, -1)]  # 19 scores, unsorted
    # ceil(20 * 0.9) = 18, so the 18th smallest score, 0.9.
    assert conformal.lac_quantile(scores, 0.1) == 0.9
    # ceil(20 * 0.5) = 10, so the 10th smallest, 0.5.
    assert conformal.lac_quantile(scores, 0.5) == 0.5
    # ceil(5 * 0.9) = 5 > 4: the quantile is infinite and every label is admitted.
    assert conformal.lac_quantile([0.1, 0.2, 0.3, 0.4], 0.1) == 1.0


def test_prediction_set_membership_scalar_and_mondrian():
    probs = {"a": 0.6, "b": 0.3, "c": 0.1}
    assert conformal.lac_score(probs, "b") == pytest.approx(0.7)
    assert conformal.lac_score(probs, "missing") == 1.0
    assert conformal.prediction_set(probs, 0.75) == ["a", "b"]
    assert conformal.prediction_set(probs, 0.3) == []
    # Mondrian: a is held to 0.3 and drops out, b passes at 0.8, c has no
    # calibration quantile and is admitted rather than silently dropped.
    assert conformal.prediction_set(probs, {"a": 0.3, "b": 0.8}) == ["b", "c"]


def test_marginal_coverage_on_2000_exchangeable_draws():
    calibration, test = _draws(1709), _draws(1710)
    qhat = conformal.split_quantile(calibration, ALPHA)
    report = conformal.coverage(test, qhat)
    assert report["n"] == N_DRAWS
    assert report["coverage"] >= 0.88
    # Informative sets: admitting all 4 labels would cover trivially.
    assert report["mean_set_size"] < 3.0


def test_mondrian_coverage_holds_per_class():
    calibration, test = _draws(1711), _draws(1712)
    qhats = conformal.mondrian_quantiles(calibration, ALPHA)
    assert set(qhats) == {""} and set(qhats[""]) == {"c0", "c1", "c2", "c3"}
    assert conformal.coverage(test, qhats[""])["coverage"] >= 0.88
    for label in ("c0", "c1", "c2", "c3"):
        rows = [row for row in test if row["target"] == label]
        # About 500 rows per class: 0.85 sits about 2.5 standard errors below 0.9.
        assert conformal.coverage(rows, qhats[""])["coverage"] >= 0.85


def test_mondrian_groups_by_family():
    rows = [{**row, "family": "f1"} for row in _draws(3, 200)]
    rows += [{**row, "family": "f2"} for row in _draws(4, 200, signal=0.2)]
    qhats = conformal.mondrian_quantiles(rows, ALPHA)
    assert set(qhats) == {"f1", "f2"}
    # The weak-signal family needs wider sets, so its quantiles are larger.
    assert sum(qhats["f2"].values()) > sum(qhats["f1"].values())


def test_control_wrong_level_quantile_fails_the_same_check():
    calibration, test = _draws(1709), _draws(1710)
    too_tight = conformal.split_quantile(calibration, 0.5)
    assert conformal.coverage(test, too_tight)["coverage"] < 0.88


def test_control_shifted_draws_break_the_guarantee():
    qhat = conformal.split_quantile(_draws(1709), ALPHA)
    shifted = _draws(1713, signal=0.0)  # not exchangeable with calibration
    assert conformal.coverage(shifted, qhat)["coverage"] < 0.88


@pytest.mark.parametrize("call", [
    lambda: conformal.lac_quantile([0.1], 0),
    lambda: conformal.lac_quantile([0.1], 1),
    lambda: conformal.lac_quantile([0.1], True),
    lambda: conformal.lac_quantile([], 0.1),
    lambda: conformal.lac_quantile([1.5], 0.1),
    lambda: conformal.lac_quantile([float("nan")], 0.1),
    lambda: conformal.prediction_set({"a": 0.5, "b": 0.4}, 0.5),
    lambda: conformal.prediction_set({"a": 1.0}, 1.5),
    lambda: conformal.prediction_set({"a": 1.0}, {"a": -0.1}),
    lambda: conformal.mondrian_quantiles([{"probabilities": {"a": 1.0}}], 0.1),
])
def test_invalid_inputs_are_refused(call):
    with pytest.raises(ValueError):
        call()
