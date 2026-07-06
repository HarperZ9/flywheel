"""task.py — the task IR for M1.

A Task is the unit the loop consumes. For M1 it is explicit JSON (the NL->IR
compiler that produces this shape is a later input-boundary layer, not M1).
The oracle_cmd must be re-runnable by a third party against the candidate to
reproduce the verdict — that is the M1 falsifier.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Retrieved:
    source: str
    receipt: str
    text: str = ""


@dataclass
class Task:
    task_id: str
    prompt: str
    oracle: str
    oracle_cmd: str
    workdir: str
    candidate_path: str
    system: str = ""
    max_new_tokens: int = 512
    temperature: float = 0.0
    seed: int = 0
    retrieved: list[Retrieved] = field(default_factory=list)

    def workdir_path(self) -> Path:
        return Path(self.workdir)

    def candidate_full(self) -> Path:
        return self.workdir_path() / self.candidate_path


def load_task(task_dir: str | Path, *, workdir: str | Path | None = None) -> Task:
    task_dir = Path(task_dir)
    meta = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    if workdir is None:
        workdir = task_dir / meta.get("workdir_name", "workdir")
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    skel = task_dir / "skeleton"
    if skel.exists():
        for p in skel.rglob("*"):
            if p.is_file():
                rel = p.relative_to(skel)
                dst = workdir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(p.read_bytes())
    return Task(
        task_id=meta["task_id"],
        prompt=meta["prompt"],
        oracle=meta["oracle"],
        oracle_cmd=meta["oracle_cmd"],
        workdir=str(workdir),
        candidate_path=meta["candidate_path"],
        system=meta.get("system", ""),
        max_new_tokens=meta.get("max_new_tokens", 512),
        temperature=meta.get("temperature", 0.0),
        seed=meta.get("seed", 0),
    )
