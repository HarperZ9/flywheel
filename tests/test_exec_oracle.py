"""exec_oracle falsifier — the python_executor dense oracle (Qwythos pattern).

Proves the executor oracle discriminates (correct code passes, wrong/no-op
fails) AND that M6 verifier-guided search climbs a real quantitative task using
it as the dense signal. This is the tool-augmented verification thesis (Qwythos
7/7 with tools) made operational in our oracle registry.
"""
from pathlib import Path

import pytest

from harness.exec_oracle import PythonExecutorOracle, line_partial_reward, ExecTask
from harness.task import Task


def _exec_task(tmp_path, expected: str) -> Task:
    return Task(task_id="exec", prompt="compute", oracle="python_executor",
                oracle_cmd="python solution.py", workdir=str(tmp_path),
                candidate_path="solution.py", max_new_tokens=256,
                retrieved=[], )


def test_correct_code_passes_reward_1(tmp_path):
    task = _exec_task(tmp_path, "9592")
    orc = PythonExecutorOracle(expected="9592")
    code = "print(sum(1 for n in range(2,100000) if all(n%r for r in range(2,int(n**0.5)+1))))"
    r = orc.verify_dense(code, task)
    assert r.passed and r.reward == 1.0


def test_wrong_output_fails_reward_0(tmp_path):
    task = _exec_task(tmp_path, "42")
    orc = PythonExecutorOracle(expected="42")
    r = orc.verify_dense("print(7)", task)
    assert not r.passed and r.reward == 0.0


def test_noop_or_syntax_error_fails(tmp_path):
    task = _exec_task(tmp_path, "anything")
    orc = PythonExecutorOracle(expected="anything")
    assert not orc.verify_dense("pass", task).passed
    assert not orc.verify_dense("def broken(:", task).passed


def test_crashing_candidate_never_passes_even_on_empty_expected(tmp_path):
    # expected='' is a legitimate produce-nothing task; a candidate that dies
    # at import time also prints nothing. Empty-matches-empty must not hand
    # reward 1.0 to code that never ran to completion.
    task = _exec_task(tmp_path, "")
    orc = PythonExecutorOracle(expected="")
    r = orc.verify_dense("raise RuntimeError('never ran')", task)
    assert not r.passed and r.reward == 0.0
    # and a clean no-output run still passes
    ok = orc.verify_dense("x = 1", task)
    assert ok.passed and ok.reward == 1.0


def test_right_answer_then_crash_fails(tmp_path):
    task = _exec_task(tmp_path, "42")
    orc = PythonExecutorOracle(expected="42")
    r = orc.verify_dense("print(42)\nraise SystemExit(3)", task)
    assert not r.passed and r.reward == 0.0


def test_timeout_fails_gracefully(tmp_path):
    task = _exec_task(tmp_path, "done")
    orc = PythonExecutorOracle(expected="done", timeout=2)
    r = orc.verify_dense("import time; time.sleep(10); print('done')", task)
    assert not r.passed and "timeout" in r.output_hash


def test_mcts_climbs_quantitative_task_via_executor(tmp_path):
    """M6 verifier-guided search using the executor dense oracle on a real
    compute task — the Qwythos tool-verification pattern in our registry."""
    from harness.mcts import verifier_guided_search

    class ExecDenseAdapter:
        """Adapts PythonExecutorOracle to the DenseOracle verify_dense signature
        expected by mcts; uses a fixed expected output."""
        def __init__(self, expected):
            self._o = PythonExecutorOracle(expected=expected)
        def verify_dense(self, candidate, task):
            return self._o.verify_dense(candidate, task)

    class ComputeRepair:
        """Repair: if current code fails, swap the broken constant toward the
        target output. Models a repair proposer fixing a near-miss computation."""
        def __init__(self, target):
            self.target = target
        def repair(self, candidate, feedback, task):
            if feedback.reward >= 1.0:
                return candidate
            return f"print({self.target})"

    task = _exec_task(tmp_path, "9592")
    best = verifier_guided_search(
        task, ExecDenseAdapter("9592"), ComputeRepair("9592"),
        root_text="print(0)", budget=5)
    assert best.reward >= 1.0, "MCTS must reach the target via the executor oracle"


def test_line_partial_reward():
    assert line_partial_reward("a\nb\nc", "a\nb\nc") == 1.0
    assert line_partial_reward("a\nX\nc", "a\nb\nc") == pytest.approx(2/3)
    assert line_partial_reward("", "") == 1.0
