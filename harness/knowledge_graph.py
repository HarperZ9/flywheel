"""knowledge_graph.py -- one graph over every surface, with priced context.

The index lane's niche made concrete on the gateway: a single typed graph a
person, a model, and the desktop all read the same way. Nodes are the live
surfaces (lanes, projects with their index summaries, memory, plugins,
workflows); every node carries `signals` (the named, mechanical inputs) and a
`priority` computed ONLY from those signals -- no vibes, and the arithmetic is
re-checkable from the payload itself.

Context prioritization is the point: `context_plan(nodes, budget)` returns
the deterministic greedy order that fits a context budget, with the excluded
count visible. That is memory management a model can trust: what enters the
window is ranked by measured liveness, salience, and recency, and what was
cut is counted, never silently dropped.

A surface that cannot be read becomes an `error` node. The graph never
pretends a blind spot is an empty region.
"""
from __future__ import annotations

SCHEMA = "flywheel.knowledge-graph/v1"

# Named priority weights (documented in the payload, applied in _priority).
_STATUS_WEIGHT = {"live": 1.0, "verified": 1.0, "enabled": 0.9,
                  "declared": 0.6, "pending": 0.5, "disabled": 0.3,
                  "missing": 0.2, "error": 0.1}
_KIND_BASE = {"hub": 1.0, "project": 0.8, "lane": 0.7, "memory": 0.6,
              "workflow": 0.5, "plugin": 0.5, "error": 0.9}
# Rough context cost in tokens a node's expansion would occupy.
_KIND_COST = {"hub": 50, "project": 800, "lane": 200, "memory": 400,
              "workflow": 150, "plugin": 150, "error": 40}


def _node(kind: str, name: str, label: str, *, verdict: str = "",
          signals: "dict | None" = None) -> dict:
    signals = signals or {}
    return {"id": f"{kind}:{name}", "kind": kind, "label": label,
            "verdict": verdict, "signals": signals,
            "cost": _KIND_COST.get(kind, 200),
            "priority": _priority(kind, verdict, signals)}


def _priority(kind: str, verdict: str, signals: dict) -> float:
    """base(kind) + status weight + bounded salience. Every term is visible:
    kind and verdict are on the node, salience inputs are in `signals`."""
    p = _KIND_BASE.get(kind, 0.4)
    p += _STATUS_WEIGHT.get(verdict, 0.4)
    rel = signals.get("relation_count") or 0
    notes = signals.get("notes") or signals.get("spans") or 0
    p += min(0.5, rel / 200.0) + min(0.3, notes / 20.0)
    return round(p, 4)


def build_graph(surfaces: dict) -> dict:
    """Merge surface documents (each the relevant API payload, or
    {"error": ...} when unreadable) into one typed node/edge graph."""
    nodes = [_node("hub", "flywheel", "flywheel", verdict="live")]
    edges = []
    hub = "hub:flywheel"

    def attach(n: dict, parent: str = hub, edge_kind: str = "surface"):
        nodes.append(n)
        edges.append({"from": parent, "to": n["id"], "kind": edge_kind})

    def error_node(surface: str, message: str):
        attach(_node("error", surface, f"{surface}: {message}",
                     verdict="error"))

    for surface, doc in surfaces.items():
        if not isinstance(doc, dict):
            continue
        if "error" in doc:
            error_node(surface, str(doc["error"]))
            continue
        if surface == "lanes":
            for l in doc.get("lanes", []):
                attach(_node("lane", l.get("name", "?"), l.get("name", "?"),
                             verdict=l.get("status", ""),
                             signals={"status": l.get("status", ""),
                                      "role": l.get("role", "")}))
        elif surface == "projects":
            for p in doc.get("projects", []):
                idx = p.get("index") or {}
                attach(_node("project", p.get("name", "?"),
                             p.get("name", "?"), verdict="live",
                             signals={"root": p.get("root", ""),
                                      "relation_count":
                                          idx.get("relation_count", 0),
                                      "class_total":
                                          idx.get("class_total", 0)}))
        elif surface == "memory":
            attach(_node("memory", "fold-index", "memory (fold index)",
                         verdict="live",
                         signals={k: v for k, v in doc.items()
                                  if isinstance(v, (int, float, bool))
                                  and not isinstance(v, str)}))
        elif surface == "plugins":
            for p in doc.get("plugins", []):
                attach(_node("plugin", p.get("name", "?"),
                             p.get("name", "?"),
                             verdict="enabled" if p.get("enabled", True)
                                     else "disabled",
                             signals={"kind": p.get("kind", "")}))
        elif surface == "workflows":
            for w in doc.get("workflows", []):
                attach(_node("workflow", w.get("name", "?"),
                             w.get("name", "?"), verdict="declared",
                             signals={}))
    return {"schema": SCHEMA, "nodes": nodes, "edges": edges,
            "weights": {"status": _STATUS_WEIGHT, "kind_base": _KIND_BASE,
                        "kind_cost": _KIND_COST},
            "note": "priority is computed from the signals on each node; "
                    "re-derive it to check the graph"}


def gateway_graph(root, run_root, *, with_index: bool = False,
                  budget: "int | None" = None,
                  query: "str | None" = None) -> dict:
    """The live graph: gather each surface from its own module, each failure
    becoming an error node. Per-project index summaries are opt-in
    (`with_index`) because they shell the index engine and cost seconds."""
    surfaces: dict = {}

    def gather(name, fn):
        try:
            surfaces[name] = fn()
        except Exception as e:
            surfaces[name] = {"error": f"{type(e).__name__}: {e}"}

    def projects_doc():
        from harness.projects import project_roster
        doc = project_roster()
        if with_index:
            from harness.index_bridge import index_summary
            for p in doc.get("projects", []):
                s = index_summary(p.get("root", ""))
                p["index"] = {"relation_count": s.get("relation_count", 0),
                              "class_total": s.get("class_total", 0)}
        return doc

    from harness.lanes import lane_roster
    from harness.memory_api import memory_stats
    from harness.plugins import plugin_roster
    from harness.workflows import workflow_roster
    gather("lanes", lane_roster)
    gather("projects", projects_doc)
    gather("memory", lambda: memory_stats(run_root))
    gather("plugins", plugin_roster)
    gather("workflows", lambda: workflow_roster(run_root))
    g = build_graph(surfaces)
    if budget:
        g["context_plan"] = context_plan(g["nodes"], budget, query=query)
    return g


def _relevance(node: dict, terms: list) -> float:
    """Fraction of query terms found in the node's label, id, or signal
    values. Plain substring match: cheap, deterministic, re-derivable."""
    hay = " ".join(
        [node.get("label", ""), node.get("id", "")] +
        [f"{k} {v}" for k, v in (node.get("signals") or {}).items()]).lower()
    hits = sum(1 for t in terms if t in hay)
    return round(hits / len(terms), 4) if terms else 0.0


def context_plan(nodes: list, budget: int, query: "str | None" = None) -> dict:
    """Greedy highest-priority-first selection under a token budget, ties
    broken by id so the plan is deterministic. A query reranks by
    effective_priority = priority + 2 * relevance (the weight is in the
    payload); the excluded count is part of the answer either way: a cut
    context is a fact, not an implementation detail."""
    terms = [t for t in (query or "").lower().split() if t]
    scored = []
    for n in nodes:
        if terms:
            n = dict(n)
            n["relevance"] = _relevance(n, terms)
            n["effective_priority"] = round(
                n.get("priority", 0.0) + 2.0 * n["relevance"], 4)
        scored.append(n)
    ranked = sorted(scored, key=lambda n: (
        -n.get("effective_priority", n.get("priority", 0.0)),
        n.get("id", "")))
    selected, spent = [], 0
    for n in ranked:
        cost = int(n.get("cost", 200))
        if spent + cost > budget:
            continue
        selected.append(n)
        spent += cost
    doc = {"schema": "flywheel.context-plan/v1", "budget": budget,
           "spent": spent, "selected": selected,
           "excluded": len(nodes) - len(selected)}
    if terms:
        doc["query"] = " ".join(terms)
        doc["relevance_weight"] = 2.0
    return doc
