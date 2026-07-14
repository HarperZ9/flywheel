"""uplift_bench.py -- does the wrapper measurably uplift the model? Paired arms.

The one claim the operator wants ("Flywheel raises any model to its best
performance") is only ever earned per metric, per family, with an interval.
This bench runs the SAME task set through the SAME provider twice:

- bare     one candidate, graded by the external oracle (what a raw call or a
           thin web app gives you);
- wrapped  the verified loop: up to n candidates, the FIRST one the oracle
           accepts wins. The oracle disposes; the wrapper only proposes more.

The delta row carries a Newcombe (1998) score interval on the uplift, and an
interval that includes zero is flagged `includes_zero` with a "no uplift
claimed" note -- the honest null is a first-class result, never dressed up.
Latency and candidate counts are reported per arm because the wrapper COSTS
time and tokens; a bench that hid the overhead would be lying by omission.

Honesty is mechanical, exactly as in quality_duel: injected proposers mark
every row evidence="synthetic" (tests can never masquerade as measurements),
unverifiable tasks leave the pass-rate denominator visibly, and nothing
imports this module and fires a quota-consuming run on its own -- a live run
is an operator decision.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

SCHEMA = "flywheel.uplift-bench/v1"
SUMMARY_SCHEMA = "flywheel.uplift-summary/v1"
Z95 = 1.959963984540054


def wilson_interval(passed: int, n: int, z: float = Z95) -> tuple:
    """Wilson score interval; mirrors scripts/run_benchmark_ci.py exactly."""
    if n <= 0:
        return (0.0, 0.0)
    p = passed / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def newcombe_diff_interval(passed_a: int, n_a: int,
                           passed_b: int, n_b: int) -> tuple:
    """Newcombe (1998) method-10 interval for the UPLIFT (b minus a).
    Direction differs from scripts/run_benchmark_ci.py (a minus b) on
    purpose: here b is the wrapped arm and the sign IS the claim."""
    ra = passed_a / n_a if n_a else 0.0
    rb = passed_b / n_b if n_b else 0.0
    la, ua = wilson_interval(passed_a, n_a)
    lb, ub = wilson_interval(passed_b, n_b)
    d = rb - ra
    lower = d - math.sqrt((ua - ra) ** 2 + (rb - lb) ** 2)
    upper = d + math.sqrt((ra - la) ** 2 + (ub - rb) ** 2)
    return (max(-1.0, lower), min(1.0, upper))


def load_tasks(tasks_path, max_tasks=None) -> list:
    tasks = []
    with open(tasks_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                tasks.append(json.loads(line))
            except ValueError:
                continue
            if max_tasks and len(tasks) >= max_tasks:
                break
    return tasks


def _run_arm(proposer, tasks: list, oracle, n_candidates: int) -> dict:
    """One arm over the task set. Per task: propose up to n_candidates times;
    the first oracle-accepted candidate wins; an unverifiable oracle verdict
    stops the attempts (retrying cannot help when nothing can dispose)."""
    passes = fails = unverifiable = 0
    latencies, attempts_used = [], []
    for task in tasks:
        prompt = task.get("prompt", "")
        max_new = int(task.get("max_new_tokens", 512) or 512)
        t0 = time.perf_counter()
        outcome = "fail"
        attempts = 0
        for seed in range(n_candidates):
            attempts += 1
            try:
                out = proposer.generate(
                    prompt, seed=seed,
                    temperature=0.0 if seed == 0 else 0.8,
                    max_new_tokens=max_new)
                candidate = out.text if isinstance(out.text, str) else str(out.text)
            except Exception:
                continue                     # a dead attempt; retries remain
            verdict = oracle(candidate, task)
            if verdict is None:
                outcome = "unverifiable"
                break
            if verdict:
                outcome = "pass"
                break
        latencies.append((time.perf_counter() - t0) * 1000)
        attempts_used.append(attempts)
        if outcome == "pass":
            passes += 1
        elif outcome == "unverifiable":
            unverifiable += 1
        else:
            fails += 1
    graded = passes + fails
    lo, hi = wilson_interval(passes, graded)
    return {
        "n_tasks": len(tasks), "passes": passes, "graded": graded,
        "unverifiable": unverifiable,
        "pass_rate": round(passes / graded, 4) if graded else 0.0,
        "wilson_95": [round(lo, 4), round(hi, 4)],
        "latency_ms_mean": round(sum(latencies) / len(latencies), 3)
                           if latencies else 0.0,
        "candidates_mean": round(sum(attempts_used) / len(attempts_used), 3)
                           if attempts_used else 0.0,
    }


def run_uplift_bench(tasks_path, providers: list, *, oracle,
                     n_candidates: int = 4, proposers: "dict | None" = None,
                     max_tasks: "int | None" = None,
                     out_path=None) -> dict:
    """Bare vs wrapped over every provider. `proposers` maps name -> factory
    (a zero-arg callable returning a fresh proposer); injecting it marks the
    whole run synthetic. Live runs resolve each name from the roster."""
    tasks = load_tasks(tasks_path, max_tasks)
    if not tasks:
        return {"error": f"no tasks loaded from {tasks_path}"}
    synthetic = proposers is not None
    rows, deltas = [], []
    for name in providers:
        if synthetic:
            factory = proposers.get(name)
            if factory is None:
                return {"error": f"no injected proposer for '{name}'"}
        else:
            from .endpoint_registry import make_endpoint_proposer
            # "endpoint:model" pins a specific model on a roster endpoint
            # (e.g. ollama:qwen2.5:7b), same split the OpenAI-compat route uses.
            base, _, sub = name.partition(":")
            def factory(_b=base, _m=sub or None):
                return make_endpoint_proposer(_b, model=_m)
        arms = {}
        for arm, n_cand in (("bare", 1), ("wrapped", n_candidates)):
            row = _run_arm(factory(), tasks, oracle, n_cand)
            row.update({"provider": name, "arm": arm,
                        "n_candidates": n_cand,
                        "evidence": "synthetic" if synthetic else "live"})
            rows.append(row)
            arms[arm] = row
        b, w = arms["bare"], arms["wrapped"]
        lo, hi = newcombe_diff_interval(
            b["passes"], b["graded"], w["passes"], w["graded"])
        includes_zero = lo <= 0.0 <= hi
        deltas.append({
            "provider": name,
            "uplift": round(w["pass_rate"] - b["pass_rate"], 4),
            "newcombe_95": [round(lo, 4), round(hi, 4)],
            "includes_zero": includes_zero,
            "latency_overhead_ms": round(
                w["latency_ms_mean"] - b["latency_ms_mean"], 3),
            "note": ("no uplift claimed: the interval includes zero"
                     if includes_zero else
                     "measured uplift: the interval excludes zero"),
        })
    doc = {"schema": SCHEMA,
           "comparison_key": f"uplift:{Path(str(tasks_path)).stem}",
           "n_candidates": n_candidates,
           "rows": rows, "deltas": deltas,
           "note": "synthetic rows never enter comparison; the wrapped arm "
                   "wins only through the external oracle; overhead is "
                   "reported because the wrapper costs time"}
    if out_path:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc, indent=1), encoding="utf-8")
        doc["artifact_path"] = str(p)
    return doc


def bench_summary(root) -> dict:
    """Read-only roster of persisted bench runs under artifacts/uplift/,
    newest last write wins as `latest`. Honest when nothing has run."""
    runs_dir = Path(root) / "artifacts" / "uplift"
    entries = sorted(runs_dir.glob("*.json"),
                     key=lambda p: p.stat().st_mtime) if runs_dir.is_dir() else []
    runs, latest = [], None
    for p in entries:
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if doc.get("schema") != SCHEMA:
            continue
        runs.append({"path": p.name,
                     "comparison_key": doc.get("comparison_key", ""),
                     "providers": sorted({r.get("provider", "")
                                          for r in doc.get("rows", [])}),
                     "deltas": doc.get("deltas", [])})
        latest = doc
    if not runs:
        return {"schema": SUMMARY_SCHEMA, "runs": [],
                "note": "no uplift bench artifact yet; a live run is an "
                        "operator decision (it consumes provider quota)"}
    return {"schema": SUMMARY_SCHEMA, "runs": runs, "latest": latest}
