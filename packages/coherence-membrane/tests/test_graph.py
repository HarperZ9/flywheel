"""Tests for the Graph L0 substrate -- normalisation, UNVERIFIABLE-carrying, helpers."""
from __future__ import annotations

from coherence_membrane.graph import Graph


def test_empty_graph_is_empty():
    g = Graph()
    assert g.is_empty()
    assert g.node_count() == 0 and g.edge_count() == 0
    assert not g.has_unknown()


def test_nodes_and_edges_normalised_deterministically():
    # built in scrambled order with a duplicate node + duplicate edge
    a = Graph(nodes=("c", "a", "b", "a"), edges=(("b", "a"), ("a", "b")))  # undirected
    b = Graph(nodes=("a", "b", "c"), edges=(("a", "b"),))
    # undirected: (b,a) and (a,b) canonicalise to the SAME edge (a,b); dup collapses
    assert a == b
    assert a.nodes == ("a", "b", "c")
    assert a.edges == (("a", "b"),)


def test_directed_preserves_orientation():
    g = Graph(nodes=("a", "b"), edges=(("b", "a"),), directed=True)
    assert g.edges == (("b", "a"),)
    assert g.neighbors("b") == ("a",)
    assert g.neighbors("a") == ()  # directed: no back-edge


def test_undirected_neighbors_both_directions():
    g = Graph(nodes=("a", "b", "c"), edges=(("a", "b"), ("b", "c")))
    assert g.neighbors("b") == ("a", "c")
    assert g.neighbors("a") == ("b",)


def test_edge_to_undeclared_node_is_unknown_not_dropped():
    # an edge naming a node that was never declared is UNVERIFIABLE structure: it is
    # CARRIED in unknown_edges, never silently added nor silently discarded.
    g = Graph(nodes=("a",), edges=(("a", "ghost"),))
    assert g.edges == ()                      # not added as a real edge
    assert ("a", "ghost") in g.unknown_edges  # but carried as unknown
    assert g.has_unknown()
    assert not g.is_empty()                   # unknowns are first-class content


def test_unknown_only_graph_is_not_empty():
    g = Graph(unknown_nodes=("x",))
    assert not g.is_empty()
    assert g.has_unknown()


def test_weights_and_labels_keyed_canonically():
    g = Graph(nodes=("a", "b"), edges=(("b", "a"),),
              weights=((("a", "b"), 3.0),), labels=((("a", "b"), "road"),))
    # undirected canonical edge is (a,b); weight/label resolve regardless of order
    assert g.weight("a", "b") == 3.0
    assert g.weight("b", "a") == 3.0
    assert g.has_edge("b", "a")
    assert dict(g.labels)[("a", "b")] == "road"


def test_weight_on_absent_edge_is_none():
    g = Graph(nodes=("a", "b"), edges=(("a", "b"),))
    assert g.weight("a", "b") is None  # edge exists but unweighted
    assert g.weight("a", "x") is None  # no such edge


def test_node_ids_coerced_to_strings():
    # an int node and the str of it are the SAME node -- construction is total.
    g = Graph(nodes=(1, 2), edges=((1, 2),), directed=True)
    assert g.nodes == ("1", "2")
    assert g.edges == (("1", "2"),)


def test_to_dict_is_serialisable_and_deterministic():
    g = Graph(nodes=("b", "a"), edges=(("a", "b"),))
    d = g.to_dict()
    assert d["nodes"] == ["a", "b"]
    assert d["edges"] == [["a", "b"]]
    # same content built differently -> identical dict (content-addressed)
    assert Graph(nodes=("a", "b"), edges=(("b", "a"),)).to_dict() == d


def test_frozen_value_equality_and_hashable():
    g1 = Graph(nodes=("a", "b"), edges=(("a", "b"),), directed=True)
    g2 = Graph(nodes=("a", "b"), edges=(("a", "b"),), directed=True)
    assert g1 == g2
    assert hash(g1) == hash(g2)  # frozen + value-stable -> usable as a dict key
