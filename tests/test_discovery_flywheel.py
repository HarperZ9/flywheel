"""Falsifier for the discovery flywheel (harness/discovery_flywheel.py).

The load-bearing properties: (1) a discovery with NO falsifier can never become
adoptable, no matter how it is ranked -- it is demoted at intake; (2) capability/
code discoveries go to gated admission, never auto-apply; (3) course drift fires
ONLY on the transition, never in steady state; (4) unknown ranks fail closed to
NOISE. No learned judge, no auto-apply, no auto course change.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.discovery_flywheel import (
    Discovery, normalize_sweep, frontier_feed, CourseDriftDetector,
    discovery_cycle, ACTIONABLE, INSPIRATION, NOISE,
)

# a config discovery (auto-tunable) and a code discovery (gated), both falsifiable
CONFIG_DISC = Discovery("bigger battery", ACTIONABLE, "selection",
                        "increase the n_candidates budget threshold",
                        "re-run eval; pass_rate must not drop at matched budget")
CODE_DISC = Discovery("tensor-identity oracle", ACTIONABLE, "verification",
                      "add a symbolic matmul oracle",
                      "calibrate: zero false accepts over a known-good/bad ladder")
NO_FALSIFIER = Discovery("shiny idea", ACTIONABLE, "selection",
                         "adopt the shiny thing", falsifier="")
INSPO = Discovery("interesting but not buildable", INSPIRATION, "perception")
JUNK = Discovery("hype", NOISE, "marketing")


def test_falsifier_gate_blocks_unfalsifiable_actionable():
    feed, demotions = frontier_feed([CONFIG_DISC, NO_FALSIFIER])
    titles = [t["title"] for t in feed["actionable_threads"]]
    assert "bigger battery" in titles          # has a falsifier -> adoptable lane
    assert "shiny idea" not in titles          # no falsifier -> NOT adoptable
    assert any(d["concept"] == "shiny idea" for d in demotions)
    assert "shiny idea" in [t["title"] for t in feed["inspiration_threads"]]


def test_noise_is_dropped():
    feed, _ = frontier_feed([JUNK])
    assert feed["actionable_threads"] == [] and feed["inspiration_threads"] == []


def test_code_discovery_needs_admission_never_auto_applies():
    cyc = discovery_cycle({"ranked": [
        {"concept": CODE_DISC.concept, "rank": "ACTIONABLE", "domain": "verification",
         "application": CODE_DISC.application, "falsifier": CODE_DISC.falsifier}]},
        CourseDriftDetector())
    adm = [g["description"] for g in cyc["needs_admission"]]
    assert any("oracle" in a for a in adm)      # -> admission gate
    assert "adoptable" not in cyc               # NO auto-apply lane for discoveries


def test_even_config_looking_discovery_needs_admission():
    # the dogfooding fix: a config-hint word ("escalation"/"budget") must NOT route
    # an external discovery into evolve's auto-config lane -- it still needs admission
    cyc = discovery_cycle({"ranked": [
        {"concept": CONFIG_DISC.concept, "rank": "ACTIONABLE", "domain": "selection",
         "application": CONFIG_DISC.application, "falsifier": CONFIG_DISC.falsifier}]},
        CourseDriftDetector())
    assert cyc["needs_admission"]               # even config-looking -> admission
    assert all(a["validation"] for a in cyc["needs_admission"])  # carries its falsifier
    assert "adoptable" not in cyc               # never auto-applied


def test_course_drift_fires_only_on_transition():
    det = CourseDriftDetector(course={"selection"}, drift_threshold=2)
    # two adoptable threads in a NEW domain -> should fire once
    new = [Discovery(f"c{i}", ACTIONABLE, "robotics", "app", "falsifier") for i in range(2)]
    r1 = det.observe(new)
    assert r1["fired"] is True and "robotics" in r1["emerging_domains"]
    r2 = det.observe(new)                       # identical -> steady state
    assert r2["fired"] is False                 # does NOT re-fire
    assert r2["emerging_domains"] == ["robotics"]


def test_course_drift_holds_for_in_course_domain():
    det = CourseDriftDetector(course={"selection"}, drift_threshold=2)
    inside = [Discovery(f"c{i}", ACTIONABLE, "selection", "app", "fx") for i in range(3)]
    r = det.observe(inside)
    assert r["fired"] is False and r["recommendation"] == "course holds"


def test_below_threshold_does_not_drift():
    det = CourseDriftDetector(course=set(), drift_threshold=3)
    two = [Discovery(f"c{i}", ACTIONABLE, "quantum", "app", "fx") for i in range(2)]
    r = det.observe(two)
    assert r["emerging_domains"] == []          # 2 < threshold 3


def test_unfalsifiable_does_not_count_toward_drift():
    det = CourseDriftDetector(course=set(), drift_threshold=2)
    # 3 in a new domain but NONE have a falsifier -> not adoptable -> no drift
    soft = [Discovery(f"c{i}", ACTIONABLE, "biology", "app", falsifier="") for i in range(3)]
    r = det.observe(soft)
    assert r["emerging_domains"] == []


def test_unknown_rank_fails_closed_to_noise():
    ds = normalize_sweep({"ranked": [{"concept": "x", "rank": "MAYBE"}]})
    assert ds[0].rank == NOISE


def test_cycle_receipt_shape_and_invariant():
    cyc = discovery_cycle({"ranked": [
        {"concept": "a", "rank": "ACTIONABLE", "domain": "selection",
         "application": "increase threshold", "falsifier": "re-run eval"},
        {"concept": "b", "rank": "ACTIONABLE", "domain": "x", "falsifier": ""},
        {"concept": "c", "rank": "NOISE"}]},
        CourseDriftDetector())
    assert cyc["schema"] == "flywheel.discovery-cycle/v1"
    assert cyc["sensed"] == 3
    assert cyc["noise_dropped"] == 1
    assert len(cyc["demoted_no_falsifier"]) == 1
    assert "auto-applied" in cyc["invariant"] and "admission" in cyc["invariant"]
