"""graph_ops -- pure stdlib operations over the Graph substrate.

No third-party imports. Every op is deterministic (fixed node/edge ordering from the
Graph substrate's normalisation) and total over a well-formed Graph; none mutate
their input. These are the re-derivation kernels the Graph criteria call to build
and re-check witnesses -- kept separate from the criteria so a third party can re-run
a single op against a witness in isolation: adjacency, connected components, BFS
shortest-path/reachability, de Bruijn construction, and serial transitive closure.
The search + connectivity kernels (the cycle finder, tree jump-edges, and the
spanning/cut bottleneck kernels) live in graph_search, which builds on these.
"""
from __future__ import annotations

from collections import deque
from itertools import product
from typing import Optional

from .graph import Edge, Graph, Node


def adjacency(g: Graph) -> dict[Node, tuple[Node, ...]]:
    """Out-adjacency map: node -> sorted out-neighbours, for EVERY declared node
    (isolated nodes map to ()). Deterministic; honours directedness via
    Graph.neighbors."""
    return {n: g.neighbors(n) for n in g.nodes}


def connected_components(g: Graph) -> tuple[tuple[Node, ...], ...]:
    """Weakly-connected components (edges traversed ignoring direction), each a
    sorted node tuple; the components themselves are returned in sorted order. A
    deterministic partition of the declared nodes -- unknown edges do NOT connect
    anything (they are not real adjacency)."""
    # undirected reachability: build a symmetric adjacency over real edges only.
    adj: dict[Node, set[Node]] = {n: set() for n in g.nodes}
    for u, v in g.edges:
        adj[u].add(v)
        adj[v].add(u)
    seen: set[Node] = set()
    comps: list[tuple[Node, ...]] = []
    for start in g.nodes:  # g.nodes is already sorted -> deterministic component order
        if start in seen:
            continue
        stack = [start]
        comp: set[Node] = set()
        while stack:
            x = stack.pop()
            if x in comp:
                continue
            comp.add(x)
            seen.add(x)
            stack.extend(adj[x] - comp)
        comps.append(tuple(sorted(comp)))
    return tuple(sorted(comps))


def bfs_shortest_path(g: Graph, src, dst, *, max_nodes: Optional[int] = None) -> Optional[tuple[Node, ...]]:
    """A shortest (fewest-edges) path src..dst as a node tuple, or None if none / a
    bound was hit / an endpoint is undeclared. Deterministic: neighbours are visited
    in sorted order, so among equal-length paths the lexicographically smallest is
    returned. `max_nodes` caps how many nodes may be expanded (bounded search);
    returning None on the cap means "no decision within budget", never a false path.
    """
    from .graph import _norm_node

    s, t = _norm_node(src), _norm_node(dst)
    node_set = set(g.nodes)
    if s not in node_set or t not in node_set:
        return None
    if s == t:
        return (s,)
    adj = adjacency(g)
    prev: dict[Node, Node] = {s: s}
    q: deque[Node] = deque([s])
    expanded = 0
    while q:
        x = q.popleft()
        expanded += 1
        if max_nodes is not None and expanded > max_nodes:
            return None
        for nbr in adj[x]:  # already sorted
            if nbr in prev:
                continue
            prev[nbr] = x
            if nbr == t:
                # reconstruct
                path = [t]
                while path[-1] != s:
                    path.append(prev[path[-1]])
                return tuple(reversed(path))
            q.append(nbr)
    return None


def reaches(g: Graph, src, dst, *, max_nodes: Optional[int] = None) -> Optional[bool]:
    """True/False if `dst` is reachable from `src` within budget; None if a bound was
    hit (UNVERIFIABLE) or an endpoint is undeclared. False is a real closure result
    (the BFS exhausted reachable nodes without hitting the cap)."""
    from .graph import _norm_node

    s, t = _norm_node(src), _norm_node(dst)
    node_set = set(g.nodes)
    if s not in node_set or t not in node_set:
        return None
    if s == t:
        return True
    adj = adjacency(g)
    seen = {s}
    q: deque[Node] = deque([s])
    expanded = 0
    while q:
        x = q.popleft()
        expanded += 1
        if max_nodes is not None and expanded > max_nodes:
            return None  # budget exhausted -> no decision, never a false False
        for nbr in adj[x]:
            if nbr == t:
                return True
            if nbr not in seen:
                seen.add(nbr)
                q.append(nbr)
    return False


# --- de Bruijn construction ---------------------------------------------------


def de_bruijn_graph(symbols, n: int) -> Graph:
    """The de Bruijn graph B(k, n): nodes are length-(n-1) words over `symbols`,
    a directed edge w -> w' iff w[1:] == w'[:-1] (overlap by n-1 chars). Used to turn
    a recurrence/transition claim over an alphabet into a reachability question (the
    'Prescribing the Death of a CA' construction). n>=1; n==1 yields the single empty
    node with a self-loop per symbol. Deterministic node/edge order via the Graph
    substrate. Symbols are coerced to single-char strings; raises ValueError on n<1.
    """
    if n < 1:
        raise ValueError("de Bruijn order n must be >= 1")
    syms = [str(s) for s in symbols]
    if not syms:
        raise ValueError("de Bruijn needs at least one symbol")
    k = n - 1
    nodes = ["".join(t) for t in product(syms, repeat=k)]  # length-(n-1) words
    edges: list[Edge] = [(w, (w + s)[1:] if k > 0 else "")  # overlap-by-(n-1) successor
                         for w in nodes for s in syms]
    return Graph(nodes=tuple(nodes), edges=tuple(edges), directed=True)


# --- serial transitive closure (composable jump-edges) ------------------------


def transitive_closure(g: Graph, *, max_nodes: Optional[int] = None) -> Optional[frozenset[tuple[Node, Node]]]:
    """Serial transitive closure: the set of all (a, b) with b reachable from a
    (a != b), honouring directedness. Returns None if the graph exceeds `max_nodes`
    (the closure is O(V*(V+E)); past the cap it is UNVERIFIABLE-in-practice, not
    silently truncated). This is the precompute behind composable reachability
    certificates: any reachability fact is then ONE membership test. Deterministic
    (the result is a set; iteration order is irrelevant to membership)."""
    if max_nodes is not None and g.node_count() > max_nodes:
        return None
    adj = adjacency(g)
    closure: set[tuple[Node, Node]] = set()
    for s in g.nodes:
        # BFS from s over real edges
        seen = {s}
        q: deque[Node] = deque([s])
        while q:
            x = q.popleft()
            for nbr in adj[x]:
                if nbr not in seen:
                    seen.add(nbr)
                    q.append(nbr)
        for b in seen:
            if b != s:
                closure.add((s, b))
    return frozenset(closure)
