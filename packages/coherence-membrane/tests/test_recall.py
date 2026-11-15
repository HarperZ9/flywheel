from __future__ import annotations

import pytest

from coherence_membrane.certificate import Certificate, Verdict
from coherence_membrane.reconcile import Criterion
from coherence_membrane.memory import MemoryRecord, MemoryStore, CriterionRef, PerceiveRef
from coherence_membrane.registries import CriterionRegistry, PerceiverRegistry
from coherence_membrane.recall import verify_fresh
from coherence_membrane.phash import MATCH, DRIFT, UNVERIFIABLE


def _source_backed(claim, expect_value):
    # a memory whose truth is re-read from a (mock) source and judged equal to expect
    return MemoryRecord(
        id="m", type="pointer", claim=claim,
        criterion_ref=CriterionRef("equals", "v1", (("expect", expect_value),)),
        perceive_ref=PerceiveRef("source", (("value", claim),)),
    )


def _registries(current_source_value):
    crits = CriterionRegistry()
    # criterion: VERIFIED iff the perceived form == "match"
    crits.register(Criterion("equals", lambda form:
        Certificate(str(form), Verdict.VERIFIED if form == "match" else Verdict.REFUTED, "equals-v1")),
        version="v1")
    percs = PerceiverRegistry()
    # perceiver re-reads the (mock) live source; "match" if it equals the pinned expectation
    percs.register("source", lambda args: (
        "match" if current_source_value == "blue" else "changed",
        current_source_value.encode(),
    ))
    return crits, percs


def test_source_unchanged_is_match():
    s = MemoryStore(); r = _source_backed("blue", "blue"); s.remember(r)
    crits, percs = _registries(current_source_value="blue")
    assert verify_fresh(r, s, criteria=crits, perceivers=percs)[0] == MATCH


def test_source_changed_is_drift():
    s = MemoryStore(); r = _source_backed("blue", "blue"); s.remember(r)
    crits, percs = _registries(current_source_value="red")  # live source moved
    assert verify_fresh(r, s, criteria=crits, perceivers=percs)[0] == DRIFT


def test_unregistered_criterion_is_unverifiable():
    s = MemoryStore(); r = _source_backed("blue", "blue"); s.remember(r)
    assert verify_fresh(r, s, criteria=CriterionRegistry(), perceivers=PerceiverRegistry())[0] == UNVERIFIABLE


def test_graph_backed_supersession():
    s = MemoryStore()
    old = MemoryRecord(id="old", type="decision", claim="use X")
    s.remember(old)
    s.remember(MemoryRecord(id="new", type="decision", claim="use Y"),
               parents=("old",), edge_type="supersedes")
    assert verify_fresh(old, s)[0] == DRIFT       # superseded
    new = s.get("new")
    assert verify_fresh(new, s)[0] == MATCH        # not superseded, no source


from coherence_membrane.recall import recall, RecalledMemory


def _store():
    s = MemoryStore()
    s.remember(MemoryRecord(id="d1", type="decision", claim="adopt reconcile", tags=("arch",)))
    s.remember(MemoryRecord(id="f1", type="fact", claim="sky is blue", tags=("color",)))
    s.remember(MemoryRecord(id="d2", type="decision", claim="defer mip", tags=("arch", "scope")),
               parents=("d1",), edge_type="derived-from")
    return s


def test_recall_by_type():
    out = recall(_store(), type="decision")
    assert {r.record.id for r in out} == {"d1", "d2"}


def test_recall_by_tag_and_match():
    out = recall(_store(), tags=("arch",), match="mip")
    assert [r.record.id for r in out] == ["d2"]


def test_recall_traverse_ancestors():
    """Non-vacuous mixed-edge-type traversal test.

    Graph:  A  <--derived-from-- B  <--supersedes-- C
    - recall(traverse_from=("C","supersedes")) must return exactly {B}
      (follows C's supersedes edge to B; B's edge_type is "derived-from" so stops)
    - recall(traverse_from=("C","derived-from")) must return set()
      (C's edge to B is "supersedes", not "derived-from" -- no match)
    - recall(traverse_from=("B","derived-from")) must return {A}
      (follows B's derived-from edge to A)
    """
    s = MemoryStore()
    a = MemoryRecord(id="A", type="decision", claim="root")
    b = MemoryRecord(id="B", type="decision", claim="derived")
    c = MemoryRecord(id="C", type="decision", claim="superseder")
    s.remember(a)
    s.remember(b, parents=("A",), edge_type="derived-from")
    s.remember(c, parents=("B",), edge_type="supersedes")

    # C's edge to B is "supersedes": following "supersedes" from C reaches B
    out = recall(s, traverse_from=("C", "supersedes"))
    assert {r.record.id for r in out} == {"B"}

    # C's edge to B is "supersedes", not "derived-from": no match
    out2 = recall(s, traverse_from=("C", "derived-from"))
    assert {r.record.id for r in out2} == set()

    # B's edge to A is "derived-from": following "derived-from" from B reaches A
    out3 = recall(s, traverse_from=("B", "derived-from"))
    assert {r.record.id for r in out3} == {"A"}


def test_recall_reverify_attaches_freshness():
    s = _store()
    s.remember(MemoryRecord(id="old", type="decision", claim="x"))
    s.remember(MemoryRecord(id="new", type="decision", claim="y"),
               parents=("old",), edge_type="supersedes")
    crits, percs = CriterionRegistry(), PerceiverRegistry()
    out = recall(s, type="decision", reverify=True, criteria=crits, perceivers=percs)
    fresh = {r.record.id: r.freshness for r in out}
    assert fresh["old"] == DRIFT and fresh["new"] == MATCH


def test_recall_verdict_filter_drifted_only():
    s = _store()
    s.remember(MemoryRecord(id="old", type="decision", claim="x"))
    s.remember(MemoryRecord(id="new", type="decision", claim="y"),
               parents=("old",), edge_type="supersedes")
    crits, percs = CriterionRegistry(), PerceiverRegistry()
    drifted = recall(s, verdict=DRIFT, criteria=crits, perceivers=percs)
    assert [r.record.id for r in drifted] == ["old"]


def test_recall_limit_truncates():
    assert len(recall(_store(), limit=1)) == 1


def test_recall_verdict_filter_without_registries_raises():
    """recall(store, verdict=MATCH) with no registries raises ValueError."""
    s = _store()
    with pytest.raises(ValueError, match="requires criteria and perceivers"):
        recall(s, verdict=MATCH)


def test_recall_reverify_without_registries_raises():
    """recall(store, reverify=True) with no registries raises ValueError."""
    s = _store()
    with pytest.raises(ValueError, match="requires criteria and perceivers"):
        recall(s, reverify=True)
