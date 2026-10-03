"""run_heldout_rerun.py -- the shipped hard benchmark, rerun with hidden tests that decide.

Each task's tests are split in file order: odd positions (1st, 3rd, ...) are the
visible suite, even positions the held-out suite. The reference solution must pass
both, or the task is excluded and reported. Two arms run through run_loop:

  single     one attempt at temperature 0; scored on the held-out suite
  search     best-of-4; the visible suite picks, the held-out suite decides once

Per task it also records whether the self-scored path (visible tests pick and
decide) would have accepted, so its false accepts are visible.

  python scripts/run_heldout_rerun.py --registry hard --model flywheel-local-coder-14b \
      --base-url http://127.0.0.1:11500/v1 --out artifacts/heldout-rerun/hard.json
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.eval import VERIFIED_INFERENCE  # noqa: E402
from harness.loop import run_loop  # noqa: E402
from harness.oracle import PytestOracle  # noqa: E402
from harness.providers import make_proposer  # noqa: E402
from harness.task import load_task  # noqa: E402
from harness.uplift_bench import wilson_interval  # noqa: E402

PYTEST = "python -m pytest {} -q -p no:cacheprovider"


def split_tests(source: str) -> tuple[str, list[str]]:
    head, *tests = source.split("\ndef test_")
    return head + "\n", ["def test_" + t.rstrip("\n") + "\n" for t in tests]


def registry(name: str) -> list[dict]:
    if name == "hard":
        from harness.tasks_hard import HARD_REGISTRY
        return [vars(t) for t in HARD_REGISTRY]
    path = ROOT / "tasks" / "curated" / f"{name}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def materialize(spec: dict, dest: Path) -> Path | None:
    head, tests = split_tests(spec["hidden_tests"])
    if len(tests) < 2:
        return None
    skel = dest / "skeleton"
    for sub, part in (("tests", tests[0::2]), ("heldout", tests[1::2])):
        (skel / sub).mkdir(parents=True, exist_ok=True)
        (skel / sub / f"test_{sub}.py").write_text(head + "".join(part), encoding="utf-8")
    (skel / spec["candidate_filename"]).write_text("pass\n", encoding="utf-8")
    meta = {"task_id": spec["task_id"], "prompt": spec["prompt"], "oracle": "pytest",
            "oracle_cmd": PYTEST.format("tests/"), "held_out_cmd": PYTEST.format("heldout/"),
            "candidate_path": spec["candidate_filename"],
            "max_new_tokens": spec.get("max_new_tokens", 512)}
    (dest / "task.json").write_text(json.dumps(meta), encoding="utf-8")
    return dest


def _held(text: str, task) -> bool:
    return PytestOracle(cmd_attr="held_out_cmd").verify(text, task).verdict() == "PASS"


def _visible(text: str, task) -> bool:
    return PytestOracle().verify(text, task).verdict() == "PASS"


def run_task(spec: dict, proposer, scratch: Path) -> dict:
    tdir = materialize(spec, scratch / spec["task_id"])
    row = {"task_id": spec["task_id"]}
    if tdir is None:
        return dict(row, excluded="fewer than two tests")
    ref = load_task(tdir, workdir=scratch / "ref" / spec["task_id"])
    if not (_visible(spec["solution"], ref) and _held(spec["solution"], ref)):
        return dict(row, excluded="reference fails a split suite")
    single = run_loop(load_task(tdir, workdir=scratch / "s" / spec["task_id"]), proposer,
                      PytestOracle(), envelopes_dir=scratch / "env", witness_recheck=False)
    stask = load_task(tdir, workdir=scratch / "s2" / spec["task_id"])
    search = run_loop(load_task(tdir, workdir=scratch / "v" / spec["task_id"]), proposer,
                      PytestOracle(), envelopes_dir=scratch / "env", witness_recheck=False,
                      search=VERIFIED_INFERENCE)
    stage = next(s for s in search.envelope.chain if s["stage"] == "search")["payload"]
    picked = any(c["verdict"] == "PASS" for c in stage["candidates"])
    decided = stage.get("decision", {}).get("verdict") == "PASS"
    return dict(row, single_held=_held(single.envelope.candidate, stask),
                single_visible=single.envelope.verdict == "PASS",
                search_held=decided, self_scored_accept=picked,
                self_scored_false_accept=picked and not decided,
                selection=stage["selection"])


def paired_bootstrap(a: list, b: list, iters: int = 10000, seed: int = 7) -> tuple:
    rng, n, diffs = random.Random(seed), len(a), []
    for _ in range(iters):
        idx = [rng.randrange(n) for _ in range(n)]
        diffs.append(sum(a[i] - b[i] for i in idx) / n)
    diffs.sort()
    return (round(diffs[int(0.025 * iters)], 4), round(diffs[int(0.975 * iters) - 1], 4))


def summarize(rows: list) -> dict:
    kept = [r for r in rows if "excluded" not in r]
    n = len(kept)
    s = [int(r["single_held"]) for r in kept]
    v = [int(r["search_held"]) for r in kept]
    fa = sum(r["self_scored_false_accept"] for r in kept)
    acc = sum(r["self_scored_accept"] for r in kept)
    return {"n": n, "excluded": len(rows) - n,
            "single_held_pass": [sum(s), [round(x, 3) for x in wilson_interval(sum(s), n)]],
            "search_held_pass": [sum(v), [round(x, 3) for x in wilson_interval(sum(v), n)]],
            "diff_search_minus_single": round((sum(v) - sum(s)) / n, 4) if n else None,
            "diff_95_paired_bootstrap": paired_bootstrap(v, s) if n else None,
            "self_scored_accepts": acc, "self_scored_false_accepts": fa,
            "false_accept_share": [fa, acc, [round(x, 3) for x in wilson_interval(fa, acc)]]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default="hard")
    ap.add_argument("--model", required=True)
    ap.add_argument("--base-url", default="http://127.0.0.1:11434/v1")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    proposer = make_proposer("ollama", model=a.model, base_url=a.base_url)
    scratch = Path(tempfile.mkdtemp(prefix="heldout-rerun-"))
    try:
        rows = []
        for spec in registry(a.registry):
            rows.append(run_task(spec, proposer, scratch))
            print(json.dumps(rows[-1]), flush=True)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    doc = {"schema": "flywheel.heldout-rerun/v1", "registry": a.registry,
           "model_ref": f"ollama:{a.model}", "rows": rows, "summary": summarize(rows)}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(json.dumps(doc["summary"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
