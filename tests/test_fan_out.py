"""test_fan_out.py — sub-agent fan-out runs isolated sub-tasks and gates on accept.

Success criteria:
  - results are returned in input order; all sub-tasks run.
  - a raising sub-task is captured (ok=False) without sinking the batch.
  - the accept predicate counts only verified sub-results.
  - it composes with the real routed agent loop over isolated roots.
"""
from harness.fan_out import fan_out
from harness.local_tools import ToolExecutor
from harness.router_agent import run_router_agent


def test_runs_all_in_order():
    rep = fan_out([1, 2, 3], lambda x: x * 10)
    assert rep["n"] == 3 and rep["completed"] == 3 and rep["failed"] == 0
    assert [r["result"] for r in rep["results"]] == [10, 20, 30]


def test_a_raising_subtask_is_captured():
    def run(x):
        if x == 2:
            raise ValueError("boom")
        return x

    rep = fan_out([1, 2, 3], run)
    assert rep["completed"] == 2 and rep["failed"] == 1
    assert rep["results"][1]["ok"] is False and "ValueError" in rep["results"][1]["error"]


def test_accept_predicate_counts_verified():
    rep = fan_out([{"v": True}, {"v": False}, {"v": True}],
                  lambda s: s, accept=lambda r: r["v"])
    assert rep["completed"] == 3 and rep["accepted"] == 2


def test_empty_batch():
    rep = fan_out([], lambda x: x)
    assert rep["n"] == 0 and rep["results"] == []


class _StubProposer:
    def __init__(self, script):
        self.script = list(script)

    def generate(self, prompt, **k):
        class _O:
            text = self.script.pop(0) if self.script else "done"
            model_ref = "stub"
            seed = 0
        return _O()


def test_composes_with_the_routed_loop(tmp_path):
    # two isolated sub-agents, each in its own root, each a real (stubbed) loop
    def run_sub(i):
        root = tmp_path / f"sub{i}"
        root.mkdir()
        return run_router_agent(f"sub-goal {i}", endpoint="e", root=str(root),
                                proposer=_StubProposer([f"done {i}"]))

    rep = fan_out([0, 1], run_sub, accept=lambda r: r["verified"])
    assert rep["completed"] == 2 and rep["accepted"] == 2
    assert {r["result"]["final"] for r in rep["results"]} == {"done 0", "done 1"}
