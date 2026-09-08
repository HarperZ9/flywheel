"""Legacy one-attempt versus oracle-selected retry diagnostic.

These arms have different generation budgets and reuse the selector as scorer.
Their descriptive difference does not establish workflow uplift. New and stored
v1 results are interpreted by uplift_evidence; historical bytes remain intact.
Use pool.py and pool_arms.py for generation-matched selection experiments with
a distinct held-out scorer. Live generation remains an operator action.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path

from .uplift_evidence import interpret_legacy_run

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
    """Legacy independent-proportions difference interval (b minus a).

    Retained for reproducing historical arithmetic, not paired uplift inference.
    """
    ra = passed_a / n_a if n_a else 0.0
    rb = passed_b / n_b if n_b else 0.0
    la, ua = wilson_interval(passed_a, n_a)
    lb, ub = wilson_interval(passed_b, n_b)
    d = rb - ra
    lower = d - math.sqrt((ua - ra) ** 2 + (rb - lb) ** 2)
    upper = d + math.sqrt((ra - la) ** 2 + (ub - rb) ** 2)
    return (max(-1.0, lower), min(1.0, upper))


def oracle_fingerprint(oracle) -> dict:
    """The check definition as part of the receipt (the Verification
    Horizon requirement): name + source hash, so old results can be
    re-adjudicated when the check strengthens. Unreadable source is
    reported as such, never guessed."""
    import inspect
    name = getattr(oracle, "__name__", type(oracle).__name__)
    try:
        src = inspect.getsource(oracle)
        sha = hashlib.sha256(src.encode("utf-8")).hexdigest()
    except (OSError, TypeError):
        sha = "unavailable"
    return {"name": name, "source_sha256": sha}


def load_tasks(tasks_path, max_tasks=None) -> list:
    tasks = []
    seen = set()
    with open(tasks_path, encoding="utf-8") as f:
        for number, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                task = json.loads(line)
            except ValueError as exc:
                raise ValueError(f"invalid task JSON at line {number}") from exc
            if (not isinstance(task, dict)
                    or not isinstance(task.get("task_id"), str)
                    or not task["task_id"].strip()
                    or not isinstance(task.get("prompt"), str)):
                raise ValueError(f"invalid task record at line {number}")
            if task["task_id"] in seen:
                raise ValueError(f"duplicate task ID at line {number}")
            seen.add(task["task_id"])
            tasks.append(task)
            if max_tasks and len(tasks) >= max_tasks:
                break
    return tasks


def _run_arm(proposer, tasks: list, oracle, n_candidates: int) -> dict:
    """One arm over the task set. Per task: propose up to n_candidates times;
    the first oracle-accepted candidate wins; an unverifiable oracle verdict
    stops the attempts (retrying cannot help when nothing can dispose)."""
    passes = fails = unverifiable = generation_failed = 0
    latencies, attempts_used = [], []
    per_task: list = []   # outcome vectors: heterogeneity vs diversity is
                          # only separable with per-task data
    for task in tasks:
        prompt = task.get("prompt", "")
        max_new = int(task.get("max_new_tokens", 512) or 512)
        t0 = time.perf_counter()
        outcome = "fail"
        attempts = 0
        gen_errors: list = []
        generated = 0
        for seed in range(n_candidates):
            attempts += 1
            try:
                out = proposer.generate(
                    prompt, seed=seed,
                    temperature=0.0 if seed == 0 else 0.8,
                    max_new_tokens=max_new)
                candidate = out.text if isinstance(out.text, str) else str(out.text)
            except Exception as e:
                # This was `except Exception: continue`, which swallowed the
                # error and burned an attempt without recording it. In the bare
                # arm, where n_candidates is 1, that turned "nothing was
                # generated" into a CANDIDATE FAILURE, which is exactly the
                # misattribution harness/verdict.py exists to prevent. It is also
                # a live candidate mechanism for the observed anomaly where four
                # tasks failed in the bare arm and passed in the wrapped arm on
                # its first attempt, the identical seed-0 temp-0 call.
                gen_errors.append(f"{type(e).__name__}: {e}"[:200])
                continue
            generated += 1
            verdict = oracle(candidate, task)
            if verdict is None:
                outcome = "unverifiable"
                break
            if verdict:
                outcome = "pass"
                break
        if not generated:
            # Nothing was ever produced for this task, so there is no candidate
            # to grade. Attributed to the harness and kept OUT of the denominator,
            # the same treatment unverifiable already gets.
            outcome = "generation_failed"
        latencies.append((time.perf_counter() - t0) * 1000)
        attempts_used.append(attempts)
        row = {"task_id": str(task.get("task_id", "")),
               "outcome": outcome, "attempts": attempts,
               "generated": generated}
        if gen_errors:
            row["generation_errors"] = gen_errors
        per_task.append(row)
        if outcome == "pass":
            passes += 1
        elif outcome == "unverifiable":
            unverifiable += 1
        elif outcome == "generation_failed":
            generation_failed += 1
        else:
            fails += 1
    graded = passes + fails
    lo, hi = wilson_interval(passes, graded)
    return {
        "n_tasks": len(tasks), "passes": passes, "graded": graded,
        "tasks": per_task,
        "unverifiable": unverifiable,
        # HARNESS-attributed, excluded from `graded`. A run reporting 0 here
        # either had none or predates this field; the two are not distinguishable
        # in any artifact written before 2026-07-26.
        "generation_failed": generation_failed,
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
    if (type(n_candidates) is not int or n_candidates < 1
            or (max_tasks is not None
                and (type(max_tasks) is not int or max_tasks < 1))):
        return {"error": "candidate and task limits must be positive integers"}
    if (not isinstance(providers, list) or not providers
            or any(not isinstance(p, str) or not p.strip() for p in providers)
            or len(set(providers)) != len(providers)):
        return {"error": "providers must be a nonempty list of unique names"}
    try:
        tasks = load_tasks(tasks_path, max_tasks)
    except (OSError, ValueError) as exc:
        return {"error": str(exc)}
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
        deltas.append({
            "provider": name,
            # Keep provenance beside the descriptive rate difference.
            "evidence": "synthetic" if synthetic else "live",
            "uplift": round(w["pass_rate"] - b["pass_rate"], 4),
            "latency_overhead_ms": round(
                w["latency_ms_mean"] - b["latency_ms_mean"], 3),
        })
    doc = {"schema": SCHEMA,
           "comparison_key": f"uplift:{Path(str(tasks_path)).stem}",
           "n_candidates": n_candidates,
           "oracle": oracle_fingerprint(oracle),
           "rows": rows, "deltas": deltas}
    doc = interpret_legacy_run(doc)
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
        doc = interpret_legacy_run(doc)
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
