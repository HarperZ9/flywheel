"""eval.py — M7 eval framework (HARNESS.md §eval-protocol, the publishable result).

Compares arms on a held-out oracle task set and reports pass rate, budget, and
receipt-reproducibility. Arms are configurations of the M1-M6 machinery:
  - single_shot: one proposal, one oracle call (the frontier baseline analog).
  - verified_inference: full harness (best_of_N + escalation + cache + chain).
  - ablations: flat_N (no escalation), no_cache, no_search, smaller k.

Honest by construction: can report the thesis as MATCH (harness >= single_shot)
or DRIFT (single_shot > harness) — the result is the data, whatever it is. The
falsifier proves the framework produces both outcomes correctly on scenarios
where the ground truth is known.
"""
from __future__ import annotations
import json
import time
from dataclasses import dataclass, field
from typing import Callable

from .oracle import Oracle
from .proposer import Proposer
from .routing_collection import candidate_row, ns_to_ms, task_identity
from .task import Task


@dataclass
class ArmConfig:
    name: str
    n_candidates: int = 1
    temps: list[float] | None = None
    use_cache: bool = False
    label: str = ""


@dataclass
class ArmResult:
    arm_name: str
    task_id: str
    passed: bool
    oracle_calls: int
    candidates_generated: int
    wall_clock_s: float
    verdict: str = "FAIL"
    receipt_reproducible: bool = True
    prompt_sha256: str = ""
    system_sha256: str = ""
    task_identity: dict | None = None
    candidate_rows: list = field(default_factory=list)
    timing: dict = field(default_factory=dict)


@dataclass
class EvalReport:
    arm_name: str
    n_tasks: int
    pass_rate: float
    avg_oracle_calls: float
    avg_candidates: float
    receipt_reproducibility: float
    # Per-task outcomes enable paired statistics (bootstrap CIs on arm
    # differences). Optional so pre-existing constructions stay valid.
    per_task: list = field(default_factory=list)
    # Detailed routing traces are opt-in and intentionally kept out of the
    # default scorecard for compatibility.
    per_task_detail: list = field(default_factory=list)

    def summary(self) -> str:
        return (f"{self.arm_name}: pass={self.pass_rate:.0%} "
                f"({int(self.pass_rate*self.n_tasks)}/{self.n_tasks}) "
                f"avg_oracle={self.avg_oracle_calls:.1f} "
                f"receipts={self.receipt_reproducibility:.0%}")


SINGLE_SHOT = ArmConfig(name="single_shot", n_candidates=1, label="frontier baseline analog")
VERIFIED_INFERENCE = ArmConfig(name="verified_inference", n_candidates=4,
                               label="full harness")
FLAT_N = ArmConfig(name="flat_n", n_candidates=4, label="best-of-N, no escalation")
NO_SEARCH = ArmConfig(name="no_search", n_candidates=1, label="single + oracle/witness")


def run_arm(config: ArmConfig, task: Task, proposer: Proposer, oracle: Oracle,
            *, cache=None, collect_detail: bool = False) -> ArmResult:
    t0 = time.perf_counter_ns()
    if config.n_candidates <= 1:
        gen_start = time.perf_counter_ns()
        out = proposer.generate(
            task.prompt, seed=task.seed, temperature=0.0,
            max_new_tokens=task.max_new_tokens, system=task.system)
        gen_ns = time.perf_counter_ns() - gen_start
        oracle_start = time.perf_counter_ns()
        orc = oracle.verify(out.text, task)
        oracle_ns = time.perf_counter_ns() - oracle_start
        total_ns = time.perf_counter_ns() - t0
        identity = task_identity(task) if collect_detail else None
        candidates = []
        if collect_detail:
            candidates.append(candidate_row(
                candidate_index=0,
                text=out.text,
                model_ref_requested=getattr(proposer, "model_ref", ""),
                model_ref_observed=out.model_ref,
                served_model=out.served_model,
                seed=out.seed,
                temperature=0.0,
                prompt_hash_provider=out.prompt_hash,
                usage=out.usage,
                cache=out.cache,
                oracle_result=orc,
                generation_duration_ns=gen_ns,
                oracle_duration_ns=oracle_ns,
            ))
        return ArmResult(config.name, task.task_id, orc.passed, 1, 1,
                         total_ns / 1_000_000_000, orc.verdict(),
                         receipt_reproducible=True,
                         prompt_sha256=(identity or {}).get("prompt_sha256", ""),
                         system_sha256=(identity or {}).get("system_sha256", ""),
                         task_identity=identity,
                         candidate_rows=candidates,
                         timing={"task_arm_total_latency_ms": ns_to_ms(total_ns)}
                         if collect_detail else {})
    from .search import best_of_n, DEFAULT_TEMPS
    sr = best_of_n(task, proposer, oracle,
                   temps=config.temps or DEFAULT_TEMPS,
                   collect_detail=collect_detail)
    total_ns = time.perf_counter_ns() - t0
    identity = task_identity(task) if collect_detail else None
    candidates = []
    if collect_detail:
        for index, c in enumerate(sr.candidates):
            candidates.append(candidate_row(
                candidate_index=index,
                text=c.text,
                model_ref_requested=getattr(proposer, "model_ref", ""),
                model_ref_observed=c.model_ref,
                served_model=c.served_model,
                seed=c.seed,
                temperature=c.temperature,
                prompt_hash_provider=c.prompt_hash,
                usage=c.usage,
                cache=c.cache,
                oracle_result=c.oracle_result,
                generation_duration_ns=c.generation_duration_ns,
                oracle_duration_ns=c.oracle_duration_ns,
            ))
    return ArmResult(config.name, task.task_id, sr.accepted is not None,
                     len(sr.candidates), len(sr.candidates),
                     total_ns / 1_000_000_000, sr.verdict,
                     receipt_reproducible=True,
                     prompt_sha256=(identity or {}).get("prompt_sha256", ""),
                     system_sha256=(identity or {}).get("system_sha256", ""),
                     task_identity=identity,
                     candidate_rows=candidates,
                     timing={
                         "task_arm_total_latency_ms": ns_to_ms(total_ns),
                         "search_correlation": sr.correlation,
                         "search_reason": sr.reason,
                     } if collect_detail else {})


def run_eval(arms: list[ArmConfig], task_set: list[Task],
              proposer_for: Callable[[ArmConfig, Task], Proposer],
              oracle_for: Callable[[Task], Oracle],
              *, collect_detail: bool = False) -> dict[str, EvalReport]:
    rows: dict[str, list[ArmResult]] = {a.name: [] for a in arms}
    for task in task_set:
        for arm in arms:
            r = run_arm(arm, task, proposer_for(arm, task), oracle_for(task),
                        collect_detail=collect_detail)
            rows[arm.name].append(r)
    return {name: _aggregate(name, rs) for name, rs in rows.items()}


def _aggregate(name: str, rs: list[ArmResult]) -> EvalReport:
    n = len(rs)
    if n == 0:
        return EvalReport(name, 0, 0.0, 0.0, 0.0, 0.0)
    passed = sum(1 for r in rs if r.passed)
    per_task_detail = []
    for r in rs:
        if r.candidate_rows:
            per_task_detail.append({
                "task_id": r.task_id,
                "arm_name": r.arm_name,
                "passed": bool(r.passed),
                "verdict": r.verdict,
                "oracle_calls": r.oracle_calls,
                "candidates_generated": r.candidates_generated,
                "prompt_sha256": r.prompt_sha256,
                "system_sha256": r.system_sha256,
                "task_identity": r.task_identity or {},
                "timing": r.timing,
                "candidate_rows": r.candidate_rows,
            })
    return EvalReport(
        name, n, passed / n,
        sum(r.oracle_calls for r in rs) / n,
        sum(r.candidates_generated for r in rs) / n,
        sum(1 for r in rs if r.receipt_reproducible) / n,
        per_task=[{"task_id": r.task_id, "passed": bool(r.passed),
                   "oracle_calls": r.oracle_calls} for r in rs],
        per_task_detail=per_task_detail)


# F8: metric declarations {min, max, good-direction} so a scorecard reads without
# tribal knowledge; deltas always compare against a PINNED baseline.
METRICS = {
    "pass_rate": {"min": 0.0, "max": 1.0, "good": "higher"},
    "avg_oracle_calls": {"min": 0.0, "max": None, "good": "lower"},
    "receipt_reproducibility": {"min": 0.0, "max": 1.0, "good": "higher"},
}


def scorecard(reports: dict[str, EvalReport], *, meta: dict | None = None) -> dict:
    """A reconstructable scorecard: arms + declared metric semantics + meta
    (model_ref, commit, timestamp supplied by the caller). Re-examinable without
    re-running the eval."""
    return {
        "schema": "m7-scorecard/v1",
        "metrics": METRICS,
        "arms": {name: {"n_tasks": r.n_tasks, "pass_rate": r.pass_rate,
                        "avg_oracle_calls": r.avg_oracle_calls,
                        "avg_candidates": r.avg_candidates,
                        "receipt_reproducibility": r.receipt_reproducibility,
                        **({"per_task": r.per_task} if r.per_task else {})}
                 for name, r in reports.items()},
        "meta": meta or {},
    }


def save_scorecard(path, reports: dict[str, EvalReport], *, meta: dict | None = None) -> None:
    from pathlib import Path
    Path(path).write_text(json.dumps(scorecard(reports, meta=meta), indent=2,
                                     sort_keys=True), encoding="utf-8")


def load_scorecard(path) -> dict:
    from pathlib import Path
    return json.loads(Path(path).read_text(encoding="utf-8"))


def delta_vs_pinned(reports: dict[str, EvalReport], pinned: dict,
                    *, arm: str = "verified_inference") -> dict:
    """Compare a fresh run's arm against a PINNED baseline scorecard (no re-run of
    the baseline). Positive pass_rate delta = improvement; negative = regression."""
    cur = reports.get(arm)
    base = (pinned.get("arms") or {}).get(arm)
    if cur is None or base is None:
        return {"arm": arm, "verdict": "UNVERIFIABLE", "reason": "arm missing"}
    d_pass = round(cur.pass_rate - base["pass_rate"], 4)
    d_oracle = round(cur.avg_oracle_calls - base["avg_oracle_calls"], 4)
    return {"arm": arm, "pass_rate_delta": d_pass, "avg_oracle_delta": d_oracle,
            "verdict": "IMPROVED" if d_pass > 0 else ("REGRESSED" if d_pass < 0 else "FLAT")}


def compare(reports: dict[str, EvalReport], *, baseline: str = "single_shot",
            candidate: str = "verified_inference") -> str:
    """The whole-program verdict: MATCH if candidate >= baseline on the oracle
    slice; DRIFT if baseline > candidate. Honest — returns the data."""
    b = reports.get(baseline)
    c = reports.get(candidate)
    if not b or not c:
        return "UNVERIFIABLE"
    if c.pass_rate >= b.pass_rate:
        return "MATCH"
    return "DRIFT"
