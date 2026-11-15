#!/usr/bin/env python3
"""
Flywheel receipt path, end to end, in one command.

What you are about to watch, without the author present:

  1. A coding task is run through the engine.
  2. The engine emits a proof receipt for the result.
  3. A separate process re-derives the result from that receipt and returns MATCH.
  4. A control: a forged receipt is re-derived and returns DRIFT, so you can see
     the check actually checks.

The claim Flywheel makes is narrow and testable: an accepted answer ships a
receipt, and a stranger can reproduce the verdict from the receipt offline. This
script is that stranger, run for you.

Run it with:

    python run_demo.py

No API key, no GPU, no network. Only Python and the installed engine.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK_DIR = HERE / "task"
OUT_DIR = HERE / "out"
RECEIPT = OUT_DIR / "receipt.json"
FORGED = OUT_DIR / "receipt.forged.json"

# The candidate answer under test. In production this text is produced by a
# model; it is pinned here so the demo is deterministic and needs no model,
# key, or GPU. The engine treats it as an opaque string to be checked -- the
# only thing that can accept it is the pytest oracle in task/skeleton/.
CANDIDATE = '''\
def merge_intervals(intervals):
    if not intervals:
        return []
    ivs = sorted([list(iv) for iv in intervals], key=lambda p: p[0])
    out = [ivs[0]]
    for start, end in ivs[1:]:
        if start <= out[-1][1]:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return out
'''


def banner(n: int, title: str) -> None:
    print()
    print("=" * 72)
    print(f"  STEP {n}. {title}")
    print("=" * 72)


def preflight() -> None:
    print("=" * 72)
    print("  FLYWHEEL RECEIPT PATH -- SELF-CONTAINED DEMO")
    print("=" * 72)
    try:
        import importlib.metadata as md
        version = md.version("flywheel-verify")
    except Exception:
        print()
        print("  The engine is not installed. Install it and pytest, then re-run:")
        print()
        print("      pip install flywheel-verify pytest")
        print()
        sys.exit(2)
    try:
        import harness.loop  # noqa: F401
        import harness.verify_receipt  # noqa: F401
    except Exception as exc:  # pragma: no cover
        print(f"\n  The engine is installed but did not import: {exc!r}")
        print("      pip install --upgrade flywheel-verify pytest")
        sys.exit(2)
    print(f"  python           : {sys.version.split()[0]}")
    print(f"  flywheel-verify  : {version}")
    print(f"  demo directory   : {HERE.name}/")
    print("  network / API key: none used")


def run_task_and_emit_receipt() -> dict:
    """Run the task through the real engine and write its proof receipt."""
    from harness.task import load_task
    from harness.proposer import StubProposer
    from harness.oracle import PytestOracle
    from harness.loop import run_loop

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)

    task = load_task(TASK_DIR)
    banner(1, "The task the engine will run")
    print(f"  task id     : {task.task_id}")
    print(f"  oracle      : {task.oracle}")
    print(f"  oracle cmd  : {task.oracle_cmd}")
    print(f"  prompt      : {task.prompt}")

    banner(2, "Run the task, emit a proof receipt")
    print("  Running the oracle against the candidate answer ...")
    result = run_loop(
        task,
        StubProposer(CANDIDATE),
        PytestOracle(),
        envelopes_dir=str(OUT_DIR / "envelopes"),
    )
    env = result.envelope
    env.write(RECEIPT)

    print()
    print(f"  verdict     : {env.verdict}          (PASS / FAIL / UNDECIDED / UNVERIFIABLE)")
    print(f"  accepted    : {result.accepted}")
    print(f"  witness     : {result.witness.verdict if result.witness else 'n/a'}")
    print(f"  receipt file: out/{RECEIPT.name}")
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def show_receipt(receipt: dict) -> None:
    banner(3, "What the receipt records")
    for key in ("task_id", "oracle", "oracle_cmd", "verdict", "oracle_output_hash", "model_ref"):
        print(f"  {key:20s}: {receipt.get(key)}")
    print()
    print("  The receipt binds the task, the exact command, the candidate answer,")
    print("  the recomputed output hash, and the verdict. It carries no trust of its")
    print("  own: everything in it is re-checkable from the task files beside it.")


def rederive(receipt_path: Path, label: str) -> dict:
    """Run the engine's offline verifier as a SEPARATE process."""
    rel = receipt_path.relative_to(HERE).as_posix()
    cmd = [sys.executable, "-m", "harness.verify_receipt",
           "--receipt", str(receipt_path), "--task-dir", str(TASK_DIR)]
    print(f"  command     : python -m harness.verify_receipt --receipt {rel} --task-dir task")
    print(f"  ({label} -- a fresh process, re-running the oracle from the receipt)")
    print()
    proc = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True)
    print(proc.stdout.rstrip())
    if proc.stderr.strip():
        print("  [stderr]", proc.stderr.strip())
    print(f"  exit code   : {proc.returncode}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"verdict": "PARSE_ERROR", "exit": proc.returncode}


def forge_receipt(receipt: dict) -> None:
    forged = dict(receipt)
    forged["verdict"] = "FAIL"  # claim the task failed, though the answer passes
    FORGED.write_text(json.dumps(forged, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    preflight()
    receipt = run_task_and_emit_receipt()
    show_receipt(receipt)

    banner(4, "Independent re-derivation from the receipt")
    honest = rederive(RECEIPT, "the honest receipt")

    banner(5, "Control: forge the receipt, re-derive, expect DRIFT")
    print("  Flipping the stored verdict from PASS to FAIL and re-checking.")
    print("  A receipt that could not be forged would still say MATCH here; a real")
    print("  one must catch the tamper.")
    print()
    forge_receipt(receipt)
    forged = rederive(FORGED, "the forged receipt")

    banner(6, "Verdict")
    print("  Re-derivation vocabulary: MATCH / DRIFT / UNVERIFIABLE.")
    print(f"    honest receipt  -> {honest.get('verdict')}")
    print(f"    forged receipt  -> {forged.get('verdict')}")
    print()
    print("  Does not prove: this shows the receipt path reproduces a verdict")
    print("  offline and catches a tampered verdict. It does not prove the task")
    print("  is hard, that the answer is the best one, or anything about a model.")
    print("  It proves one thing precisely: the result re-derives from its receipt,")
    print("  and a forged result does not.")

    ok = honest.get("verdict") == "MATCH" and forged.get("verdict") == "DRIFT"
    print()
    if ok:
        print("  RESULT: receipt path verified. Honest MATCH, forged DRIFT.")
        return 0
    print("  RESULT: unexpected outcome above. The demo did not confirm the path.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
