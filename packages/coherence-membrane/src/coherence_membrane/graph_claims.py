"""graph_claims -- the perceived claim shapes the Graph-plane judges consume.

Split out of graph_oracle (pure refactor; no behaviour change) so the immutable
claim forms live in one small module. graph_oracle re-exports them, so the public
import surface (coherence_membrane.graph_oracle.ReachabilityClaim, etc.) is
unchanged. No third-party imports.
"""
from __future__ import annotations

from dataclasses import dataclass

from .graph import Edge, Graph, Node


@dataclass(frozen=True)
class ReachabilityClaim:
    """`expect_cycle` = does a simple cycle through `label_node` exist in `graph`?
    The de Bruijn reachability property as a checkable claim."""

    graph: Graph
    label_node: Node
    expect_cycle: bool = True
    claim: str = ""


@dataclass(frozen=True)
class BottleneckClaim:
    """A claimed minimax (bottleneck) spanning structure: `spanning` edges span the
    graph and `bottleneck` is the largest weight among them, asserted minimal."""

    graph: Graph
    spanning: tuple[Edge, ...]
    bottleneck: float
    claim: str = ""


@dataclass(frozen=True)
class ClosureClaim:
    """A reachability fact (`src` reaches `dst`) on a tree rooted at `root`, to be
    certified by composing the precomputed ancestor jump-edges."""

    graph: Graph
    root: Node
    src: Node
    dst: Node
    claim: str = ""
