"""evolve falsifier — the acceleration engine composes feeds, ranks by
falsifiable leverage, and gates application correctly.

The load-bearing properties:
  - config+falsifiable candidates (telemetry insights) classify as auto-config
    (the system self-tunes where safe) and rank ABOVE inspiration-only.
  - capability/code candidates classify as gated (never auto-applied — that
    automates confusion).
  - non-falsifiable threads stay surface-only.
  - the meta_cycle output has the acceleration shape (apply -> re-measure -> next).
"""
import pytest

from harness.evolve import (collect_candidates, rank_candidates, meta_cycle,
                            ImprovementCandidate, _classify, CONFIG_HINTS)


RESEARCH_FEED = {
    "actionable_threads": [
        {"title": "T1", "suggested_extension": "measurable mechanism: add cache eviction knob, ablate pass-rate"},
        {"title": "T2", "suggested_extension": "new oracle for property checks (code change)"},
    ],
    "inspiration_threads": [
        {"title": "Intelligence as emergent entropy (metaphor, no mechanism)"},
    ],
}
EFFICIENCY_FEED = {
    "improvement_candidates": [
        "LOW CACHE HIT RATE (5%): widen cache key or coalesce similar tasks",
        "HIGH ORACLE COST / LOW PASS: M4 escalation (cheap-prune) cuts compute-to-first-pass",
        "OVER-SAMPLING: pass@1 strong, reduce N for this task class",
    ],
}


def test_telemetry_config_insights_are_auto_config():
    cands = collect_candidates(RESEARCH_FEED, EFFICIENCY_FEED)
    telemetry_cands = [c for c in cands if c.source == "telemetry"]
    assert telemetry_cands
    assert all(c.application == "auto-config" for c in telemetry_cands), (
        "config-shaped telemetry insights must be self-tunable (falsifier-gated)")


def test_code_change_capability_is_gated_not_auto():
    cands = collect_candidates(RESEARCH_FEED, EFFICIENCY_FEED)
    code_cands = [c for c in cands if "new oracle" in c.description.lower()
                  or "code change" in c.description.lower()]
    assert any(c.application == "gated-capability" for c in code_cands), (
        "capability/code changes must be gated, never auto-applied")


def test_inspiration_is_surface_only():
    cands = collect_candidates(RESEARCH_FEED, EFFICIENCY_FEED)
    surface = [c for c in cands if c.application == "surface-only"]
    assert any("emergent entropy" in c.description for c in surface)


def test_ranking_prefers_falsifiable_high_leverage():
    cands = collect_candidates(RESEARCH_FEED, EFFICIENCY_FEED)
    ranked = rank_candidates(cands)
    assert ranked[0].falsifiable
    assert ranked[0].score >= ranked[-1].score
    # a surface-only (inspiration) should never outrank an auto-config
    auto_scores = [c.score for c in ranked if c.application == "auto-config"]
    surface_scores = [c.score for c in ranked if c.application == "surface-only"]
    if auto_scores and surface_scores:
        assert max(auto_scores) > max(surface_scores)


def test_auto_config_has_a_validator():
    cands = collect_candidates(RESEARCH_FEED, EFFICIENCY_FEED)
    for c in cands:
        if c.application == "auto-config":
            assert c.validation, "every auto-config candidate needs a falsifier (no regression gate)"


def test_meta_cycle_has_acceleration_shape():
    out = meta_cycle(RESEARCH_FEED, EFFICIENCY_FEED,
                     baseline={"pass_rate": 0.5, "cache_hit_rate": 0.05})
    assert out["baseline"]["pass_rate"] == 0.5
    assert "auto_apply" in out and out["auto_apply"]
    assert "re-measure" in out["next_step"] or "telemetry" in out["next_step"].lower()
    assert "auto-config" in out["cycle_summary"]


def test_classify_logic():
    assert _classify("widen cache key", True) == "auto-config"
    assert _classify("reduce N candidates threshold", True) == "auto-config"
    assert _classify("add a new neural oracle module", True) == "gated-capability"
    assert _classify("intelligence is entropy", False) == "surface-only"


# --- Outer-loop source (Bilevel Autoresearch, arXiv 2603.23420) ---
# The mechanism: introspect the search machinery's own bottleneck signals and
# PROPOSE a new search mechanism. We adopt the proposal half only; a synthesized
# mechanism is a structural change and must NEVER auto-apply.

OUTER_LOOP_FEED = {
    "bottleneck_signals": [
        {"proposed_mechanism": "MCTS UCB1 exploration constant is imbalanced on "
                               "deep tasks: increase exploration via a tuned-c strategy",
         "bottleneck_metric": "avg_oracle_calls", "leverage": 0.7, "ease": 0.3},
        {"proposed_mechanism": "MAP-Elites archive coverage stagnated 3 cycles: "
                               "widen niche granularity and swap the mutation operator",
         "bottleneck_metric": "archive_coverage", "leverage": 0.6, "ease": 0.2},
    ],
}


def test_outer_loop_candidates_are_collected_with_source():
    cands = collect_candidates(RESEARCH_FEED, EFFICIENCY_FEED, OUTER_LOOP_FEED)
    outer = [c for c in cands if c.source == "outer_loop"]
    assert len(outer) == 2
    assert all(c.validation for c in outer)


def test_outer_loop_never_auto_applies_even_with_config_words():
    # The first signal literally contains "increase" (a CONFIG_HINT) and the
    # second contains "widen" and "swap". A telemetry candidate with those words
    # would classify auto-config. An outer-loop MECHANISM proposal must not: it
    # is a structural change and stays gated. This is the load-bearing property
    # from the research do-not-integrate list (never auto-apply synthesized code).
    cands = collect_candidates(RESEARCH_FEED, EFFICIENCY_FEED, OUTER_LOOP_FEED)
    outer = [c for c in cands if c.source == "outer_loop"]
    assert outer, "expected outer-loop candidates"
    assert all(c.application == "gated-capability" for c in outer)
    assert not any(c.application == "auto-config" for c in outer)


def test_outer_loop_flows_into_gated_lane_of_meta_cycle():
    out = meta_cycle(RESEARCH_FEED, EFFICIENCY_FEED, outer_loop_feed=OUTER_LOOP_FEED)
    gated_descs = " ".join(g["description"] for g in out["gated"])
    assert "UCB1" in gated_descs or "MAP-Elites" in gated_descs
    # every gated entry still carries a falsifier
    assert all(g["validation"] for g in out["gated"])


def test_meta_cycle_backward_compatible_without_outer_loop():
    # Omitting outer_loop_feed must reproduce the prior behavior exactly.
    before = meta_cycle(RESEARCH_FEED, EFFICIENCY_FEED)
    after = meta_cycle(RESEARCH_FEED, EFFICIENCY_FEED, outer_loop_feed=None)
    assert before == after
    assert not any("UCB1" in d for d in after["surface_only"])


def test_outer_loop_blank_proposal_is_skipped():
    feed = {"bottleneck_signals": [{"bottleneck_metric": "x"}, {"proposed_mechanism": "  "}]}
    cands = collect_candidates(RESEARCH_FEED, EFFICIENCY_FEED, feed)
    assert not [c for c in cands if c.source == "outer_loop"]
