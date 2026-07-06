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
