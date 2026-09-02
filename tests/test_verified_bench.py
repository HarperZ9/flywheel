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
    run_benchmark,
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

    def propose(endpoint, prompt):
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
                                    "attempts": 2}
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
