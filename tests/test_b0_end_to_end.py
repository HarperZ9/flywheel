import json
from pathlib import Path

from harness.verified_bench import (
    load_task_set,
    run_private_benchmark,
    verified_frontier,
)


REPO = Path(__file__).resolve().parent.parent


def _curated_solutions():
    by_id = {}
    for line in (REPO / "tasks" / "curated" / "hard_v3.jsonl").read_text(
        encoding="utf-8"
    ).splitlines():
        if line.strip():
            row = json.loads(line)
            by_id[row["task_id"]] = row["solution"]
    return by_id


class StubBackend:
    """Offline backend matching the ladder's bounded chat contract."""

    def __init__(self, name, answers):
        self.name, self._answers = name, answers

    def chat(self, messages, *, system="", max_tokens=2048, temperature=0, seed=0):
        prompt = messages[0]["content"]
        return {"text": self._answers.get(prompt, "def broken(): return None\n")}


def _first_n_tasks(n):
    return load_task_set(REPO / "tasks" / "b0" / "task_set.jsonl")[:n]


def test_good_backend_verifies_at_one(tmp_path):
    tasks = _first_n_tasks(3)
    sols = _curated_solutions()
    answers = {task["prompt"]: sols[task["task_id"]] for task in tasks}
    good = StubBackend("flywheel-stub-good", answers)
    bench = run_private_benchmark(
        tasks=tasks,
        ladder=[good],
        workspace_root=tmp_path,
        created_at="2026-08-29T00:00:00Z",
    )
    assert bench["denominator"] == {"tasks": 3, "endpoints": 1,
                                    "replicates": 1, "attempts": 3}
    assert bench["bench_sha256"]
    assert "does_not_prove" in bench
    frontier = verified_frontier(bench, None)
    rate = {row["endpoint"]: row["verified_pass_rate"] for row in frontier["rankings"]}
    assert rate["flywheel-stub-good"] == 1.0


def test_garbage_backend_verifies_at_zero(tmp_path):
    tasks = _first_n_tasks(3)
    garbage = StubBackend("flywheel-stub-garbage", {})
    bench = run_private_benchmark(
        tasks=tasks,
        ladder=[garbage],
        workspace_root=tmp_path,
        created_at="2026-08-29T00:00:00Z",
    )
    frontier = verified_frontier(bench, None)
    rate = {row["endpoint"]: row["verified_pass_rate"] for row in frontier["rankings"]}
    assert rate["flywheel-stub-garbage"] == 0.0


def test_seal_is_deterministic(tmp_path):
    tasks = _first_n_tasks(3)
    sols = _curated_solutions()
    answers = {task["prompt"]: sols[task["task_id"]] for task in tasks}
    kwargs = {
        "ladder": [StubBackend("s", answers)],
        "created_at": "2026-08-29T00:00:00Z",
    }
    first = run_private_benchmark(tasks=tasks, workspace_root=tmp_path / "a", **kwargs)
    second = run_private_benchmark(tasks=tasks, workspace_root=tmp_path / "b", **kwargs)
    assert first["bench_sha256"] == second["bench_sha256"]
