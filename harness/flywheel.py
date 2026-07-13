"""flywheel.py — the engine. The substrate Project Telos is built around.

Turns the meta-cycle and emits the momentum trace. Each spin: run the task set
→ the M5 receipt cache fills (verified results become reusable assets) →
telemetry profiles the run → evolve surfaces falsifier-gated auto-config
candidates → the next spin starts from a higher/cheaper baseline. The wheel is
hard to start (turn 0: cold cache, full cost) but once spinning, repeats cost
~0 (cache hits skip the proposer + oracle entirely) — genuine compounding
momentum, measured turn-over-turn.

This is the loop the whole program is for: do verified work, bank the receipts,
reuse them, surface the next lever, spin again. Each turn the floor rises.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from .task import Task
from .proposer import Proposer
from .oracle import Oracle
from .cache import ReceiptCache
from .loop import run_loop
from .telemetry import signal_from_result, profile, efficiency_feed, RunSignal
from .eval import ArmConfig
from .evolve import meta_cycle
from . import scout


def research_feed_from_catalog(catalog: list[dict], *,
                               harness_vocab: set[str] | None = None,
                               top_k: int = 5) -> dict:
    """The glue that closes the research half of the loop: a curated catalog
    (X reposts, gather output, a reading list) becomes the research_feed spin()
    threads into every meta_cycle. Without this, research signal only reaches
    evolve through intake and never turns the wheel."""
    return scout.synthesize_feed(scout.rank(catalog, harness_vocab), top_k=top_k)


@dataclass
class SpinTrace:
    turn: int
    n_tasks: int
    pass_rate: float
    cache_hit_rate: float
    avg_oracle_calls: float
    total_elapsed_s: float
    insights: list[str] = field(default_factory=list)
    auto_apply_candidates: list[dict] = field(default_factory=list)
    cycle_summary: str = ""

    def momentum_line(self) -> str:
        return (f"turn {self.turn}: pass={self.pass_rate:.0%} "
                f"cache_hit={self.cache_hit_rate:.0%} "
                f"avg_oracle={self.avg_oracle_calls:.1f} "
                f"elapsed={self.total_elapsed_s:.2f}s")


def spin(task_set: list[Task], proposer: Proposer, oracle: Oracle, *,
         cache: ReceiptCache, search: ArmConfig | None = None,
         turns: int = 3, research_feed: dict | None = None) -> list[SpinTrace]:
    """Run the flywheel for `turns` spins. Turn 0 is cold (cache empty, full
    cost); subsequent turns reuse cached verdicts (cost -> ~0 for repeats) and
    surface auto-config candidates from telemetry + any research feed. Returns
    the momentum trace — the proof the wheel is spinning."""
    traces: list[SpinTrace] = []
    for turn in range(turns):
        signals: list[RunSignal] = []
        for task in task_set:
            r = run_loop(task, proposer, oracle,
                         envelopes_dir=f"envelopes-turn-{turn}",
                         cache=cache, search=search)
            signals.append(signal_from_result(r))
        prof = profile(signals)
        eff_feed = efficiency_feed(signals)
        cycle = meta_cycle(research_feed or {}, eff_feed,
                           baseline={"pass_rate": prof.pass_rate,
                                     "cache_hit_rate": prof.cache_hit_rate})
        traces.append(SpinTrace(
            turn=turn, n_tasks=len(task_set),
            pass_rate=prof.pass_rate, cache_hit_rate=prof.cache_hit_rate,
            avg_oracle_calls=prof.avg_oracle_calls,
            total_elapsed_s=prof.total_elapsed_s,
            insights=prof.insights,
            auto_apply_candidates=cycle.get("auto_apply", []),
            cycle_summary=cycle.get("cycle_summary", "")))
    return traces


def momentum_report(traces: list[SpinTrace]) -> str:
    """Human-readable momentum trace — the flywheel taking off, turn by turn."""
    if not traces:
        return "flywheel: no spins"
    lines = ["flywheel momentum:"]
    for t in traces:
        lines.append("  " + t.momentum_line())
    if len(traces) >= 2:
        d_hit = traces[-1].cache_hit_rate - traces[0].cache_hit_rate
        d_orc = traces[-1].avg_oracle_calls - traces[0].avg_oracle_calls
        d_pass = traces[-1].pass_rate - traces[0].pass_rate
        lines.append(f"  delta over {len(traces)} turns: "
                     f"cache_hit {d_hit:+.0%}, avg_oracle {d_orc:+.1f}, "
                     f"pass {d_pass:+.0%}")
    return "\n".join(lines)
