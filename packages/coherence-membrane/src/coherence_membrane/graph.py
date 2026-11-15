"""Graph -- the L0 relational primitive (nodes + directed/undirected edges).

The deferred third L0 IR primitive alongside Field and Geometry. A Graph is a
frozen, value-stable bundle of nodes and edges in one relational space. Like
Geometry, UNVERIFIABLE is first-class: a Graph carries the nodes/edges whose
membership or structure could NOT be determined (e.g. an edge naming a node that
was never declared) in `unknown_nodes` / `unknown_edges`, so downstream ops report
incompleteness rather than silently drop a malformed relation.

Determinism is a substrate invariant, not an op concern: `nodes`, `edges`, and the
unknown sets are normalised to fixed, sorted order in `__post_init__`, so two graphs
built from the same content compare equal and serialise identically. An undirected
graph stores each edge with its endpoints sorted (u <= v) and rejects directed self-
asymmetry by construction; a directed graph preserves (src, dst) orientation.

Edges are `(u, v)` for unweighted, or carry an optional weight and label via the
parallel `weights` / `labels` maps keyed by the canonical edge tuple. Stdlib only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# An edge is a 2-tuple of node ids (strings). Weights/labels are side maps keyed by
# the canonical edge tuple (already endpoint-sorted for undirected graphs), so the
# core edge set stays a plain comparable tuple-of-pairs.
Node = str
Edge = tuple[str, str]


def _norm_node(n: object) -> Node:
    """A node id is its string form. Coercing here (not raising) keeps construction
    total; an int 3 and the str '3' are the SAME node, deterministically."""
    return str(n)


@dataclass(frozen=True)
class Graph:
    """A frozen relational structure: nodes + edges, UNVERIFIABLE-carrying.

    nodes         -- the declared node ids (sorted, de-duplicated).
    edges         -- (u, v) pairs over declared nodes (sorted; for an undirected
                    graph each pair is stored endpoint-sorted u <= v).
    directed      -- orientation of every edge in `edges`.
    weights       -- optional edge -> weight (float); keyed by the canonical edge.
    labels        -- optional edge -> label (str); keyed by the canonical edge.
    unknown_nodes -- node ids referenced but not resolvable (carried, never dropped).
    unknown_edges -- edges referencing an undeclared endpoint (carried, never dropped).

    All five collections are normalised to deterministic order in __post_init__, so
    equality and serialisation are content-addressed: same content -> same Graph.
    """

    nodes: tuple[Node, ...] = ()
    edges: tuple[Edge, ...] = ()
    directed: bool = False
    weights: tuple[tuple[Edge, float], ...] = ()
    labels: tuple[tuple[Edge, str], ...] = ()
    unknown_nodes: tuple[Node, ...] = ()
    unknown_edges: tuple[Edge, ...] = ()

    def __post_init__(self) -> None:
        node_set = {_norm_node(n) for n in self.nodes}
        # Canonicalise each edge: coerce endpoints to node ids; for an undirected
        # graph store endpoints sorted so (a,b) and (b,a) are the SAME edge.
        canon_edges: list[Edge] = []
        unknown: set[Edge] = {self._canon(e) for e in self.unknown_edges}
        for e in self.edges:
            ce = self._canon(e)
            if ce[0] not in node_set or ce[1] not in node_set:
                # An edge to an undeclared endpoint is UNVERIFIABLE structure: carried,
                # never silently added as if its endpoints existed.
                unknown.add(ce)
            else:
                canon_edges.append(ce)
        # de-dup + deterministic order on every collection
        object.__setattr__(self, "nodes", tuple(sorted(node_set)))
        object.__setattr__(self, "edges", tuple(sorted(set(canon_edges))))
        object.__setattr__(self, "unknown_edges", tuple(sorted(unknown)))
        object.__setattr__(
            self, "unknown_nodes",
            tuple(sorted({_norm_node(n) for n in self.unknown_nodes})),
        )
        # weight/label maps: canonicalise keys, keep only those on a real edge, sort.
        real = set(self.edges)
        w = {self._canon(k): float(v) for k, v in self.weights if self._canon(k) in real}
        lab = {self._canon(k): str(v) for k, v in self.labels if self._canon(k) in real}
        object.__setattr__(self, "weights", tuple(sorted(w.items())))
        object.__setattr__(self, "labels", tuple(sorted(lab.items())))

    def _canon(self, e) -> Edge:
        u, v = _norm_node(e[0]), _norm_node(e[1])
        if not self.directed and v < u:
            u, v = v, u
        return (u, v)

    # --- house-style helpers --------------------------------------------------

    def node_count(self) -> int:
        return len(self.nodes)

    def edge_count(self) -> int:
        return len(self.edges)

    def is_empty(self) -> bool:
        """True only when there is no content at all -- no nodes, edges, OR unknown
        markers. UNVERIFIABLE markers are first-class content (a graph with only
        unknown edges is not 'empty'), consistent with Geometry.is_empty."""
        return not (self.nodes or self.edges or self.unknown_nodes or self.unknown_edges)

    def has_unknown(self) -> bool:
        """True if any node/edge could not be resolved -- the substrate-level
        UNVERIFIABLE signal an op or criterion must honour (never read past it)."""
        return bool(self.unknown_nodes or self.unknown_edges)

    def neighbors(self, node) -> tuple[Node, ...]:
        """Out-neighbours of `node` in deterministic order. For an undirected graph
        every incident edge contributes its other endpoint. Returns () for an
        unknown/declared-but-isolated node alike -- the caller distinguishes via
        `node in self.nodes`."""
        n = _norm_node(node)
        out: set[Node] = set()
        for u, v in self.edges:
            if u == n:
                out.add(v)
            elif not self.directed and v == n:
                out.add(u)
        return tuple(sorted(out))

    def weight(self, u, v) -> Optional[float]:
        """Weight of edge (u, v), or None if the edge is absent/unweighted."""
        key = self._canon((u, v))
        for k, w in self.weights:
            if k == key:
                return w
        return None

    def has_edge(self, u, v) -> bool:
        return self._canon((u, v)) in set(self.edges)

    def to_dict(self) -> dict:
        return {
            "nodes": list(self.nodes),
            "edges": [list(e) for e in self.edges],
            "directed": self.directed,
            "weights": [[list(k), v] for k, v in self.weights],
            "labels": [[list(k), v] for k, v in self.labels],
            "unknown_nodes": list(self.unknown_nodes),
            "unknown_edges": [list(e) for e in self.unknown_edges],
        }
