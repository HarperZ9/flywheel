"""self_improve_adapters.py -- executor, editor and selector adapters for the loop.

The loop takes any object with the right method. These are the stock ones.

  CallableExecutor  wraps a Python function; the substitute benchmark uses it.
  CommandExecutor   runs a command-line agent in a fresh workspace holding the
                    harness tree and the task files, and reads its answer back.
  CommandEditor     runs a command-line agent over an editing context and
                    harvests the edited harness tree from the workspace.
  ContrastSelector  picks the final with the best behavioural-contrast score;
                    ties go to the smallest output digest, so the choice is
                    content-determined and independent of label order.

opencode_argv and codex_argv give the argument shapes for the two executors
Harness-squared ships. Nothing here calls a network service itself; the agent
a command launches does whatever its own configuration says.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable

from . import self_improve_tree as st
from .self_improve_loop import EditContext, Proposal, Rollout


def opencode_argv(model: str) -> list[str]:
    """OpenCode's non-interactive run; model is provider/model, e.g. ollama/qwen3:8b."""
    return ["opencode", "run", "{prompt}", "--dir", "{workdir}", "--model", model,
            "--format", "json"]


def codex_argv(model: str, *, local_provider: str = "") -> list[str]:
    """Codex's non-interactive exec; local_provider='ollama' adds --oss."""
    argv = ["codex", "exec", "--skip-git-repo-check", "-C", "{workdir}", "-m", model,
            "-o", "{workdir}/last_message.txt"]
    if local_provider:
        argv += ["--oss", "--local-provider", local_provider]
    return argv + ["{prompt}"]


def _safe_name(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if not path.parts or path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError(f"unsafe task file name: {name!r}")
    return path


def _fill(argv: list[str], **values: str) -> list[str]:
    return [a.format(**values) for a in argv]


@dataclass
class CallableExecutor:
    fn: Callable[[dict, st.Tree, str], Rollout]

    def execute(self, task: dict, tree: st.Tree, label: str) -> Rollout:
        return self.fn(task, tree, label)


@dataclass
class CommandExecutor:
    argv: list[str]
    prompt_key: str = "prompt"
    files_key: str = "files"            # task[files_key]: {relative name: text}
    output_file: str = "answer.txt"
    timeout: int = 3600

    def execute(self, task: dict, tree: st.Tree, label: str) -> Rollout:
        with tempfile.TemporaryDirectory(prefix="fw-si-") as tmp:
            ws = Path(tmp)
            st.write_tree(tree, ws / "harness")
            for name, text in (task.get(self.files_key) or {}).items():
                dest = ws / _safe_name(name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(text, encoding="utf-8")
            proc = subprocess.run(_fill(self.argv, prompt=str(task.get(self.prompt_key, "")),
                                        workdir=str(ws)),
                                  cwd=ws, capture_output=True, text=True,
                                  timeout=self.timeout, check=False)
            out = ws / self.output_file
            answer = out.read_text(encoding="utf-8") if out.is_file() else proc.stdout
            return Rollout(label, answer, trajectory=proc.stdout[-20000:],
                           delivered=proc.returncode == 0 and bool(answer.strip()),
                           error=proc.stderr[-2000:] if proc.returncode else "")


def write_edit_context(ctx: EditContext, ws: Path) -> None:
    """Lay out what an editor may read: never a grader key, never a rubric."""
    st.write_tree(ctx.current, ws / "harness")
    (ws / "task.json").write_text(json.dumps(ctx.task, indent=1, sort_keys=True),
                                  encoding="utf-8")
    for r in ctx.reference:
        (ws / "rollouts").mkdir(exist_ok=True)
        (ws / "rollouts" / f"{r.label}.md").write_text(r.trajectory or r.output,
                                                     encoding="utf-8")
    for label, tree, rollout in ctx.pool:
        st.write_tree(tree, ws / "pool" / label / "harness")
        (ws / "pool" / label / "rollout.md").write_text(rollout.trajectory or rollout.output,
                                                      encoding="utf-8")
    (ws / "lessons.json").write_text(json.dumps(ctx.lessons, indent=1), encoding="utf-8")


@dataclass
class CommandEditor:
    argv: list[str]
    mission: Callable[[EditContext], str]
    timeout: int = 3600

    def propose(self, ctx: EditContext) -> Proposal:
        with tempfile.TemporaryDirectory(prefix="fw-si-edit-") as tmp:
            ws = Path(tmp)
            write_edit_context(ctx, ws)
            proc = subprocess.run(_fill(self.argv, prompt=self.mission(ctx), workdir=str(ws)),
                                  cwd=ws, capture_output=True, text=True,
                                  timeout=self.timeout, check=False)
            if proc.returncode:
                raise ValueError(f"editor exited {proc.returncode}: {proc.stderr[-300:]}")
            return Proposal(st.read_tree(ws / "harness"), notes=proc.stdout[-2000:])


@dataclass
class ContrastSelector:
    score: Callable[[dict, Rollout], float]
    prefer: tuple[str, ...] = ()       # labels that win a tie, e.g. ("base1",)

    def choose(self, task: dict, finals: dict[str, Rollout]) -> tuple[str, str, dict]:
        scores = {lbl: float(self.score(task, r)) if r.delivered else float("-inf")
                  for lbl, r in finals.items()}
        best = max(scores.values())
        tied = [lbl for lbl, s in scores.items() if s == best]
        pick = min(tied, key=lambda lbl: (lbl not in self.prefer, hashlib.sha256(
            finals[lbl].output.encode("utf-8")).hexdigest()))
        why = f"highest contrast score {best:.3f} among {len(finals)} finals"
        return pick, why, {k: (None if v == float("-inf") else v) for k, v in scores.items()}
