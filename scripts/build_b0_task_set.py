"""Build a strict B0 task set and separate hidden-test fixtures.

Curated rows keep the reference solution and hidden tests together. This
builder writes only the task id, prompt, and gate command to the model-facing
JSONL, while placing each hidden test in a task-specific fixture directory.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _rows(source: Path, limit: int | None):
    count = 0
    for line_no, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"curated row {line_no} is not JSON") from exc
        if not isinstance(row, dict):
            raise ValueError(f"curated row {line_no} is not an object")
        if limit is not None and count >= limit:
            return
        yield row
        count += 1


def _task_id(row: dict) -> str:
    task_id = row.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise ValueError("curated row is missing a task id")
    path = Path(task_id)
    if path.name != task_id or task_id in {".", ".."}:
        raise ValueError(f"unsafe task id: {task_id!r}")
    return task_id


def build(src_jsonl: Path | str, out_dir: Path | str, *, limit: int | None = None) -> int:
    """Write ``task_set.jsonl`` plus one hidden fixture per curated task."""
    source, output = Path(src_jsonl), Path(out_dir)
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
    output.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    records: list[dict[str, str]] = []
    for row in _rows(source, limit):
        task_id = _task_id(row)
        if task_id in seen:
            raise ValueError(f"duplicate task id: {task_id}")
        prompt = row.get("prompt")
        hidden = row.get("hidden_tests")
        if not isinstance(prompt, str) or not prompt:
            raise ValueError(f"task {task_id!r} has no prompt")
        if not isinstance(hidden, str) or not hidden:
            raise ValueError(f"task {task_id!r} has no hidden tests")
        if "def test_" in prompt:
            raise ValueError(f"task {task_id!r} leaks a hidden test into its prompt")
        fixture = output / task_id
        fixture.mkdir(parents=True, exist_ok=True)
        (fixture / "hidden_test.py").write_text(hidden, encoding="utf-8", newline="\n")
        records.append({
            "task_id": task_id,
            "prompt": prompt,
            "gate_cmd": f"python -m harness.b0_gate {task_id}",
        })
        seen.add(task_id)
    if not records:
        raise ValueError("the task set is empty")
    (output / "task_set.jsonl").write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
        newline="\n",
    )
    return len(records)


def main(argv: list[str]) -> int:
    if len(argv) not in {3, 4}:
        print("usage: build_b0_task_set.py <hard_v3.jsonl> <out_dir> [limit]", file=sys.stderr)
        return 2
    limit = int(argv[3]) if len(argv) == 4 else None
    count = build(argv[1], argv[2], limit=limit)
    print(f"wrote {count} tasks to {argv[2]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
