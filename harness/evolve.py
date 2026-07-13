"""evolve.py — the meta-loop: composes scout + telemetry feeds into one ranked
improvement pipeline with falsifier-gated application. The acceleration engine.

Super-linear compounding (not just accumulation): each cycle (a) collects
improvement candidates from research + efficiency feeds, (b) ranks by leverage x
ease x falsifiability, (c) classifies — config+falsifiable candidates are
AUTO-APPLY (the system self-tunes where a falsifier proves no regression);
capability/code candidates are GATED (surfaced for admission, never auto-applied
— that automates confusion). After each applied+verified change, telemetry
re-profiles and the next cycle starts from the higher baseline.

Bounded honestly by: compute (the CPT), the falsifier gate (no change lands
unless it passes), and the no-learned-model-in-the-accept-path invariant. Real
acceleration, not infinite — but each turn of the loop genuinely raises the
floor the next turn starts from.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class ImprovementCandidate:
    source: str          # "scout" | "telemetry" | "outer_loop"
    description: str
    leverage: float      # 0..1 estimated impact
    ease: float          # 0..1 (config=high, code=low)
    falsifiable: bool
    application: str = "surface-only"  # auto-config | gated-capability | surface-only
    validation: str = ""  # the falsifier that proves no regression (if auto)

    @property
    def score(self) -> float:
        f = 1.0 if self.falsifiable else 0.3
        return self.leverage * self.ease * f


CONFIG_HINTS = ("cache", "temp", "budget", "n_candidates", "threshold", "reduce",
                "widen", "increase", "decrease", "escalation", "route", "prune")


def _classify(description: str, falsifiable: bool) -> str:
    d = description.lower()
    looks_config = any(h in d for h in CONFIG_HINTS)
    if looks_config and falsifiable:
        return "auto-config"
    if falsifiable:
        return "gated-capability"
    return "surface-only"


def _validation_for(description: str) -> str:
    d = description.lower()
    if "cache" in d:
        return "re-run task set; cache_hit_rate must not decrease AND pass_rate must not decrease"
    if "escalation" in d or "prune" in d:
        return "re-run M7 eval; avg_oracle_calls must decrease AND pass_rate must not decrease"
    if "temp" in d or "candidates" in d or "budget" in d:
        return "re-run M7 eval; pass_rate must not decrease at matched-or-lower budget"
    return "re-run M7 eval; the relevant metric must improve without pass_rate regression"


def _outer_loop_validation(signal: dict) -> str:
    metric = str(signal.get("bottleneck_metric", "the targeted bottleneck metric")).strip()
    return (f"re-run M7 eval with the proposed mechanism; {metric} must improve "
            "AND pass_rate must not decrease at matched budget")


def collect_candidates(research_feed: dict, efficiency_feed: dict,
                       outer_loop_feed: dict | None = None) -> list[ImprovementCandidate]:
    out: list[ImprovementCandidate] = []
    for t in research_feed.get("actionable_threads", []):
        desc = t.get("suggested_extension") or t.get("title", "")
        out.append(ImprovementCandidate(
            source="scout", description=desc,
            leverage=0.6, ease=0.3, falsifiable=True,
            application=_classify(desc, True),
            validation=_validation_for(desc)))
    for ins in efficiency_feed.get("improvement_candidates", []):
        out.append(ImprovementCandidate(
            source="telemetry", description=ins,
            leverage=0.8, ease=0.7, falsifiable=True,
            application=_classify(ins, True),
            validation=_validation_for(ins)))
    # Outer-loop source (Bilevel Autoresearch, arXiv 2603.23420): introspect the
    # search machinery's own bottleneck signals (MCTS UCB1 imbalance, MAP-Elites
    # archive stagnation) and PROPOSE a new search mechanism. We adopt the
    # proposal half only. A synthesized mechanism is a structural/code change, so
    # it is ALWAYS gated-capability and can never fall into the auto-apply lane,
    # no matter what words its description contains. That is the load-bearing
    # safety property: the paper's outer loop self-injects code; ours never does.
    for signal in (outer_loop_feed or {}).get("bottleneck_signals", []):
        desc = str(signal.get("proposed_mechanism") or signal.get("description", "")).strip()
        if not desc:
            continue
        out.append(ImprovementCandidate(
            source="outer_loop",
            description=desc,
            leverage=float(signal.get("leverage", 0.5)),
            ease=float(signal.get("ease", 0.2)),
            falsifiable=True,
            application="gated-capability",
            validation=_outer_loop_validation(signal)))
    for t in research_feed.get("inspiration_threads", []):
        out.append(ImprovementCandidate(
            source="scout", description=t.get("title", ""),
            leverage=0.4, ease=0.2, falsifiable=False,
            application="surface-only", validation=""))
    return out


def rank_candidates(cands: list[ImprovementCandidate]) -> list[ImprovementCandidate]:
    return sorted(cands, key=lambda c: -c.score)


def meta_cycle(research_feed: dict, efficiency_feed: dict,
               *, baseline: dict | None = None,
               outer_loop_feed: dict | None = None) -> dict:
    """One turn of the acceleration loop. Returns the ranked pipeline:
    auto-config candidates (self-tunable, falsifier-gated), gated-capability
    candidates (need admission), and surface-only (inspiration). The caller
    applies auto-config ones (after their validator passes), re-measures via
    telemetry, and feeds the new baseline into the next meta_cycle.

    outer_loop_feed is optional (Bilevel Autoresearch): bottleneck signals from
    introspecting the search machinery become gated-capability mechanism
    proposals, never auto-applied."""
    cands = rank_candidates(collect_candidates(research_feed, efficiency_feed, outer_loop_feed))
    auto = [c for c in cands if c.application == "auto-config"]
    gated = [c for c in cands if c.application == "gated-capability"]
    surface = [c for c in cands if c.application == "surface-only"]
    return {
        "baseline": baseline or {},
        "auto_apply": [{"description": c.description, "validation": c.validation,
                        "score": round(c.score, 3)} for c in auto],
        "gated": [{"description": c.description, "validation": c.validation,
                   "score": round(c.score, 3)} for c in gated],
        "surface_only": [c.description for c in surface],
        "cycle_summary": (f"{len(auto)} auto-config (self-tunable, falsifier-gated), "
                          f"{len(gated)} gated-capability, {len(surface)} surface-only"),
        "next_step": ("apply auto-config candidates whose validator passes, "
                      "re-run telemetry.profile, feed new baseline into next meta_cycle"),
    }
