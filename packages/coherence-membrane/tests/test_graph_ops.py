"""Tests for graph_ops -- the stdlib re-derivation kernels (determinism + bounds)."""
from __future__ import annotations

from coherence_membrane.graph import Graph
from coherence_membrane.graph_ops import (
    adjacency,
    bfs_shortest_path,
    connected_components,
    de_bruijn_graph,
    reaches,
    transitive_closure,
)
# find_cycle_through and tree_jump_edges moved to graph_search in the 300-line split
# (pure refactor; same kernels, new home).
from coherence_membrane.graph_search import find_cycle_through, tree_jump_edges


def test_adjacency_covers_every_node_including_isolated():
    g = Graph(nodes=("a", "b", "c"), edges=(("a", "b"),), directed=True)
    adj = adjacency(g)
    assert adj == {"a": ("b",), "b": (), "c": ()}


def test_connected_components_partition():
    g = Graph(nodes=("a", "b", "c", "d"), edges=(("a", "b"), ("c", "d")))
    comps = connected_components(g)
    assert comps == (("a", "b"), ("c", "d"))


def test_connected_components_unknown_edge_does_not_connect():
    # a malformed edge carried in unknown_edges must NOT join components.
    g = Graph(nodes=("a", "b"), edges=(("a", "ghost"),))
    assert connected_components(g) == (("a",), ("b",))


def test_bfs_shortest_path_is_shortest_and_deterministic():
    # two equal-length paths a->b->d and a->c->d ; the lexicographically smaller wins
    g = Graph(nodes=("a", "b", "c", "d"),
              edges=(("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")), directed=True)
    assert bfs_shortest_path(g, "a", "d") == ("a", "b", "d")


def test_bfs_no_path_returns_none():
    g = Graph(nodes=("a", "b"), edges=(), directed=True)
    assert bfs_shortest_path(g, "a", "b") is None


def test_bfs_undeclared_endpoint_returns_none():
    g = Graph(nodes=("a",), edges=(), directed=True)
    assert bfs_shortest_path(g, "a", "z") is None


def test_bfs_budget_hit_returns_none_not_false_path():
    g = Graph(nodes=("a", "b", "c"), edges=(("a", "b"), ("b", "c")), directed=True)
    # cap of 1 expansion cannot reach c -> None (no decision), never a wrong path
    assert bfs_shortest_path(g, "a", "c", max_nodes=1) is None


def test_reaches_true_false_and_budget():
    g = Graph(nodes=("a", "b", "c"), edges=(("a", "b"),), directed=True)
    assert reaches(g, "a", "b") is True
    assert reaches(g, "a", "c") is False        # real closure: exhausted, not reachable
    assert reaches(g, "a", "b", max_nodes=0) is None  # budget hit -> UNVERIFIABLE


def test_find_cycle_through_finds_a_real_cycle():
    g = Graph(nodes=("a", "b", "c"),
              edges=(("a", "b"), ("b", "c"), ("c", "a")), directed=True)
    cyc = find_cycle_through(g, "a")
    assert cyc is not None
    assert cyc[0] == cyc[-1] == "a"
    # every consecutive hop is a real edge -> the witness is re-checkable
    assert all(g.has_edge(u, v) for u, v in zip(cyc, cyc[1:]))


def test_find_cycle_through_none_when_acyclic():
    g = Graph(nodes=("a", "b", "c"), edges=(("a", "b"), ("b", "c")), directed=True)
    assert find_cycle_through(g, "a") is None  # DAG -> no cycle (real closure)


def test_find_self_loop_cycle():
    g = Graph(nodes=("a",), edges=(("a", "a"),), directed=True)
    assert find_cycle_through(g, "a") == ("a", "a")


def test_de_bruijn_graph_structure():
    # B(2,2): nodes are length-1 words {0,1}; 4 directed overlap edges.
    g = de_bruijn_graph(("0", "1"), 2)
    assert g.directed
    assert set(g.nodes) == {"0", "1"}
    assert g.edge_count() == 4  # 0->0,0->1,1->0,1->1
    assert g.has_edge("0", "1") and g.has_edge("1", "0")


def test_de_bruijn_is_strongly_connected_so_has_cycle():
    g = de_bruijn_graph(("0", "1"), 3)  # nodes = length-2 words
    # every de Bruijn graph is Eulerian/strongly connected -> a cycle through any node
    assert find_cycle_through(g, "00") is not None


def test_de_bruijn_rejects_bad_order():
    import pytest
    with pytest.raises(ValueError):
        de_bruijn_graph(("0", "1"), 0)
    with pytest.raises(ValueError):
        de_bruijn_graph((), 2)


def test_transitive_closure_membership():
    g = Graph(nodes=("a", "b", "c"), edges=(("a", "b"), ("b", "c")), directed=True)
    tc = transitive_closure(g)
    assert ("a", "b") in tc and ("a", "c") in tc and ("b", "c") in tc
    assert ("c", "a") not in tc  # directed: no reverse reachability


def test_transitive_closure_over_cap_is_none():
    g = Graph(nodes=("a", "b", "c"), edges=(("a", "b"),), directed=True)
    assert transitive_closure(g, max_nodes=2) is None  # over cap -> UNVERIFIABLE


def test_tree_jump_edges_ancestor_chains():
    # tree: r -> a -> b, r -> c
    g = Graph(nodes=("r", "a", "b", "c"),
              edges=(("r", "a"), ("a", "b"), ("r", "c")), directed=True)
    chains = tree_jump_edges(g, "r")
    assert chains["b"] == ("r", "a")  # root-first ancestors of b
    assert chains["a"] == ("r",)
    assert chains["c"] == ("r",)
    assert chains["r"] == ()


def test_tree_jump_edges_rejects_non_tree():
    # a node with two parents (diamond) is NOT a tree -> None (ill-defined chain)
    g = Graph(nodes=("r", "a", "b", "d"),
              edges=(("r", "a"), ("r", "b"), ("a", "d"), ("b", "d")), directed=True)
    assert tree_jump_edges(g, "r") is None


def test_tree_jump_edges_rejects_unreached_node():
    g = Graph(nodes=("r", "a", "island"), edges=(("r", "a"),), directed=True)
    assert tree_jump_edges(g, "r") is None  # 'island' unreachable -> ill-defined


def test_tree_jump_edges_undeclared_root_is_none():
    g = Graph(nodes=("a",), edges=(), directed=True)
    assert tree_jump_edges(g, "zzz") is None
