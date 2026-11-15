"""graph_search -- search, connectivity, and the bottleneck-certificate kernels.

Split out of graph_ops (pure refactor; no behaviour change) so the search and
connectivity re-derivation kernels live beside one another and a third party can
re-run a single one against a witness in isolation: the de Bruijn cycle finder,
the serial-transitive-closure tree jump-edges, and the spanning/cut kernels the
bottleneck certificate re-checks (union-find `spans` AND the genuinely disjoint
BFS decider `connects_all`, kept apart on purpose so neither hides the other's
bug). No third-party imports; deterministic; none mutate their input.
"""
from __future__ import annotations

from collections import deque
from typing import Optional

from .graph import Graph, Node, _norm_node
from .graph_ops import adjacency, bfs_shortest_path


def find_cycle_through(g: Graph, label_node, *, max_nodes: Optional[int] = None) -> Optional[tuple[Node, ...]]:
    """A simple directed cycle passing through `label_node`, returned as a node tuple
    [label_node, ..., label_node] (first == last), or None if none exists / a bound
    was hit / the node is undeclared. The de Bruijn reachability kernel: a cycle
    through the labelled state witnesses the recurring-property claim. Deterministic
    (sorted neighbours -> the lexicographically-smallest shortest return path). None
    on the cap is UNVERIFIABLE, never a fabricated cycle."""
    n = _norm_node(label_node)
    if n not in set(g.nodes):
        return None
    adj = adjacency(g)
    # A cycle through n = an edge n->first, then a shortest path first..n not reusing
    # the closing edge. Search each out-neighbour deterministically.
    best: Optional[tuple[Node, ...]] = None
    for first in adj[n]:
        if first == n:  # a self-loop is the shortest cycle through n
            return (n, n)
        # shortest path first..n in the full graph (bounded)
        sub = bfs_shortest_path(g, first, n, max_nodes=max_nodes)
        if sub is None:
            continue
        cycle = (n,) + sub  # n -> first -> ... -> n
        if best is None or len(cycle) < len(best) or (len(cycle) == len(best) and cycle < best):
            best = cycle
    return best


def tree_jump_edges(g: Graph, root, *, max_nodes: Optional[int] = None) -> Optional[dict[Node, tuple[Node, ...]]]:
    """For a tree rooted at `root` (directed away from root, or undirected acyclic),
    the ancestor chain of every node: node -> (root..parent) in root-first order. The
    'serial transitive closure on a tree' precompute -- a node's reachability-from is
    EXACTLY its ancestor set, so any reachability certificate is one composition of
    these jump-edges. Returns None over the cap, or None if the structure is not a
    tree reachable from root (a cycle / unreached node makes the ancestor chain
    ill-defined -> UNVERIFIABLE, never a wrong chain)."""
    r = _norm_node(root)
    if r not in set(g.nodes):
        return None
    if max_nodes is not None and g.node_count() > max_nodes:
        return None
    adj = adjacency(g)
    parent: dict[Node, Node] = {r: r}
    order: list[Node] = [r]
    q: deque[Node] = deque([r])
    while q:
        x = q.popleft()
        for nbr in adj[x]:
            if nbr in parent:
                if parent[x] == nbr or nbr == r:
                    continue
                # nbr already has a parent and it's not x's link back -> not a tree
                return None
            parent[nbr] = x
            order.append(nbr)
            q.append(nbr)
    if len(parent) != g.node_count():
        return None  # some node unreachable from root -> ancestor chain ill-defined
    chains: dict[Node, tuple[Node, ...]] = {}
    for node in order:
        chain: list[Node] = []
        cur = node
        while cur != r:
            cur = parent[cur]
            chain.append(cur)
        chains[node] = tuple(reversed(chain))  # root-first ancestors (excludes node)
    return chains


# --- spanning + cut (the bottleneck-certificate kernels) ----------------------


def spans(nodes: tuple[Node, ...], edges) -> Optional[dict]:
    """Union-find: return the parent map iff `edges` connect ALL `nodes` into one
    component, else None. O(E * inverse-Ackermann). Edges naming a node outside
    `nodes` are skipped (they cannot connect declared nodes). The re-check kernel for
    a bottleneck certificate's spanning + minimality (cut) conditions."""
    parent = {n: n for n in nodes}

    def find(x):
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:  # path compression
            parent[x], x = root, parent[x]
        return root

    for u, v in edges:
        if u not in parent or v not in parent:
            continue
        ru, rv = find(u), find(v)
        if ru != rv:
            parent[ru] = rv
    if not nodes:
        return None
    roots = {find(n) for n in nodes}
    return parent if len(roots) == 1 else None


def connects_all(nodes: tuple[Node, ...], edges) -> bool:
    """A SECOND, independent connectivity decider: True iff `edges` connect ALL `nodes`
    into one component, by BFS-reachability over the edge set -- DISJOINT from the
    union-find `spans()` (no shared helper, no shared kernel). Edges naming a node
    outside `nodes` are skipped (they cannot connect declared nodes); empty `nodes` is
    False (no single component to span).

    Why a duplicate of `spans()`'s connectivity question on a different algorithm: the
    bottleneck certificate's load-bearing connectivity checks (is the claim spanning?
    do sub-bottleneck edges disconnect?) must not both flow through ONE kernel, or a
    bug in that kernel is a latent false VERIFIED the re-checker cannot see. Two
    algorithms that AGREE shrink the trusted base to 'they are not both wrong the same
    way' (cf. crosscheck.py); a disagreement is a caught bug (UNVERIFIABLE), never a
    guess. Builds its own adjacency inline on purpose so it shares NO code path with
    union-find. Deterministic; never mutates input."""
    if not nodes:
        return False
    # own adjacency over real edges only -- built here, NOT via adjacency()/cut_sides,
    # so this decider is genuinely disjoint from every other connectivity helper.
    adj: dict[Node, set[Node]] = {n: set() for n in nodes}
    node_set = set(nodes)
    for u, v in edges:
        if u in node_set and v in node_set:
            adj[u].add(v)
            adj[v].add(u)  # connectivity is undirected (same notion spans() decides)
    start = nodes[0]
    seen: set[Node] = {start}
    q: deque[Node] = deque([start])
    while q:
        x = q.popleft()
        for nbr in adj[x]:
            if nbr not in seen:
                seen.add(nbr)
                q.append(nbr)
    return len(seen) == len(node_set)


def cut_sides(nodes: tuple[Node, ...], edges) -> tuple[set, set]:
    """Partition `nodes` into the component containing the smallest node (under
    `edges`) and the rest -- the cut a sub-bottleneck edge set fails to bridge, carried
    as a bottleneck-minimality witness. Deterministic (nodes are sorted)."""
    adj: dict[Node, set] = {n: set() for n in nodes}
    for u, v in edges:
        if u in adj and v in adj:
            adj[u].add(v)
            adj[v].add(u)
    start = nodes[0]
    seen = {start}
    stack = [start]
    while stack:
        x = stack.pop()
        for nbr in adj[x]:
            if nbr not in seen:
                seen.add(nbr)
                stack.append(nbr)
    return seen, set(nodes) - seen
