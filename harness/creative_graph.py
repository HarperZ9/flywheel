"""creative_graph.py: the creative line grows branches.

A graph is nodes and edges: sources start branches (plate, wireframe,
harmonograph), transforms bend one input (the lane's dither and
pixel-sort, the film treatment), and merges join two (blend, beside,
difference, multiply). Images flow along the edges; every node's receipt
hash folds the chains of its inputs into its own, so the graph is a
Merkle DAG of creative work: the id of any node witnesses its entire
upstream subtree, and the graph id witnesses everything. Reorder, reseed,
or swap any upstream node and every id downstream of it moves. No node
runs unwitnessed; a cycle, a dangling edge, or a wrong arity is a named
refusal, never a shrug.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json

from .creative_pipeline import _OPS as _LINE_OPS
from .creative_pipeline import SOURCES

SCHEMA = "flywheel.creative-graph/v1"
MAX_NODES = 24

MERGES = ("blend", "beside", "difference", "multiply")
TRANSFORMS = ("dither", "pixel_sort", "film_frame")


def _fit(a, b):
    """Merges want same-size inputs; the second resizes to the first."""
    if a.size != b.size:
        b = b.resize(a.size)
    return b


def _merge(op, a, b, args):
    from PIL import Image, ImageChops
    b = _fit(a, b)
    if op == "blend":
        alpha = max(0.0, min(1.0, float(args.get("alpha", 0.5))))
        return Image.blend(a, b, alpha), {"op": "blend", "alpha": alpha}
    if op == "beside":
        out = Image.new("RGB", (a.width + b.width, a.height))
        out.paste(a, (0, 0))
        out.paste(b, (a.width, 0))
        return out, {"op": "beside"}
    if op == "difference":
        return ImageChops.difference(a, b), {"op": "difference"}
    if op == "multiply":
        return ImageChops.multiply(a, b), {"op": "multiply"}
    raise ValueError(f"unknown merge {op!r}")


def run_graph(nodes: list, edges: list) -> dict:
    """Nodes + edges in, every sink's image out, one Merkle-DAG receipt."""
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        return {"refused": True,
                "refusals": ["the graph needs Pillow on the engine side"]}
    if not isinstance(nodes, list) or not nodes:
        return {"refused": True, "refusals": ["give the graph at least one "
                                              "node"]}
    if len(nodes) > MAX_NODES:
        return {"refused": True,
                "refusals": [f"more than {MAX_NODES} nodes is a workflow, "
                             "not a graph"]}

    byid: dict = {}
    for n in nodes:
        nid = str((n or {}).get("id", "")).strip()
        op = str((n or {}).get("op", "")).strip()
        if not nid:
            return {"refused": True, "refusals": ["every node needs an id"]}
        if nid in byid:
            return {"refused": True,
                    "refusals": [f"duplicate node id {nid!r}"]}
        if op not in SOURCES and op not in TRANSFORMS and op not in MERGES:
            return {"refused": True,
                    "refusals": [f"node {nid!r}: unknown op {op!r}; ops: "
                                 + ", ".join([*SOURCES, *TRANSFORMS,
                                              *MERGES])]}
        byid[nid] = {"id": nid, "op": op,
                     "args": n.get("args")
                     if isinstance(n.get("args"), dict) else {}}

    inputs: dict = {nid: [] for nid in byid}
    for e in (edges or []):
        src = str((e or {}).get("from", "")).strip()
        dst = str((e or {}).get("to", "")).strip()
        if src not in byid or dst not in byid:
            return {"refused": True,
                    "refusals": [f"edge {src!r} -> {dst!r} names a node "
                                 "that does not exist"]}
        inputs[dst].append(src)

    # arity: sources take none, transforms one, merges two (order matters)
    for nid, node in byid.items():
        need = 0 if node["op"] in SOURCES else 2 if node["op"] in MERGES else 1
        if len(inputs[nid]) != need:
            return {"refused": True,
                    "refusals": [f"node {nid!r} ({node['op']}) takes {need} "
                                 f"input(s), got {len(inputs[nid])}"]}

    # topological order; a cycle is a named refusal
    order, seen, visiting = [], set(), set()

    def visit(nid):
        if nid in seen:
            return True
        if nid in visiting:
            return False
        visiting.add(nid)
        for up in inputs[nid]:
            if not visit(up):
                return False
        visiting.discard(nid)
        seen.add(nid)
        order.append(nid)
        return True

    for nid in byid:
        if not visit(nid):
            return {"refused": True,
                    "refusals": ["the graph has a cycle; a creative line "
                                 "flows forward only"]}

    images: dict = {}
    chains: dict = {}
    trail = []
    for nid in order:
        node = byid[nid]
        op, args = node["op"], node["args"]
        try:
            if op in SOURCES:
                img, receipt = _LINE_OPS[op](args)
            elif op in TRANSFORMS:
                img, receipt = _LINE_OPS[op](images[inputs[nid][0]], args)
            else:
                a, b = (images[inputs[nid][0]], images[inputs[nid][1]])
                img, receipt = _merge(op, a, b, args)
        except (ValueError, OSError, KeyError) as e:
            return {"refused": True,
                    "refusals": [f"node {nid!r} ({op}): {e}"]}
        images[nid] = img
        node_sha = hashlib.sha256(
            json.dumps(receipt, sort_keys=True).encode()).hexdigest()
        upstream = sorted(chains[u] for u in inputs[nid])
        chains[nid] = hashlib.sha256(
            (":".join([*upstream, node_sha])).encode()).hexdigest()
        trail.append({"id": nid, **receipt, "node_sha256": node_sha,
                      "chain": chains[nid][:16],
                      "inputs": list(inputs[nid])})

    # sinks: nodes nothing consumes; their images are the graph's outputs
    consumed = {u for ins in inputs.values() for u in ins}
    sinks = [nid for nid in order if nid not in consumed]
    graph_id = hashlib.sha256(
        (":".join(sorted(chains[s] for s in sinks))).encode()).hexdigest()[:16]

    outputs = {}
    for s in sinks:
        buf = io.BytesIO()
        images[s].convert("RGB").save(buf, "PNG")
        outputs[s] = base64.b64encode(buf.getvalue()).decode("ascii")

    return {"refused": False, "refusals": [],
            "outputs": outputs,
            "receipt": {"schema": SCHEMA,
                        "n_nodes": len(order),
                        "sinks": sinks,
                        "nodes": trail,
                        "graph_id": graph_id,
                        "note": "every node's chain folds its inputs' "
                                "chains, so any id witnesses its whole "
                                "upstream subtree and the graph id "
                                "witnesses everything"}}
