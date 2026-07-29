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
from .oracle import _kill_tree, clear_bytecode, run_env, spawn_killable
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
        # Popen + tree-kill (the oracle.py discipline, PR #16), NOT
        # subprocess.run(timeout=): with shell=True, run()'s timeout kills
        # only the shell -- the candidate, and anything the candidate itself
        # spawned, is a grandchild that survives as an orphan. spawn_killable
        # gives the immediate child its own session so _kill_tree's killpg
        # reaps the whole tree, not just the shell.
        proc = spawn_killable(cmd, cwd=task.workdir, shell=True,
                              env=run_env(), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        try:
            try:
                out, _ = proc.communicate(timeout=self.timeout)
            except BaseException:
                # subprocess.run() (what this call replaced) wrapped Popen in
                # `with Popen(...) as process:` with a bare `except:` that
                # killed the child before re-raising -- a blanket guarantee
                # against any exception mid-run. Popen alone does not give
                # that for free: TimeoutExpired is the common case, but a
                # MemoryError from buffering unbounded candidate output, an
                # OSError off the pipe, or a KeyboardInterrupt/SystemExit
                # hitting mid-wait would all leave alive the very
                # session-leader tree spawn_killable built specifically so
                # _kill_tree could reap it. Kill first, unconditionally, then
                # let the except clauses below classify (or re-raise) as before.
                _kill_tree(proc)
                raise
            got = out.decode("utf-8", errors="replace").strip()
            # a candidate that crashed (rc != 0) never passes, even when its
            # stdout happens to match — especially the empty-expected case,
            # where a candidate that died at import also printed nothing.
            passed = proc.returncode == 0 and got == self.expected
            # the outcome CLASS is a named field, not smuggled into output_hash:
            # a nonzero exit is not a mismatch, a mismatch is not a timeout.
            if proc.returncode != 0:
                status = "nonzero_exit"
            elif passed:
                status = "match"
            else:
                status = "mismatch"
            return DenseResult(passed=passed, reward=(1.0 if passed else 0.0),
                               output_hash=f"{proc.returncode}:{got[:32]}",
                               status=status)
        except subprocess.TimeoutExpired:
            # nothing ran to completion, so there is no output to witness:
            # output_hash stays empty and the class lives in status. The tree
            # is already dead (killed above); this just drains whatever
            # communicate() left on the pipes so the fds get closed.
            try:
                proc.communicate(timeout=10)
            except Exception:
                pass
            return DenseResult(passed=False, reward=0.0,
                               output_hash="", status="timeout")
        except Exception as e:
            return DenseResult(passed=False, reward=0.0,
                               output_hash="", status=f"error:{type(e).__name__}")


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
