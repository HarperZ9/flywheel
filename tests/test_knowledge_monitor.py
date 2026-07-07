"""Falsifiers for the knowledge monitor — the assessment's 3-node spec, on the
REAL wiki (build/verify), not stubs.

Load-bearing: subscriptions fire on TRANSITIONS only. A drift observed twice
fires once; recovery back to MATCH fires as its own transition; steady state
never fires (the no-false-positive discipline).
"""
from harness.knowledge_monitor import ANY, KnowledgeMonitor
from harness.wiki import build

CATALOG = [
    {"id": "a", "ref": "src:a", "text": "oracle verification receipt"},   # SEALED
    {"id": "b", "ref": "src:b", "text": "cache memory harness"},          # SEALED
    {"id": "c", "ref": "src:c", "text": ""},                              # UNVERIFIABLE
]


def _monitor(sources):
    return KnowledgeMonitor(build(CATALOG), lambda: dict(sources))


def test_three_verdicts_classified_correctly():
    sources = {"corpus/a": "oracle verification receipt",   # unchanged
               "corpus/b": "cache memory harness (updated)"}  # CHANGED; c absent
    report = _monitor(sources).observe()
    assert report["fresh"] == ["corpus/a"]
    assert report["drifted"] == ["corpus/b"]
    assert report["unverifiable"] == ["corpus/c"]


def test_subscription_fires_exactly_once_per_transition():
    sources = {"corpus/a": "oracle verification receipt",
               "corpus/b": "cache memory harness"}
    m = _monitor(sources)
    fired = []
    m.subscribe("corpus/b", lambda t: fired.append((t.frm, t.to)))
    m.observe()                                   # "" -> MATCH (first sight)
    assert fired == [("", "MATCH")]
    sources["corpus/b"] = "cache memory harness (updated)"
    m.observe()                                   # MATCH -> DRIFT
    m.observe()                                   # DRIFT again: NO re-fire
    m.observe()
    assert fired == [("", "MATCH"), ("MATCH", "DRIFT")]
    sources["corpus/b"] = "cache memory harness"  # source restored
    m.observe()                                   # DRIFT -> MATCH (recovery)
    assert fired[-1] == ("DRIFT", "MATCH")
    assert len(fired) == 3


def test_unrelated_node_subscription_never_fires_on_bs_drift():
    sources = {"corpus/a": "oracle verification receipt",
               "corpus/b": "cache memory harness"}
    m = _monitor(sources)
    a_fired = []
    m.subscribe("corpus/a", lambda t: a_fired.append(t))
    m.observe()
    sources["corpus/b"] = "totally different"
    m.observe()
    m.observe()
    assert len(a_fired) == 1                      # only its own first-sight


def test_wildcard_subscription_sees_all_transitions():
    sources = {"corpus/a": "oracle verification receipt",
               "corpus/b": "cache memory harness"}
    m = _monitor(sources)
    seen = []
    m.subscribe(ANY, lambda t: seen.append(t.node_id))
    m.observe()                                   # 3 first-sight transitions
    assert sorted(seen) == ["corpus/a", "corpus/b", "corpus/c"]


def test_query_api_reads_the_sealed_base():
    sources = {"corpus/a": "oracle verification receipt",
               "corpus/b": "cache memory harness (updated)"}
    m = _monitor(sources)
    assert "corpus/a" in [n.id for n in m.query_by_concepts(["oracle"])]
    # verdict filter before any observation matches nothing (unobserved != fresh)
    assert m.query(verdict="MATCH") == []
    m.observe()
    assert [n.id for n in m.query(verdict="DRIFT")] == ["corpus/b"]
    assert [n.id for n in m.query(verdict="MATCH")] == ["corpus/a"]


def test_monitor_never_mutates_the_base():
    sources = {"corpus/a": "oracle verification receipt"}
    m = _monitor(sources)
    root_before = m.base.seal.root_hash
    m.observe()
    m.observe()
    m.query_by_concepts(["oracle"])
    m.neighbors("corpus/a")
    assert m.base.seal.root_hash == root_before
    assert len(m.base.nodes) == 3
