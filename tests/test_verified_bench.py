"""Private verified benchmarks: run a task set across every endpoint,
dispose each attempt through a real gate, seal per-attempt receipts,
and compute the verified cost/quality frontier.

The industry's open wound is the model-vs-harness problem: public
benchmarks are contaminated, vendor numbers are self-reported, and no
competitor can re-check an eval after the fact. This module is the
answer: the tasks come from YOUR repo (they never leak), the gate
decides (no learned model on the accept path), and every attempt is a
receipt a stranger can re-verify offline.
"""
import json

import pytest

from harness.verified_bench import (
    SCHEMA,
    load_task_set,
    replicate_sd,
    run_benchmark,
    run_private_benchmark,
    verified_frontier,
    wilson_95_fields,
)


def _task_set(tmp_path, tasks):
    path = tmp_path / "tasks.jsonl"
    path.write_text(
        "\n".join(json.dumps(t) for t in tasks), encoding="utf-8")
    return path


TASKS = [
    {"task_id": "t1", "prompt": "fix the gate",
     "gate_cmd": "python -m pytest -q tests/test_gate.py"},
    {"task_id": "t2", "prompt": "add the receipt",
     "gate_cmd": "python -m pytest -q tests/test_receipt.py"},
]


def test_load_task_set_is_strict(tmp_path):
    tasks = load_task_set(_task_set(tmp_path, TASKS))
    assert [t["task_id"] for t in tasks] == ["t1", "t2"]
    with pytest.raises(ValueError):
        load_task_set(_task_set(tmp_path, [{"task_id": "x", "prompt": "p"}]))
    with pytest.raises(ValueError):
        load_task_set(_task_set(tmp_path, [TASKS[0], TASKS[0]]))


def _runner(passing_endpoints):
    """An injectable proposer + gate: an endpoint passes iff listed."""

    def propose(endpoint, prompt, seed):
        return f"proposal from {endpoint}: {prompt}"

    def gate(gate_cmd, proposed):
        passed = any(proposed.startswith(f"proposal from {e}")
                     for e in passing_endpoints)
        return {"passed": passed,
                "gate_ref": "rcpt_" + ("a" * 32 if passed else "b" * 32)}

    return propose, gate


def test_the_gate_decides_not_the_model():
    propose, gate = _runner(passing_endpoints=["strong"])
    bench = run_benchmark(
        tasks=TASKS, endpoints=["strong", "weak"],
        propose=propose, run_gate=gate, created_at="2026-08-23T00:00:00Z")
    attempts = bench["attempts"]
    assert len(attempts) == 4  # 2 tasks x 2 endpoints, task-major order
    assert [(a["task_id"], a["endpoint"]) for a in attempts] == [
        ("t1", "strong"), ("t1", "weak"), ("t2", "strong"), ("t2", "weak")]
    strong = next(a for a in attempts
                  if a["endpoint"] == "strong" and a["task_id"] == "t1")
    weak = next(a for a in attempts if a["endpoint"] == "weak")
    assert strong["gate_pass"] is True and strong["gate_ref"]
    assert weak["gate_pass"] is False


def test_benchmark_seals_denominators_and_does_not_prove():
    propose, gate = _runner(passing_endpoints=["strong"])
    bench = run_benchmark(tasks=TASKS, endpoints=["strong"],
                          propose=propose, run_gate=gate,
                          created_at="2026-08-23T00:00:00Z")
    assert bench["schema"] == SCHEMA == "flywheel.verified-bench/v1"
    assert bench["denominator"] == {"tasks": 2, "endpoints": 1,
                                    "replicates": 1, "attempts": 2}
    assert bench["does_not_prove"]
    assert bench["bench_sha256"]


def test_benchmark_is_deterministic():
    propose, gate = _runner(passing_endpoints=["strong"])
    assert run_benchmark(tasks=TASKS, endpoints=["strong"],
                         propose=propose, run_gate=gate,
                         created_at="2026-08-23T00:00:00Z") == \
        run_benchmark(tasks=TASKS, endpoints=["strong"],
                      propose=propose, run_gate=gate,
                      created_at="2026-08-23T00:00:00Z")


def test_frontier_ranks_by_verified_pass_rate():
    propose, gate = _runner(passing_endpoints=["strong"])
    bench = run_benchmark(tasks=TASKS, endpoints=["strong", "weak"],
                          propose=propose, run_gate=gate,
                          created_at="2026-08-23T00:00:00Z")
    frontier = verified_frontier(bench, cost_per_task={
        "strong": 0.02, "weak": 0.001})
    by_endpoint = {r["endpoint"]: r for r in frontier["rankings"]}
    assert by_endpoint["strong"]["verified_pass_rate"] == 1.0
    assert by_endpoint["weak"]["verified_pass_rate"] == 0.0
    assert by_endpoint["strong"]["cost_per_task"] == 0.02


def test_frontier_names_the_pareto_set():
    propose, gate = _runner(passing_endpoints=["strong"])
    bench = run_benchmark(tasks=TASKS, endpoints=["strong", "weak"],
                          propose=propose, run_gate=gate,
                          created_at="2026-08-23T00:00:00Z")
    frontier = verified_frontier(bench, cost_per_task={
        "strong": 0.02, "weak": 0.001})
    # weak is cheaper but passes nothing; strong passes everything but
    # costs more: neither dominates the other, both are on the frontier.
    assert sorted(frontier["pareto"]) == ["strong", "weak"]

    # A dominated endpoint (same pass rate, higher cost) leaves the set.
    bench3 = run_benchmark(tasks=TASKS, endpoints=["strong", "weak", "mid"],
                           propose=propose, run_gate=gate,
                           created_at="2026-08-23T00:00:00Z")
    frontier3 = verified_frontier(bench3, cost_per_task={
        "strong": 0.02, "weak": 0.001, "mid": 0.05})
    assert "mid" not in frontier3["pareto"], (
        "mid passes nothing and costs more than strong: dominated")


def test_wilson_95_fields_match_hand_computed_references():
    # Hand-checked against the Wilson score formula at z = 1.959963984540054:
    # 8/10 -> [0.490162, 0.943318]; 2/2 -> [0.342380, 1.0];
    # 0/2 -> [0.0, 0.657620]. Rounded to 6 places as pool_arms does.
    assert wilson_95_fields(8, 10)["wilson_95"] == pytest.approx(
        [0.490162, 0.943318], abs=1e-6)
    assert wilson_95_fields(2, 2)["wilson_95"] == pytest.approx(
        [0.342380, 1.0], abs=1e-6)
    assert wilson_95_fields(0, 2)["wilson_95"] == pytest.approx(
        [0.0, 0.657620], abs=1e-6)


def test_wilson_95_refuses_a_zero_denominator():
    fields = wilson_95_fields(0, 0)
    assert fields["wilson_95"] is None
    assert "ZERO_DENOMINATOR" in fields["wilson_95_refused"]


def test_frontier_rows_carry_wilson_95():
    propose, gate = _runner(passing_endpoints=["strong"])
    bench = run_benchmark(tasks=TASKS, endpoints=["strong", "weak"],
                          propose=propose, run_gate=gate,
                          created_at="2026-08-23T00:00:00Z")
    frontier = verified_frontier(bench, cost_per_task=None)
    by_endpoint = {r["endpoint"]: r for r in frontier["rankings"]}
    # strong: 2/2 passes; weak: 0/2. Same hand-checked references as above.
    assert by_endpoint["strong"]["wilson_95"] == pytest.approx(
        [0.342380, 1.0], abs=1e-6)
    assert by_endpoint["weak"]["wilson_95"] == pytest.approx(
        [0.0, 0.657620], abs=1e-6)
    for row in frontier["rankings"]:
        assert "wilson_95_refused" not in row


def test_frontier_without_cost_still_ranks_pass_rates():
    propose, gate = _runner(passing_endpoints=["strong"])
    bench = run_benchmark(tasks=TASKS, endpoints=["strong", "weak"],
                          propose=propose, run_gate=gate,
                          created_at="2026-08-23T00:00:00Z")
    frontier = verified_frontier(bench, cost_per_task=None)
    assert frontier["pareto"] == []
    assert frontier["rankings"][0]["endpoint"] == "strong"


def _seeded_runner(failing_seed=2):
    """The gate fails 'strong' on one seed, so replicate rates vary."""

    def propose(endpoint, prompt, seed):
        return f"proposal from {endpoint} seed {seed}: {prompt}"

    def gate(gate_cmd, proposed):
        passed = ("from strong" in proposed
                  and f"seed {failing_seed}:" not in proposed)
        return {"passed": passed, "gate_ref": "rcpt_" + "a" * 32}

    return propose, gate


def test_default_seeds_preserve_single_replicate_shape():
    propose, gate = _runner(passing_endpoints=["strong"])
    bench = run_benchmark(tasks=TASKS, endpoints=["strong"],
                          propose=propose, run_gate=gate,
                          created_at="2026-08-23T00:00:00Z")
    assert bench["seeds"] == [0]
    assert bench["denominator"]["replicates"] == 1
    first = bench["attempts"][0]
    assert (first["seed"], first["repetition"],
            first["randomness_control"]) == (0, 0, "seed")


def test_three_seed_replicates_emit_between_seed_sd():
    propose, gate = _seeded_runner(failing_seed=2)
    bench = run_benchmark(tasks=TASKS, endpoints=["strong"],
                          propose=propose, run_gate=gate,
                          created_at="2026-08-23T00:00:00Z",
                          seeds=[0, 1, 2])
    assert bench["denominator"] == {"tasks": 2, "endpoints": 1,
                                    "replicates": 3, "attempts": 6}
    row = replicate_sd(bench)["rows"][0]
    assert row["statistic"] == "between_seed_sd"
    assert row["randomness_control"] == "seed"
    assert row["n_replicates"] == 3
    # Replicate rates 1.0, 1.0, 0.0. Hand-checked: mean 2/3; sample
    # variance (2*(1/3)^2 + (2/3)^2)/2 = 1/3, sd = sqrt(1/3) = 0.577350.
    assert row["replicate_pass_rates"] == [1.0, 1.0, 0.0]
    assert row["mean"] == pytest.approx(0.666667, abs=1e-6)
    assert row["sd"] == pytest.approx(0.577350, abs=1e-6)


def test_unsupported_provider_class_gets_between_attempt_sd():
    propose, gate = _seeded_runner(failing_seed=2)
    bench = run_benchmark(tasks=TASKS, endpoints=["strong", "weak"],
                          propose=propose, run_gate=gate,
                          created_at="2026-08-23T00:00:00Z",
                          seeds=[0, 1, 2],
                          randomness_control={"weak": "unsupported"})
    for a in bench["attempts"]:
        if a["endpoint"] == "weak":
            assert a["randomness_control"] == "unsupported"
            assert a["seed"] is None
        else:
            assert a["randomness_control"] == "seed"
            assert a["seed"] in (0, 1, 2)
    rows = {r["endpoint"]: r for r in replicate_sd(bench)["rows"]}
    assert rows["strong"]["statistic"] == "between_seed_sd"
    assert rows["weak"]["statistic"] == "between_attempt_sd"
    assert rows["weak"]["sd"] == 0.0  # weak never passes: rates 0,0,0
    assert any("NOT_SEED_REPLICATES" in n
               for n in rows["weak"]["does_not_prove"])
    assert not any("NOT_SEED_REPLICATES" in n
                   for n in rows["strong"]["does_not_prove"])


def test_two_replicates_refuse_the_sd():
    propose, gate = _seeded_runner()
    bench = run_benchmark(tasks=TASKS, endpoints=["strong"],
                          propose=propose, run_gate=gate,
                          created_at="2026-08-23T00:00:00Z", seeds=[0, 1])
    row = replicate_sd(bench)["rows"][0]
    assert row["sd"] is None and row["mean"] is None
    assert "MIN_REPLICATES" in row["sd_refused"] and row["n_replicates"] == 2


def test_seed_and_control_validation():
    propose, gate = _runner(passing_endpoints=["strong"])
    common = dict(tasks=TASKS, endpoints=["strong"], propose=propose,
                  run_gate=gate, created_at="2026-08-23T00:00:00Z")
    for bad_seeds in ([], [0, 0], ["x"], [True]):
        with pytest.raises(ValueError):
            run_benchmark(**common, seeds=bad_seeds)
    with pytest.raises(ValueError):
        run_benchmark(**common, randomness_control={"strong": "maybe"})


def test_replicated_frontier_names_the_pooling_in_does_not_prove():
    propose, gate = _seeded_runner()
    bench = run_benchmark(tasks=TASKS, endpoints=["strong"],
                          propose=propose, run_gate=gate,
                          created_at="2026-08-23T00:00:00Z",
                          seeds=[0, 1, 2])
    frontier = verified_frontier(bench, cost_per_task=None)
    assert "correlated" in frontier["does_not_prove"]


def test_private_benchmark_threads_each_seed_to_the_backend(tmp_path):
    seen = []

    class SeedEcho:
        name = "echo"

        def chat(self, messages, *, system="", max_tokens=2048,
                 temperature=0, seed=0):
            seen.append(seed)
            return {"text": "x"}

    tasks = [{"task_id": "t1", "prompt": "p",
              "gate_cmd": "python -c pass"}]
    bench = run_private_benchmark(
        tasks=tasks, ladder=[SeedEcho()], workspace_root=tmp_path,
        created_at="2026-08-23T00:00:00Z", seeds=[7, 8, 9])
    assert seen == [7, 8, 9]
    assert [(a["seed"], a["repetition"]) for a in bench["attempts"]] == [
        (7, 0), (8, 1), (9, 2)]
