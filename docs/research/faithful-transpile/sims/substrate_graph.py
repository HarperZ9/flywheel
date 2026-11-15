"""Substrate 5 — discrete structure: a graph compressed to a spanning forest.

A discrete-structure substrate-kind (no numbers-on-a-line, no pixels). Transform T = keep only a
spanning forest (drop every non-tree edge) — massive edge-loss. Three criteria (readouts) of the graph:
  phi_conn(u,v): are u,v in the same connected component?   (preserved EXACTLY by a spanning forest)
  phi_dist(u,v): is dist(u,v) <= 2?                          (distorted — forest paths lengthen)
  phi_tri(u)   : is u in a triangle?                         (destroyed — forests have no cycles)
Same transform; faithful to connectivity, lossy to distance and triangles -> criterion-relativity.
Internal stat (the forest's edge count / degree) cannot say which query survived; only comparison to
the original (external) can.

Stdlib only, seeded, deterministic.
"""
from __future__ import annotations
import random
from collections import deque

N_NODES, P_EDGE, TRIALS = 60, 0.08, 20


def gen_graph(seed):
    rng = random.Random(seed)
    adj = {i: set() for i in range(N_NODES)}
    for i in range(N_NODES):
        for j in range(i + 1, N_NODES):
            if rng.random() < P_EDGE:
                adj[i].add(j); adj[j].add(i)
    return adj


def spanning_forest(adj):
    """Keep only BFS-tree edges per component — drops all non-tree (cycle) edges."""
    seen = set()
    fadj = {i: set() for i in adj}
    for s in adj:
        if s in seen:
            continue
        seen.add(s); q = deque([s])
        while q:
            u = q.popleft()
            for v in adj[u]:
                if v not in seen:
                    seen.add(v); fadj[u].add(v); fadj[v].add(u); q.append(v)
    return fadj


def component_of(adj):
    comp = {}; c = 0
    for s in adj:
        if s in comp:
            continue
        comp[s] = c; q = deque([s])
        while q:
            u = q.popleft()
            for v in adj[u]:
                if v not in comp:
                    comp[v] = c; q.append(v)
        c += 1
    return comp


def dist_leq(adj, u, v, k=2):
    if u == v:
        return True
    seen = {u}; q = deque([(u, 0)])
    while q:
        x, d = q.popleft()
        if d >= k:
            continue
        for y in adj[x]:
            if y == v:
                return True
            if y not in seen:
                seen.add(y); q.append((y, d + 1))
    return False


def in_triangle(adj, u):
    nb = list(adj[u])
    return any(b in adj[a] for i, a in enumerate(nb) for b in nb[i + 1:])


def edges(adj):
    return sum(len(s) for s in adj.values()) // 2


def main():
    rng = random.Random(1)
    conn = dist = tri = 0.0
    el_orig = el_forest = 0
    for t in range(TRIALS):
        g = gen_graph(100 + t)
        f = spanning_forest(g)
        el_orig += edges(g); el_forest += edges(f)
        co, cf = component_of(g), component_of(f)
        pairs = [(rng.randrange(N_NODES), rng.randrange(N_NODES)) for _ in range(40)]
        conn += sum(1 for u, v in pairs if (co[u] == co[v]) == (cf[u] == cf[v])) / len(pairs)
        dist += sum(1 for u, v in pairs if dist_leq(g, u, v) == dist_leq(f, u, v)) / len(pairs)
        nodes = [rng.randrange(N_NODES) for _ in range(40)]
        tri += sum(1 for u in nodes if in_triangle(g, u) == in_triangle(f, u)) / len(nodes)
    conn /= TRIALS; dist /= TRIALS; tri /= TRIALS
    bitloss = 1 - el_forest / el_orig

    print(f"graph n={N_NODES}, ~{el_orig//TRIALS} edges -> spanning forest ~{el_forest//TRIALS} edges "
          f"({bitloss:.0%} of edges dropped)\n")
    print("criterion (readout)        survival under the forest transform")
    print(f"  phi_conn  same-component   {conn:.3f}")
    print(f"  phi_dist  dist<=2          {dist:.3f}")
    print(f"  phi_tri   in-triangle      {tri:.3f}")

    print("\n--- verdict (substrate 5: graph -> spanning forest) ---")
    p1 = conn > 0.99                      # connectivity conserved despite ~majority edge loss
    p3 = (conn - dist) > 0.1 and (conn - tri) > 0.1   # same transform, lossy to other criteria
    print(f"(1) lossy-but-faithful: {bitloss:.0%} of edges dropped yet phi_conn survival {conn:.3f}"
          f"  -> {'HOLDS' if p1 else 'FALLS'}")
    print(f"(3) criterion-relativity: same transform faithful to connectivity ({conn:.3f}) but lossy to "
          f"dist ({dist:.3f}) and triangle ({tri:.3f})  -> {'HOLDS' if p3 else 'FALLS'}")
    print("\nSTICKS" if (p1 and p3) else "\nFALLS", "— substrate 5 (discrete structure).")


if __name__ == "__main__":
    main()
