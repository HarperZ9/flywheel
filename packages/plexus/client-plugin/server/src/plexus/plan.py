"""plan.py — turn the mesh into an executable pipeline.

Two questions a user actually asks:
  - "I want to feed tool X — what upstream chain produces its inputs?" -> plan_to
  - "I have tool A's output and want tool B's verdict — how do they connect?" -> route

Both return ordered steps naming each hop's invocation (the declared CLI) plus
the capability that justifies it. A hop is auditable always; it is runnable only
when both ends declare a CLI. When one does not, the hop is marked
`runnable: false` and the absence is named, never coerced into a command.
"""
from __future__ import annotations

from .mesh import Mesh
from .receipt import build_plan_receipt


def _cli(mesh: Mesh, organ: str):
    """The declared CLI for an organ, or None when the manifest declares none.
    Absence is returned honestly, never laundered into the organ id."""
    inv = mesh.manifests[organ].invoke if organ in mesh.manifests else {}
    return inv.get("cli")


def _token(cli, organ: str) -> str:
    return cli if cli else f"{organ}(no cli declared)"


def _toposort(mesh: Mesh, nodes: set) -> tuple:
    """Kahn's algorithm over non-self edges induced on `nodes`. Returns
    (order, cyclic): acyclic prefix in dependency order, then any nodes left in a
    feedback loop (reported, never silently linearized)."""
    edges = [(e.producer, e.consumer) for e in mesh.edges
             if not e.self_loop and e.producer in nodes and e.consumer in nodes
             and e.producer != e.consumer]
    indeg = {n: 0 for n in nodes}
    for _, c in edges:
        indeg[c] += 1
    ready = sorted(n for n in nodes if indeg[n] == 0)
    order = []
    while ready:
        n = ready.pop(0)
        order.append(n)
        for p, c in edges:
            if p == n:
                indeg[c] -= 1
                if indeg[c] == 0:
                    ready.append(c)
        ready.sort()
    cyclic = sorted(n for n in nodes if n not in order)
    return order + cyclic, cyclic


def plan_to(mesh: Mesh, target: str) -> dict:
    """The upstream producers that (transitively) feed `target`, in dependency
    order. Pure sources first; any feedback loop is reported in `cyclic` rather
    than forced into a false linear order."""
    if target not in mesh.manifests:
        return {"target": target, "error": "unknown organ", "order": []}

    upstream, frontier = set(), [target]
    while frontier:
        node = frontier.pop()
        for producer in mesh.producers_of(node):
            if producer != target and producer not in upstream:
                upstream.add(producer)
                frontier.append(producer)
    nodes = upstream | {target}

    order, cyclic = _toposort(mesh, nodes)
    hops = []
    for e in mesh.edges:
        if e.self_loop or e.producer not in nodes or e.consumer not in nodes:
            continue
        p_cli, c_cli = _cli(mesh, e.producer), _cli(mesh, e.consumer)
        hops.append({"producer": e.producer, "consumer": e.consumer,
                     "capability": e.capability,
                     "invoke": f"{_token(p_cli, e.producer)} -> {_token(c_cli, e.consumer)}",
                     "runnable": p_cli is not None and c_cli is not None})
    incoming = {c for _, c in [(e.producer, e.consumer) for e in mesh.edges
                               if not e.self_loop and e.producer in nodes
                               and e.consumer in nodes and e.producer != e.consumer]}
    plan = {"target": target, "order": order, "hops": hops, "cyclic": cyclic,
            "sources": [n for n in order if n not in incoming]}
    plan["receipt"] = build_plan_receipt(mesh, plan)
    return plan


def route(mesh: Mesh, source: str, target: str) -> dict:
    """Shortest capability-path from `source` to `target` (BFS over edges)."""
    if source not in mesh.manifests or target not in mesh.manifests:
        return {"source": source, "target": target, "error": "unknown organ", "path": []}
    # BFS keeping the edge used to reach each node
    prev: dict = {source: None}
    queue = [source]
    while queue:
        node = queue.pop(0)
        if node == target:
            break
        for e in mesh.edges:
            if e.self_loop or e.producer != node or e.consumer in prev:
                continue
            prev[e.consumer] = e
            queue.append(e.consumer)
    if target not in prev:
        out = {"source": source, "target": target, "path": [], "connected": False}
        out["receipt"] = build_plan_receipt(mesh, out)
        return out
    chain = []
    node = target
    while prev[node] is not None:
        e = prev[node]
        chain.append({"producer": e.producer, "consumer": e.consumer,
                      "capability": e.capability})
        node = e.producer
    chain.reverse()
    out = {"source": source, "target": target, "connected": True,
           "hops": len(chain), "path": chain}
    out["receipt"] = build_plan_receipt(mesh, out)
    return out
