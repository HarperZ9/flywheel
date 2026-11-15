"""Tests for the causal/temporal provenance DAG."""

from __future__ import annotations

import pytest

from coherence_membrane.observation import Observation, Provenance, Status
from coherence_membrane.provenance import (
    BROKEN,
    CAUSED_BY,
    UNVERIFIABLE,
    VALID,
    ProvenanceGraph,
    compute_binding,
)


def _loop_graph():
    """look (MATCH baseline) -> adjust -> commit, hash-chained."""
    g = ProvenanceGraph()
    g.add("look", "observation", "look-digest")
    g.add("adjust", "action", "adjust-digest", parents=["look"], edge_type=CAUSED_BY)
    g.add("commit", "action", "commit-digest", parents=["adjust"], edge_type=CAUSED_BY)
    return g


def test_well_formed_graph_verifies_valid():
    assert _loop_graph().verify().verdict == VALID


def test_empty_graph_is_unverifiable():
    assert ProvenanceGraph().verify().verdict == UNVERIFIABLE


def test_duplicate_node_id_rejected():
    g = ProvenanceGraph()
    g.add("n", "observation", "d")
    with pytest.raises(ValueError):
        g.add("n", "observation", "d2")


def test_unknown_parent_rejected():
    g = ProvenanceGraph()
    with pytest.raises(ValueError):
        g.add("child", "action", "d", parents=["ghost"])


def test_binding_is_parent_order_independent():
    g = ProvenanceGraph()
    g.add("a", "observation", "da")
    g.add("b", "observation", "db")
    n1 = g.add("c1", "action", "dc", parents=["a", "b"])
    n2 = g.add("c2", "action", "dc", parents=["b", "a"])  # parents reversed
    # same content + same parent set -> same binding regardless of listing order
    assert compute_binding("c", "action", "dc", "observed-after",
                           [g.nodes["a"].binding, g.nodes["b"].binding]) == \
           compute_binding("c", "action", "dc", "observed-after",
                           [g.nodes["b"].binding, g.nodes["a"].binding])


def test_tampering_a_node_digest_is_broken():
    g = _loop_graph()
    d = g.to_dict()
    d["nodes"][0]["digest"] = "tampered"           # rewrite the look's digest
    g2 = ProvenanceGraph.from_dict(d)
    v = g2.verify()
    assert v.verdict == BROKEN
    assert any("look" in r for r in v.reasons)


def test_dropping_an_edge_is_broken():
    g = _loop_graph()
    d = g.to_dict()
    d["nodes"][2]["parents"] = []                  # drop commit's parent edge
    g2 = ProvenanceGraph.from_dict(d)
    assert g2.verify().verdict == BROKEN


def test_re_parenting_to_a_different_parent_is_broken():
    g = ProvenanceGraph()
    g.add("a", "observation", "da")
    g.add("b", "observation", "db")
    g.add("child", "action", "dc", parents=["a"])  # child <- a
    d = g.to_dict()
    for n in d["nodes"]:
        if n["node_id"] == "child":
            n["parents"] = ["b"]                    # re-point child to b (binding unchanged)
    assert ProvenanceGraph.from_dict(d).verify().verdict == BROKEN


def test_reversed_node_order_still_verifies_valid():
    # verify() is order-independent: a valid graph serialised child-before-parent
    # must NOT be reported BROKEN (only genuine tamper is).
    g = _loop_graph()
    d = g.to_dict()
    d["nodes"].reverse()
    g2 = ProvenanceGraph.from_dict(d)
    assert g2.verify().verdict == VALID
    # ...but tampering the reversed doc is still caught
    d["nodes"][0]["digest"] = "tampered"
    assert ProvenanceGraph.from_dict(d).verify().verdict == BROKEN


def test_manifest_pin_catches_insertion_and_deletion():
    g = _loop_graph()
    pinned = g.manifest()
    assert g.verify(pinned_manifest=pinned).verdict == VALID
    # insert a fabricated, internally-consistent parentless node
    inserted = ProvenanceGraph.from_dict(g.to_dict())
    inserted.add("ghost", "observation", "ghost-digest")
    assert inserted.verify().verdict == VALID                       # chain alone passes
    assert inserted.verify(pinned_manifest=pinned).verdict == BROKEN  # manifest catches it
    # delete a node
    d = g.to_dict()
    d["nodes"] = [n for n in d["nodes"] if n["node_id"] != "commit"]
    assert ProvenanceGraph.from_dict(d).verify(pinned_manifest=pinned).verdict == BROKEN


def test_tampering_cascades_downstream():
    g = _loop_graph()
    d = g.to_dict()
    d["nodes"][0]["digest"] = "tampered"           # tamper the root look only
    g2 = ProvenanceGraph.from_dict(d)
    reasons = g2.verify().reasons
    # the look mismatches AND the descendants whose bindings chained off it
    assert any("look" in r for r in reasons)
    assert any("commit" in r or "adjust" in r for r in reasons)


def test_roundtrip_preserves_bindings_and_verifies():
    g = _loop_graph()
    g2 = ProvenanceGraph.from_dict(g.to_dict())
    assert g2.verify().verdict == VALID
    assert [n.binding for n in g2.nodes.values()] == [n.binding for n in g.nodes.values()]


def test_ancestors():
    g = _loop_graph()
    assert g.ancestors("commit") == {"adjust", "look"}
    assert g.ancestors("look") == set()


def test_has_confirming_look_ancestor():
    g = _loop_graph()
    assert g.has_confirming_look_ancestor("commit") is True   # has an observation ancestor
    assert g.has_confirming_look_ancestor("commit",
                                          confirming_digests={"look-digest"}) is True
    assert g.has_confirming_look_ancestor("commit",
                                          confirming_digests={"some-other-baseline"}) is False


def test_action_with_no_look_has_no_confirming_ancestor():
    g = ProvenanceGraph()
    g.add("blind-commit", "action", "x")
    assert g.has_confirming_look_ancestor("blind-commit") is False


def test_add_observation_uses_witnessed_identity():
    obs = Observation("visual-artifact", "frame.png", "observed", Status.PASS,
                      Provenance.witness_bytes("frame.png", b"x", "high"),
                      {"identity_sha256": "a" * 64, "perceptual_hash": "0" * 16})
    g = ProvenanceGraph()
    node = g.add_observation("look", obs)
    assert node.kind == "observation" and node.digest == "a" * 64
    assert g.verify().verdict == VALID


def test_add_observation_normalizes_prefixed_digest():
    # an observation with no identity_sha256 falls back to provenance.digest
    # ("sha256:"-prefixed); the node digest must be normalised to bare hex so a
    # confirming_digests match (bare hex) works.
    obs = Observation("x", "s", "observed", Status.PASS,
                      Provenance.witness_bytes("s", b"hello", "high"), data={})
    g = ProvenanceGraph()
    node = g.add_observation("look", obs)
    g.add("commit", "action", "c", parents=["look"])
    assert not node.digest.startswith("sha256:")           # normalised
    bare = obs.provenance.digest[len("sha256:"):]
    assert g.has_confirming_look_ancestor("commit", confirming_digests={bare}) is True
