"""The honest forecast interval. The k=5 replication falsified our own
sealed interval: the per-task Jeffreys band [0.597, 0.728] held run one
(0.600) and missed run two (0.573), because it captured within-task
uncertainty but not the between-run resampling variance of a fresh bench.
The bootstrap interval resamples whole fresh runs from the per-task
posteriors, so its width includes the run-to-run spread the point interval
missed. This is the loop closing on its own tool: a receipt falsified the
instrument, and the instrument is corrected."""

from harness.forecast_bootstrap import bootstrap_forecast


def _vectors(p_list, k=5):
    # each task: (n draws in the seed run, c correct) -> a Jeffreys posterior
    return [{"task_id": f"t{i}", "n": 5, "c": round(p * 5)}
            for i, p in enumerate(p_list)]


def test_bootstrap_interval_is_wider_than_a_naive_posterior_band():
    rows = _vectors([0.9, 0.8, 0.2, 0.1, 0.5] * 4)
    b = bootstrap_forecast(rows, k=5, draws=2000, seed=7)
    assert b["schema"] == "flywheel.passk-forecast-bootstrap/v1"
    lo, hi = b["interval_95"]
    assert 0.0 <= lo < b["expected_pass_rate"] < hi <= 1.0
    # the bootstrap must be wider than the Jeffreys point band that
    # UNDERCOVERED in the replication, because it also carries the
    # run-to-run resampling variance that band ignored
    assert b["width"] > b["jeffreys_point_width"]


def test_it_is_deterministic_under_a_fixed_seed():
    rows = _vectors([0.7, 0.3, 0.6, 0.4, 0.5] * 6)
    a = bootstrap_forecast(rows, k=5, draws=1500, seed=42)
    b = bootstrap_forecast(rows, k=5, draws=1500, seed=42)
    assert a["interval_95"] == b["interval_95"]
    assert a["expected_pass_rate"] == b["expected_pass_rate"]


def test_a_realized_rate_a_few_points_off_stays_inside():
    # the round-two miss (0.573 vs point ~0.66) must fall INSIDE a
    # correctly-widened interval; the whole point of the fix
    rows = _vectors([0.9, 0.85, 0.8, 0.2, 0.15, 0.6, 0.55, 0.5, 0.45, 0.4] * 11)
    b = bootstrap_forecast(rows, k=5, draws=3000, seed=1)
    lo, hi = b["interval_95"]
    point = b["expected_pass_rate"]
    # a realization 0.03 below the point (the round-two shape) is covered
    assert lo <= point - 0.03


def test_empty_input_is_an_honest_error_not_a_fake_interval():
    b = bootstrap_forecast([], k=5, draws=100, seed=1)
    assert "error" in b
