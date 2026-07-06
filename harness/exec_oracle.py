"""exec_oracle.py — the python_executor dense oracle (Qwythos tool-harness pattern).

Runs candidate code in a subprocess, captures stdout, compares to an expected
output. This is the dense-signal oracle that makes M6 verifier-guided search
work on REAL quantitative/algorithmic tasks (compute X, count Y) — the
PytestOracle handles test-function tasks; this handles output-matching tasks.

Pulled from the Qwythos-9B card: their tool harness used python_executor +
web_search to get 7/7 on hard factual prompts where closed-book fabricates.
That's our verified_inference thesis in miniature; this oracle is the
dense-reward half of it.
"""
from __future__ import annotations
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .mcts import DenseResult, DenseOracle
from .oracle import clear_bytecode, run_env
from .task import Task


@dataclass
class ExecTask:
    """Task shape for the executor oracle: candidate code + expected stdout."""
    task_id: str
    prompt: str
    candidate_filename: str
    expected_output: str
    workdir: str
    timeout: int = 12

    def task_json(self) -> dict:
        return {"task_id": self.task_id, "prompt": self.prompt,
                "oracle": "python_executor",
                "oracle_cmd": f"python {self.candidate_filename}",
                "candidate_path": self.candidate_filename,
                "expected_output": self.expected_output}


class PythonExecutorOracle(DenseOracle):
    """Dense oracle: run the candidate, compare stdout to expected. Reward 1.0
    on exact match (normalized), else 0.0. The cheap dense signal that lets M6
    verifier-guided search climb quantitative tasks (compute/count/verify)."""

    oracle_type = "python_executor"

    def __init__(self, expected: str, timeout: int = 12):
        self.expected = expected.strip()
        self.timeout = timeout

    def verify_dense(self, candidate: str, task: Task) -> DenseResult:
        cpath = task.candidate_full()
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_text(candidate, encoding="utf-8")
        clear_bytecode(Path(task.workdir))
        cmd = f"python {task.candidate_path}"
        try:
            p = subprocess.run(cmd, cwd=task.workdir, shell=True,
                               env=run_env(), capture_output=True,
                               timeout=self.timeout)
            got = p.stdout.decode("utf-8", errors="replace").strip()
            passed = got == self.expected
            return DenseResult(passed=passed, reward=(1.0 if passed else 0.0),
                               output_hash=f"{p.returncode}:{got[:32]}")
        except subprocess.TimeoutExpired:
            return DenseResult(passed=False, reward=0.0,
                               output_hash="timeout")
        except Exception as e:
            return DenseResult(passed=False, reward=0.0,
                               output_hash=f"err:{type(e).__name__}")


def line_partial_reward(got: str, expected: str) -> float:
    """Denser reward for multi-line output: fraction of matching lines. Lets
    M6 climb tasks where partial output is meaningful (e.g. produce 5 of 7
    correct lines)."""
    g = got.strip().splitlines()
    e = expected.strip().splitlines()
    if not e:
        return 1.0 if not g else 0.0
    n = max(len(g), len(e))
    matches = sum(1 for a, b in zip(g, e) if a.strip() == b.strip())
    return matches / len(e)
