"""fluid_router.py — springloaded flow: store the potential once, release fluid cheaply.

"A system efficient enough to springload the organic fluidity of fluid dynamics"
has a computable core, and it is two mechanisms this project already runs, joined:

  SPRINGLOAD = amortization (the flywheel). Relax a potential field ONCE (O(cells)),
    then every flow is a cheap gradient-follow (O(path)). Pay the spring once, release
    many times — 1/(1-r) in the flow domain.
  FLUIDITY   = mass conservation + least-resistance routing (the criterion, physical).
    Flow follows steepest descent of the potential, routing around obstacles the way
    water finds the gap, and every injected unit reaches the sink (continuity: in==out).

The load-bearing asymmetry (same shape as externalization): a properly RELAXED
potential has no spurious interior minima, so flow never leaks — conserved. A
plausible SELF-AUTHORED heuristic (straight-line/Euclidean-to-sink) creates local
minima behind concave obstacles, where flow gets stuck and mass LEAKS. The
self-authored field looks right and loses fluid; the relaxed criterion conserves it.

HONEST bounds (stated, not buried): this is a discrete potential-flow relaxation
(navigation-function / value-iteration), NOT Navier-Stokes. It conserves MASS, not
momentum; there is no viscosity, turbulence, pressure, or compressibility. "Organic
routing around obstacles" is real; "fluid dynamics" it is not. And the spring is only
valid while topology is fixed — blocking a cell invalidates the field and it must be
reloaded (adaptation costs a reload, it is not free). Not a new algorithm (Dijkstra +
navigation functions are textbook); the contribution is the composition and the
conserved-vs-leaky-field asymmetry made measurable.
"""
from __future__ import annotations

import heapq
import math
from collections import Counter
from dataclasses import dataclass

INF = float("inf")


@dataclass
class Grid:
    w: int
    h: int
    sink: tuple
    blocked: frozenset = frozenset()

    def passable(self, c) -> bool:
        x, y = c
        return 0 <= x < self.w and 0 <= y < self.h and c not in self.blocked

    def neighbors(self, c):
        x, y = c
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if self.passable(n):
                yield n


def cells(grid: Grid) -> list:
    return [(x, y) for x in range(grid.w) for y in range(grid.h)
            if (x, y) not in grid.blocked]


def springload(grid: Grid) -> dict:
    """Relax the potential: min-resistance distance from every cell to the sink
    (Dijkstra from the sink). The loaded spring — computed ONCE."""
    phi = {c: INF for c in cells(grid)}
    if not grid.passable(grid.sink):
        return phi
    phi[grid.sink] = 0.0
    pq = [(0.0, grid.sink)]
    while pq:
        d, c = heapq.heappop(pq)
        if d > phi[c]:
            continue
        for n in grid.neighbors(c):
            nd = d + 1.0
            if nd < phi[n]:
                phi[n] = nd
                heapq.heappush(pq, (nd, n))
    return phi


def euclidean_field(grid: Grid) -> dict:
    """A plausible SELF-AUTHORED potential: straight-line distance to the sink. Looks
    right, ignores obstacles -> spurious local minima behind concave walls."""
    sx, sy = grid.sink
    return {(x, y): math.hypot(x - sx, y - sy) for (x, y) in cells(grid)}


def flow_path(grid: Grid, phi: dict, source, max_steps: int | None = None) -> dict:
    """Release: follow steepest descent of phi from source to sink. O(path), no
    recompute. Leaks (mass lost) if it hits a non-sink local minimum."""
    max_steps = max_steps or (grid.w * grid.h + 1)
    cur = source
    path = [cur]
    if phi.get(cur, INF) == INF:
        return {"path": path, "reached_sink": False, "leaked": True}
    for _ in range(max_steps):
        if cur == grid.sink:
            return {"path": path, "reached_sink": True, "leaked": False}
        nbrs = list(grid.neighbors(cur))
        best = min(nbrs, key=lambda n: (phi.get(n, INF), n)) if nbrs else None
        if best is None or phi.get(best, INF) >= phi.get(cur, INF):
            return {"path": path, "reached_sink": False, "leaked": True}   # local min
        cur = best
        path.append(cur)
    return {"path": path, "reached_sink": cur == grid.sink, "leaked": cur != grid.sink}


def conservation(grid: Grid, phi: dict, sources: list) -> dict:
    """Mass conservation: inject one unit per source, absorb at the sink. Conserved iff
    every unit reaches the sink (nothing leaks at a spurious minimum) AND global
    balance holds (injected == absorbed)."""
    paths = [flow_path(grid, phi, s) for s in sources]
    reached = sum(1 for p in paths if p["reached_sink"])
    # interior continuity: at every non-source, non-sink node inflow == outflow
    inflow, outflow = Counter(), Counter()
    for p in paths:
        for a, b in zip(p["path"], p["path"][1:]):
            outflow[a] += 1
            inflow[b] += 1
    src = Counter(sources)
    interior_ok = all(
        inflow[c] + src[c] == outflow[c] or c == grid.sink
        for c in set(inflow) | set(outflow) | set(src) if c != grid.sink)
    return {"injected": len(sources), "absorbed_at_sink": reached,
            "leaked": len(sources) - reached, "conserved": reached == len(sources),
            "interior_continuity": interior_ok}


def springload_amortization(grid: Grid, sources: list) -> dict:
    """The springload payoff: N queries share ONE loaded field. Cost model — springload
    = |cells| relax ops (once); each release = path length (cheap). Passive = a full
    search per query = N * |cells|."""
    phi = springload(grid)
    n_cells = len(cells(grid))
    release = sum(len(flow_path(grid, phi, s)["path"]) for s in sources)
    springloaded = n_cells + release
    passive = len(sources) * n_cells
    return {"n_queries": len(sources), "cells": n_cells,
            "springloaded_cost": springloaded, "passive_cost": passive,
            "speedup": round(passive / max(springloaded, 1), 2),
            "amortized": springloaded < passive}
