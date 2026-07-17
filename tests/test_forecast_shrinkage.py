"""The point-bias correction the replication demanded. A single seed run's
per-task rate overstates the truth for tasks that passed by luck (a
winner's curse), so the forecast point ran high on both trials.
Empirical-Bayes shrinkage pulls each task's estimate toward the pool by an
amount set by how little data it has, correcting the optimism at source."""

from harness.forecast_shrinkage import shrink_rates


def test_shrinkage_pulls_extremes_toward_the_pool():
    # a lucky-fast task (1 attempt, passed -> raw 1.0) and a never-passer
    rows = [{"task_id": "lucky", "n": 1, "c": 1},
            {"task_id": "never", "n": 5, "c": 0}] + \
           [{"task_id": f"mid{i}", "n": 5, "c": 2} for i in range(10)]
    out = shrink_rates(rows)
    by = {r["task_id"]: r for r in out["rows"]}
    assert by["lucky"]["shrunk"] < 1.0, "a lucky 1/1 must shrink below 1.0"
    assert by["never"]["shrunk"] > 0.0, "a 0/5 must shrink above 0.0"
    # the shrunk estimate stays between the raw rate and the pool mean
    pool = out["pool_mean"]
    assert by["lucky"]["shrunk"] > pool
    assert by["never"]["shrunk"] < pool


def test_no_heterogeneity_means_no_room_to_shrink():
    # every task identical: variance ~0, shrinkage is a no-op-ish (stays put)
    rows = [{"task_id": f"t{i}", "n": 5, "c": 3} for i in range(8)]
    out = shrink_rates(rows)
    for r in out["rows"]:
        assert abs(r["shrunk"] - 0.6) < 0.05


def test_it_is_deterministic():
    rows = [{"task_id": f"t{i}", "n": 5, "c": i % 6} for i in range(20)]
    a = shrink_rates(rows)
    b = shrink_rates(rows)
    assert [r["shrunk"] for r in a["rows"]] == [r["shrunk"] for r in b["rows"]]


def test_empty_is_a_named_error():
    assert "error" in shrink_rates([])
