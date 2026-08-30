"""Run sealed B0 hidden tests against a proposed solution.

The bridge deliberately exposes only a task identifier and a candidate
solution. Hidden fixtures stay in the benchmark repository and are copied to
an isolated temporary directory before pytest runs.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from harness.consensus import accept_gate
from harness.task import Task


def extract_candidate(text: str) -> str:
    """Return source code from plain text or one Markdown code fence."""

    if "```" not in text:
        return text
    start = text.index("```") + 3
    newline = text.find("\n", start)
    if newline == -1:
        return text
    end = text.find("```", newline + 1)
    if end == -1:
        return text
    return text[newline + 1 : end]


def run_gate_for(
    task_id: str,
    proposed: str,
    *,
    repo_root: str | Path | None = None,
    timeout: float = 60,
) -> bool:
    """Run a hidden fixture for ``task_id`` and return whether it passes."""

    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parent.parent
    fixture = root / "tasks" / "b0" / task_id / "hidden_test.py"
    if not fixture.is_file():
        raise FileNotFoundError(f"unknown B0 task fixture: {task_id}")

    with tempfile.TemporaryDirectory(prefix="flywheel-b0-") as directory:
        workdir = Path(directory)
        (workdir / "hidden_test.py").write_text(
            fixture.read_text(encoding="utf-8"), encoding="utf-8"
        )
        task = Task(
            task_id=task_id,
            prompt="",
            oracle="pytest",
            oracle_cmd="python -m pytest hidden_test.py -q",
            workdir=str(workdir),
            candidate_path="solution.py",
        )
        result = accept_gate(task, timeout=timeout).verify(extract_candidate(proposed), task)
        return bool(result.passed)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)
    if len(args) != 2:
        print("usage: python -m harness.b0_gate TASK_ID", file=sys.stderr)
        return 2
    proposed = Path("PROPOSED.md").read_text(encoding="utf-8")
    return 0 if run_gate_for(args[1], proposed) else 1


if __name__ == "__main__":
    raise SystemExit(main())
