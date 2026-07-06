"""Regression falsifiers for the adversarial-audit findings (2026-07-06).

  A1 (HOLE, wiki): verify() keyed freshness by non-unique source_ref; two nodes
     sharing one ref multiplexed onto one slot -> node B's snapshot could vouch
     for node A (false-fresh). Fixed: node.id keys are primary; a ref shared by
     >1 node is AMBIGUOUS -> UNVERIFIABLE, never MATCH.
  A2 (GAP, seam): no call path fed scout/intake research signal into
     flywheel.spin(research_feed=...) — the research half of the loop was dark.
     Fixed: flywheel.research_feed_from_catalog + IntakeDigest.research_feed.
  A3 (GAP, receipts): scout._relevance docstring states a numeric curve
     (2 -> 0.29, 4 -> 0.44, 7 -> 0.58) that no test pinned. Pinned here.
"""
import pytest

from harness import wiki
from harness.flywheel import research_feed_from_catalog
from harness.intake import digest
from harness.scout import _relevance


# -- A1: shared source_ref must never produce a false-fresh MATCH -------------

SHARED = [
    {"id": "a", "ref": "shared:src", "text": "oracle verification cache diversity"},
    {"id": "b", "ref": "shared:src", "text": "oracle verification cache diversity"},
]


def test_shared_ref_is_ambiguous_never_match():
    # The audit's exact repro: a's upstream drifted, b's is current; the one
    # ref-keyed slot holds b's (still-current) text. Old code: a -> MATCH
    # (false-fresh). Fixed: ref-keyed material for a shared ref is refused.
    base = wiki.build(SHARED)
    v = wiki.verify(base, {"shared:src": "oracle verification cache diversity"})
    assert v["per_node"]["corpus/a"] == "UNVERIFIABLE"
    assert v["per_node"]["corpus/b"] == "UNVERIFIABLE"
    assert set(v["ambiguous_ref"]) == {"corpus/a", "corpus/b"}
    assert v["overall"] != "MATCH"


def test_shared_ref_nodes_verify_via_node_id_keys():
    # id-keyed material is 1:1, so shared-ref nodes CAN be verified precisely:
    base = wiki.build(SHARED)
    v = wiki.verify(base, {
        "corpus/a": "oracle verification cache diversity (edited upstream)",
        "corpus/b": "oracle verification cache diversity",
    })
    assert v["per_node"]["corpus/a"] == "DRIFT"      # a really drifted
    assert v["per_node"]["corpus/b"] == "MATCH"      # b really is fresh
    assert v["overall"] == "DRIFT"
    assert v["ambiguous_ref"] == []


def test_unique_ref_convenience_path_still_works():
    catalog = [{"id": "solo", "ref": "src:solo",
                "text": "oracle verification cache diversity"}]
    base = wiki.build(catalog)
    v = wiki.verify(base, {"src:solo": "oracle verification cache diversity"})
    assert v["per_node"]["corpus/solo"] == "MATCH"


# -- A2: the research half of the loop is wired ------------------------------

CATALOG = [
    {"id": "mech", "ref": "x:1",
     "text": "verification gates bound throughput; the oracle is the limit and "
             "a benchmark ablation would measure it."},
    {"id": "hype", "ref": "x:2", "text": "big model drops this week, hyped as a leap."},
]


def test_research_feed_glue_produces_spin_consumable_shape():
    feed = research_feed_from_catalog(CATALOG)
    # exactly the keys evolve.collect_candidates reads inside spin's meta_cycle
    assert "actionable_threads" in feed and "inspiration_threads" in feed
    assert any("suggested_extension" in t for t in feed["actionable_threads"])


def test_intake_digest_exposes_research_feed_for_spin():
    d = digest(CATALOG, feed_id="t")
    assert d.research_feed.get("actionable_threads"), (
        "one intake must drive BOTH evolve and flywheel.spin")
    # and it matches the glue function's output for the same catalog
    assert d.research_feed["feed_summary"] == \
        research_feed_from_catalog(CATALOG, top_k=6)["feed_summary"]


def test_research_feed_changes_spin_candidates():
    # the seam's own falsifier: a fed spin surfaces research candidates a
    # starved spin cannot. meta_cycle is deterministic, so compare directly.
    from harness.evolve import meta_cycle
    fed = meta_cycle(research_feed_from_catalog(CATALOG), {})
    starved = meta_cycle({}, {})
    n_fed = len(fed["auto_apply"]) + len(fed["gated"])
    n_starved = len(starved["auto_apply"]) + len(starved["gated"])
    assert n_fed > n_starved


# -- A3: the _relevance docstring curve is pinned, not asserted --------------

def test_relevance_curve_matches_docstring():
    assert _relevance(2) == pytest.approx(0.29, abs=0.005)
    assert _relevance(4) == pytest.approx(0.44, abs=0.005)
    assert _relevance(7) == pytest.approx(0.58, abs=0.005)
    assert _relevance(0) == 0.0
    # monotone and saturating (the property the metric exists for)
    vals = [_relevance(n) for n in range(0, 12)]
    assert all(b > a for a, b in zip(vals, vals[1:]))
    assert vals[-1] < 1.0
