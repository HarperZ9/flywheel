"""Run Harness-squared, as released, on the ledger-quirks substitute benchmark.

This file is a shim, not part of the Flywheel package. It needs a checkout of
google-research/harness2 on sys.path (POSIX only: harness2 imports fcntl) and
the Flywheel tree on sys.path. It plugs two things into Harness-squared's own
code, the same two its bundled demo plugs in:

  LedgerAdapter     a BenchmarkAdapter whose executor runs the harness scripts
                    with self_improve_bench.execute, the executor the Flywheel
                    side uses.
  ScriptedProposer  a Proposer whose edit, selection and reflection sessions
                    are answered by the shared ScriptedEditor and contrast
                    score instead of a model.

Everything else is Harness-squared's released code path: run_task, the
parallel and sequential recursion, finals-only selection, reflection, and the
per-domain Library that carries harnesses and lessons across tasks.

Carry-over: on each probe slot the scripted editor copies the features of the
latest library entry with probability `carry` (declared, default 0.5). The
paper reports 22 to 47 percent of modified files with library provenance.

Rollouts are recomputed from the harness trees Harness-squared hands the
proposer instead of parsed from its rendered markdown. The executor is
deterministic, so the recomputed rollout equals the one Harness-squared ran.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from harness2.core import tree as h2tree
from harness2.core.proposer import Proposer, Reply
from harness2.core.spec import BenchPrompts, BenchSpec, ChannelSpec
from harness2.substrate.opencode import OpencodeSubstrate

from harness import self_improve_bench as bench
from harness.self_improve_bench_agents import ScriptedEditor, apply_change, slot_rng
from harness.self_improve_loop import EditContext, public_view

FILES = ("systemprompt.md", "scripts/summarize.py", "scripts/selfcheck.py")
_HEADER = re.compile(r"^<!--.*?-->\n", re.S)


def flywheel_tree(root: Path) -> dict[str, str]:
    return {f: (Path(root) / f).read_text(encoding="utf-8") for f in FILES}


class LedgerAdapter:
    def __init__(self, root: Path, tasks: list[dict]):
        self.root = Path(root)
        self.by_id = {t["id"]: t for t in tasks}
        self.substrate = OpencodeSubstrate()
        channel = ChannelSpec("opencode", "local/deterministic")
        self.spec = BenchSpec(name="ledgerq", runs_root=self.root / "runs",
                              install_mode="workspace_config",
                              prompts=BenchPrompts(work="reconcile a transaction ledger"),
                              channels={"proposer": channel, "selector": channel},
                              leak_globs=("answer_key*",))
        base = {name: "" for name in self.substrate.surface().always_on}
        base.update(bench.base_tree())
        h2tree.write_tree(self.substrate.surface(), base, self.base_harness(), stubs=False)
        for t in tasks:
            src = self.task_files(t["id"])
            src.mkdir(parents=True, exist_ok=True)
            (src / "ledger.csv").write_text(t["files"]["ledger.csv"], encoding="utf-8")

    def tasks(self, split: str = "all") -> list[str]:
        return list(self.by_id)

    def domain_of(self, task_id: str) -> str:
        return "ledger"

    def task_prompt(self, task_id: str) -> str:
        return bench.PROMPT

    def task_files(self, task_id: str) -> Path:
        return self.root / "sources" / task_id

    def base_harness(self) -> Path:
        return self.root / "base"

    def validate_tree(self, harness) -> None:
        missing = [f for f in FILES[1:] if f not in harness]
        if missing:
            raise ValueError(f"harness lost {missing}")

    def execute(self, task_id, harness_dir, run_id, *, timeout=None) -> Path:
        run_dir = self.root / "executions" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        tree = flywheel_tree(harness_dir or self.base_harness())
        rollout = bench.execute(self.by_id[task_id], tree, run_id)
        (run_dir / "answer.txt").write_text(rollout.output, encoding="utf-8")
        (run_dir / "trajectory.md").write_text(rollout.trajectory, encoding="utf-8")
        return run_dir

    def delivered(self, run_dir: Path) -> bool:
        return (run_dir / "answer.txt").is_file()

    def trajectory(self, run_dir: Path, *, obs_trunc: int) -> str:
        return (run_dir / "trajectory.md").read_text(encoding="utf-8")

    def deliverable_text(self, run_dir: Path) -> str:
        return (run_dir / "answer.txt").read_text(encoding="utf-8")

    def deliverable_files(self, run_dir: Path) -> dict[str, str]:
        return {"answer.txt": self.deliverable_text(run_dir)}


class ScriptedProposer(Proposer):
    def __init__(self, channel, adapter: LedgerAdapter, editor: ScriptedEditor,
                 carry: float):
        super().__init__(channel)
        self.adapter, self.editor, self.carry = adapter, editor, carry

    def call(self, mission, context_dir, label, **kwargs) -> Reply:
        ctx = Path(context_dir)
        if label.startswith("select."):
            text, workspace = self._select(ctx), None
        elif label.startswith("experience."):
            text, workspace = self._reflect(ctx), None
        else:
            text, workspace = self._edit(ctx, label.rsplit(".a", 1)[0]), ctx / "harness"
        reply = Reply(label=label, text=text, ok=True, attempts=1, workspace=workspace)
        self._calls.append(reply)
        return reply

    def _task(self, ctx: Path) -> dict:
        csv_text = (ctx / "source" / "ledger.csv").read_text(encoding="utf-8")
        match = [t for t in self.adapter.by_id.values() if t["files"]["ledger.csv"] == csv_text]
        return public_view(match[0])

    def _edit(self, ctx: Path, slot: str) -> str:
        task = self._task(ctx)
        dim = "INV" if slot.startswith("inv") else "DOM" if slot.startswith("dom") else "COMPOSE"
        current = flywheel_tree(ctx / "harness")
        if dim != "COMPOSE":
            current = self._carry(ctx, task, slot, current)
        ref = bench.execute(task | {"files": task["files"]}, bench.base_tree(), "base1")
        pool = []
        for d in sorted((ctx / "pool").glob("*")) if (ctx / "pool").is_dir() else []:
            if (d / "harness" / "scripts" / "summarize.py").is_file():
                t = flywheel_tree(d / "harness")
                pool.append((d.name, t, bench.execute(task, t, d.name)))
        prop = self.editor.propose(EditContext(task, slot, dim, current, [ref], pool))
        for f in FILES:
            (ctx / "harness" / f).write_text(prop.tree[f], encoding="utf-8")
        return f"<notes>{prop.notes}</notes>"

    def _carry(self, ctx: Path, task: dict, slot: str, current: dict) -> dict:
        entries = sorted((ctx / "library" / "harnesses").glob("*/harness"))
        rng = slot_rng(self.editor.seed, task["id"], "carry:" + slot, self.editor.p_game)
        if not entries or rng.random() >= self.carry:
            return current
        copied = bench.features_of(flywheel_tree(entries[-1]))
        return bench.make_tree(apply_change(bench.features_of(current), copied))

    def _select(self, ctx: Path) -> str:
        best = None
        for path in sorted((ctx / "candidates").glob("*.md")):
            text = _HEADER.sub("", path.read_text(encoding="utf-8"), count=1)
            rollout = bench.Rollout(path.stem, text)
            key = (-bench.contrast_score({}, rollout),
                   hashlib.sha256(text.encode("utf-8")).hexdigest())
            if best is None or key < best[0]:
                best = (key, path.stem)
        return f"<why>highest contrast score</why>\n```choice\n{best[1]}\n```"

    def _reflect(self, ctx: Path) -> str:
        new = bench.features_of(flywheel_tree(ctx / "harness"))
        old = bench.features_of(flywheel_tree(ctx / "base_harness"))
        if new == old:
            return "NO_ENTRY"
        added = sorted(new - old)
        return ("<edits>\ncomponent: scripts/summarize.py\nchange: added "
                f"{added}\nverdict: helped\n</edits>\n<experience>\ncue: ledgers like this one\n"
                f"lesson: carry the features {added}\nevidence: the adopted final's contrast "
                "beat the base rollout\nconfidence: moderate\n</experience>")
