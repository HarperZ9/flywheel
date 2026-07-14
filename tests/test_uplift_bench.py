"""The uplift bench must measure, never manufacture: the wrapped arm is the
verified loop (an external oracle disposes, the wrapper only proposes more),
the delta carries an interval that can include zero, and an included zero is
flagged as the honest null instead of being dressed up as a win."""

import json

from harness.uplift_bench import (SCHEMA, newcombe_diff_interval,
                                  run_uplift_bench, wilson_interval)


class _Out:
    def __init__(self, text):
        self.text = text


class _Stub:
    """Answers `good` from `pass_seed` on; below it, `bad`."""

    def __init__(self, pass_seed=0):
        self.pass_seed = pass_seed
        self.calls = 0

    def generate(self, prompt, *, seed, temperature, max_new_tokens):
        self.calls += 1
        return _Out("good" if seed >= self.pass_seed else "bad")


def _tasks_file(tmp_path, n=4):
    p = tmp_path / "tasks.jsonl"
    p.write_text("\n".join(
        json.dumps({"task_id": f"t{i}", "prompt": f"solve {i}",
                    "max_new_tokens": 64}) for i in range(n)),
        encoding="utf-8")
    return p


def test_wilson_reference_values():
    lo, hi = wilson_interval(8, 10)
    assert abs(lo - 0.490) < 0.005 and abs(hi - 0.943) < 0.005
    lo, hi = wilson_interval(9, 10)
    assert abs(lo - 0.596) < 0.005 and abs(hi - 0.982) < 0.005
    assert wilson_interval(0, 0) == (0.0, 0.0)


def test_wrapped_arm_uplifts_only_through_the_oracle(tmp_path):
    tasks = _tasks_file(tmp_path)
    doc = run_uplift_bench(
        tasks, ["serve"], oracle=lambda cand, task: cand == "good",
        n_candidates=4, proposers={"serve": lambda: _Stub(pass_seed=2)},
        out_path=tmp_path / "uplift.json")
    assert doc["schema"] == SCHEMA
    rows = {r["arm"]: r for r in doc["rows"]}
    assert rows["bare"]["pass_rate"] == 0.0
    assert rows["wrapped"]["pass_rate"] == 1.0
    assert rows["wrapped"]["candidates_mean"] > 1.0
    assert all(r["evidence"] == "synthetic" for r in doc["rows"])
    delta = doc["deltas"][0]
    assert delta["uplift"] == 1.0
    assert delta["includes_zero"] is False
    assert (tmp_path / "uplift.json").exists()


def test_no_measured_uplift_is_an_honest_null(tmp_path):
    tasks = _tasks_file(tmp_path)
    doc = run_uplift_bench(
        tasks, ["serve"], oracle=lambda cand, task: cand == "good",
        n_candidates=4, proposers={"serve": lambda: _Stub(pass_seed=0)})
    delta = doc["deltas"][0]
    assert delta["uplift"] == 0.0
    assert delta["includes_zero"] is True
    assert "no uplift" in delta["note"]


def test_unverifiable_tasks_leave_the_denominator_visibly(tmp_path):
    tasks = _tasks_file(tmp_path, n=4)

    def oracle(cand, task):
        i = int(task["task_id"][1])
        return None if i >= 2 else (cand == "good")

    doc = run_uplift_bench(
        tasks, ["serve"], oracle=oracle, n_candidates=3,
        proposers={"serve": lambda: _Stub(pass_seed=1)})
    rows = {r["arm"]: r for r in doc["rows"]}
    assert rows["bare"]["unverifiable"] == 2
    assert rows["bare"]["graded"] == 2
    assert rows["wrapped"]["unverifiable"] == 2
    assert rows["wrapped"]["graded"] == 2
    # An unverifiable task is never retried: the oracle cannot dispose.
    assert rows["wrapped"]["candidates_mean"] < 3.0


def test_newcombe_interval_reference():
    lo, hi = newcombe_diff_interval(8, 10, 9, 10)
    assert lo < 0.0 < hi  # 80% -> 90% on n=10 includes zero: the honest null
    lo, hi = newcombe_diff_interval(1, 10, 9, 10)
    assert lo > 0.0  # 10% -> 90% on n=10 separates


def test_bench_summary_reads_artifacts_and_stays_honest_when_empty(tmp_path):
    from harness.uplift_bench import bench_summary
    s = bench_summary(tmp_path)
    assert s["runs"] == []
    assert "no uplift bench artifact" in s["note"]
    run_uplift_bench(
        _tasks_file(tmp_path), ["serve"],
        oracle=lambda c, t: c == "good",
        proposers={"serve": lambda: _Stub()},
        out_path=tmp_path / "artifacts" / "uplift" / "run1.json")
    s = bench_summary(tmp_path)
    assert len(s["runs"]) == 1
    assert s["latest"]["schema"] == SCHEMA


def test_live_provider_names_carry_a_model_suffix(tmp_path):
    # "endpoint:model" resolves through the roster (here the stub provider,
    # which generates without a network); the row stays evidence="live"
    # because nothing was injected.
    tasks = _tasks_file(tmp_path, n=2)
    doc = run_uplift_bench(tasks, ["stub:any-model"],
                           oracle=lambda c, t: c.strip() == "pass",
                           n_candidates=2)
    assert "error" not in doc
    assert {r["provider"] for r in doc["rows"]} == {"stub:any-model"}
    assert all(r["evidence"] == "live" for r in doc["rows"])


def test_empty_tasks_is_a_named_error(tmp_path):
    empty = tmp_path / "none.jsonl"
    empty.write_text("", encoding="utf-8")
    assert "error" in run_uplift_bench(
        empty, ["serve"], oracle=lambda c, t: None,
        proposers={"serve": lambda: _Stub()})
