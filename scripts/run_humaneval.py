#!/usr/bin/env python3
"""run_humaneval.py — HumanEval pass@1 (greedy) against a local model.

The public-leaderboard lane the model page honestly says is missing. Same
discipline as the rest of the harness: deterministic generation (temp 0),
tree-killed sandboxed execution, incremental checkpoint + --resume, and a
dry-run falsifier (canonical solutions MUST score 100% or the runner is
broken and no model number from it can be trusted).

Usage:
  python scripts/run_humaneval.py --dry-run --out /tmp/he_dry.json
  python scripts/run_humaneval.py --ollama-model flywheel-local-coder-14b \
      --out E:/local-model-run/humaneval_flywheel14b.json
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.extract import extract_code
from harness.oracle import _kill_tree
from harness.proposer import EnterpriseProposer

DATA_URL = ("https://github.com/openai/human-eval/raw/master/data/"
            "HumanEval.jsonl.gz")
DATA_PATH = Path("E:/local-model-run/data/HumanEval.jsonl.gz")

INSTRUCT = ("Complete the following Python function. Output ONLY the complete "
            "function definition including the signature shown, with no "
            "explanations and no example usage.\n\n")


def load_tasks() -> list[dict]:
    if not DATA_PATH.exists():
        DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading HumanEval -> {DATA_PATH}", flush=True)
        urllib.request.urlretrieve(DATA_URL, DATA_PATH)
    out = []
    with gzip.open(DATA_PATH, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line))
    return out


def run_candidate(program: str, timeout: int = 15) -> bool:
    """Execute a candidate program in a scratch dir with a tree-killed
    timeout. True iff it exits 0."""
    with tempfile.TemporaryDirectory() as wd:
        path = Path(wd) / "candidate.py"
        path.write_text(program, encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, str(path)], cwd=wd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        try:
            proc.communicate(timeout=timeout)
            return proc.returncode == 0
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            try:
                proc.communicate(timeout=10)
            except Exception:
                pass
            return False


def score(task: dict, completion: str) -> bool:
    """A candidate passes if the official test suite accepts it. Two program
    shapes are tried: the completion as a standalone definition, and the
    original prompt + completion (for body-only outputs)."""
    suffix = "\n\n" + task["test"] + f"\n\ncheck({task['entry_point']})\n"
    candidates = [completion + suffix]
    if f"def {task['entry_point']}" not in completion:
        candidates.append(task["prompt"] + completion + suffix)
    return any(run_candidate(p) for p in candidates)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ollama-model", default="flywheel-local-coder-14b")
    ap.add_argument("--ollama-url", default="http://127.0.0.1:11434/v1")
    ap.add_argument("--dry-run", action="store_true",
                    help="score the canonical solutions; must be 100%")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="humaneval_result.json")
    a = ap.parse_args()

    tasks = load_tasks()
    if a.limit:
        tasks = tasks[: a.limit]
    model_ref = ("dry-run(canonical)" if a.dry_run
                 else f"ollama:{a.ollama_model}")

    partial = Path(str(a.out) + ".partial.jsonl")
    done: dict[str, bool] = {}
    if a.resume and partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                done[row["task_id"]] = bool(row["passed"])
        print(f"resume: {len(done)} rows preloaded", flush=True)

    proposer = None
    if not a.dry_run:
        proposer = EnterpriseProposer(
            base_url=a.ollama_url, model=a.ollama_model,
            api_key_env="OLLAMA_API_KEY", model_ref="ollama")

    rows = []
    for i, t in enumerate(tasks):
        tid = t["task_id"]
        if tid in done:
            rows.append({"task_id": tid, "passed": done[tid]})
            continue
        if a.dry_run:
            completion = t["prompt"] + t["canonical_solution"]
        else:
            out = proposer.generate(
                INSTRUCT + t["prompt"], seed=0, temperature=0.0,
                max_new_tokens=768)
            completion = extract_code(out.text)
        passed = score(t, completion)
        row = {"task_id": tid, "passed": bool(passed)}
        rows.append(row)
        if not a.dry_run:
            with partial.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
        print(f"  [{i + 1}/{len(tasks)}] {tid:14s} "
              f"{'PASS' if passed else 'FAIL'}", flush=True)

    n = len(rows)
    passed_n = sum(r["passed"] for r in rows)
    report = {
        "benchmark": "HumanEval",
        "metric": "pass@1 (greedy, temperature 0)",
        "model_ref": model_ref,
        "n_tasks": n,
        "passed": passed_n,
        "pass_at_1": round(passed_n / max(n, 1), 4),
        "per_task": rows,
        "note": ("single deterministic sample per task; extraction strips "
                 "fences; body-only completions retried with the original "
                 "prompt prepended"),
    }
    Path(a.out).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"pass@1: {report['pass_at_1']:.1%} ({passed_n}/{n}) -> {a.out}")
    if a.dry_run and report["pass_at_1"] != 1.0:
        print("DRY-RUN FALSIFIER FIRED: canonical solutions must score 100%")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
