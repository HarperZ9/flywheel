"""telemetry.py — the algorithmic-efficiency feedback loop.

Every run emits a RunSignal; telemetry aggregates them into an EfficiencyProfile
and surfaces concrete, GROUNDED improvement candidates (the feed-back). "Observe
before optimizing": measure where time/compute goes, name the lever, feed it
back. Same feed-artifact shape as scout.synthesize_feed so research-loop and
efficiency-loop candidates compose into one improvement pipeline.

The loop: do work -> emit signal -> profile -> surface falsifiable insight ->
(gated) apply -> measure again. The system observes its own execution and
proposes its own optimizations — not autonomously applied (that automates
confusion), but surfaced for admission, per the loop_ledger contract.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Iterable

from .loop import LoopResult


@dataclass
class RunSignal:
    task_id: str
    accepted: bool
    cache_hit: bool
    oracle_calls: int
    candidates: int
    elapsed_s: float
    chain_stages: list[str] = field(default_factory=list)
    verdict: str = "FAIL"


def signal_from_result(r: LoopResult) -> RunSignal:
    env = r.envelope
    if r.cache_hit:
        return RunSignal(
            task_id=env.task_id, accepted=r.accepted, cache_hit=True,
            oracle_calls=0, candidates=0, elapsed_s=r.elapsed_s,
            chain_stages=[], verdict=env.verdict)
    return RunSignal(
        task_id=env.task_id, accepted=r.accepted, cache_hit=r.cache_hit,
        oracle_calls=env.budget_spent.get("oracle_calls", 0),
        candidates=env.budget_spent.get("candidates", 0),
        elapsed_s=r.elapsed_s,
        chain_stages=[s["stage"] for s in env.chain],
        verdict=env.verdict)


@dataclass
class EfficiencyProfile:
    n_runs: int
    pass_rate: float
    cache_hit_rate: float
    avg_oracle_calls: float
    avg_candidates: float
    total_elapsed_s: float
    insights: list[str] = field(default_factory=list)


def profile(signals: Iterable[RunSignal]) -> EfficiencyProfile:
    sigs = list(signals)
    n = len(sigs)
    if n == 0:
        return EfficiencyProfile(0, 0.0, 0.0, 0.0, 0.0, 0.0, [])
    accepted = sum(1 for s in sigs if s.accepted)
    hits = sum(1 for s in sigs if s.cache_hit)
    avg_orc = sum(s.oracle_calls for s in sigs) / n
    avg_cand = sum(s.candidates for s in sigs) / n
    total_t = sum(s.elapsed_s for s in sigs)
    pr = accepted / n
    chr_ = hits / n
    insights: list[str] = []
    if n >= 3 and chr_ < 0.1:
        insights.append(
            f"LOW CACHE HIT RATE ({chr_:.0%}): repeated tasks not reusing "
            f"verified results — widen cache key or coalesce similar tasks")
    if avg_orc >= 3 and pr < 0.5:
        insights.append(
            f"HIGH ORACLE COST / LOW PASS ({pr:.0%}, avg_oracle={avg_orc:.1f}): "
            f"M4 escalation (cheap-prune before expensive oracle) cuts compute-to-first-pass")
    if avg_cand >= 4 and pr >= 0.8:
        insights.append(
            f"OVER-SAMPLING (pass={pr:.0%}, avg_cand={avg_cand:.1f}): pass@1 already "
            f"strong — reduce N for this task class to save budget")
    if any("search" in s.chain_stages for s in sigs) and avg_cand <= 1.5 and n >= 2:
        insights.append(
            "SEARCH NOT DIVERSIFYING (search stage present, candidates~1): "
            "check temp profile / voice-cap engagement")
    blocked = sum(1 for s in sigs if s.verdict == "BLOCKED")
    if blocked > 0:
        insights.append(
            f"{blocked} BLOCKED runs — policy gate active; verify denials are "
            f"intended, not over-tight")
    return EfficiencyProfile(n, round(pr, 3), round(chr_, 3),
                             round(avg_orc, 2), round(avg_cand, 2),
                             round(total_t, 3), insights)


def efficiency_feed(signals: Iterable[RunSignal], *, top_k: int = 5) -> dict:
    """The feed-back artifact: efficiency insights as build/config candidates.
    Same shape as scout.synthesize_feed so both loops feed one pipeline."""
    p = profile(signals)
    return {
        "improvement_candidates": p.insights[:top_k],
        "profile": {
            "n_runs": p.n_runs, "pass_rate": p.pass_rate,
            "cache_hit_rate": p.cache_hit_rate,
            "avg_oracle_calls": p.avg_oracle_calls,
            "avg_candidates": p.avg_candidates,
            "total_elapsed_s": p.total_elapsed_s,
        },
        "feed_summary": (f"{len(p.insights)} efficiency insights from "
                         f"{p.n_runs} runs (pass={p.pass_rate:.0%}, "
                         f"cache_hit={p.cache_hit_rate:.0%})"),
    }
