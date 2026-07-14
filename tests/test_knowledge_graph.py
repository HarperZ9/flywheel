"""The cross-surface knowledge graph must be mechanical: every node's
context priority comes from named signals carried in the payload, the
budgeted context plan is a deterministic greedy order, and a surface that
cannot be read appears as an honest error node, never silently missing."""

from harness.knowledge_graph import SCHEMA, build_graph, context_plan

SURFACES = {
    "lanes": {"lanes": [
        {"name": "gather", "status": "live", "role": "perception"},
        {"name": "telos", "status": "missing", "role": "reconciliation"},
    ]},
    "projects": {"projects": [
        {"name": "demo", "root": "C:\\x\\demo",
         "index": {"relation_count": 40, "class_total": 12}},
    ]},
    "memory": {"notes": 3, "folds": 2, "bytes": 2048},
    "plugins": {"plugins": [{"name": "browser", "kind": "mcp",
                             "enabled": True}]},
    "workflows": {"workflows": [{"name": "code-change"}]},
}


def test_graph_merges_every_surface_into_typed_nodes():
    g = build_graph(SURFACES)
    assert g["schema"] == SCHEMA
    kinds = {n["kind"] for n in g["nodes"]}
    assert {"hub", "lane", "project", "memory", "plugin",
            "workflow"} <= kinds
    ids = {n["id"] for n in g["nodes"]}
    for e in g["edges"]:
        assert e["from"] in ids and e["to"] in ids


def test_priority_is_signal_grounded_and_ordered():
    g = build_graph(SURFACES)
    by_id = {n["id"]: n for n in g["nodes"]}
    live = by_id["lane:gather"]
    dead = by_id["lane:telos"]
    assert live["priority"] > dead["priority"]
    assert "signals" in live and "status" in live["signals"]
    project = by_id["project:demo"]
    assert project["signals"]["relation_count"] == 40


def test_context_plan_is_budgeted_greedy_and_deterministic():
    g = build_graph(SURFACES)
    full = context_plan(g["nodes"], budget=10_000_000)
    assert [n["id"] for n in full["selected"]] == \
           [n["id"] for n in context_plan(g["nodes"], budget=10_000_000)["selected"]]
    priorities = [n["priority"] for n in full["selected"]]
    assert priorities == sorted(priorities, reverse=True)
    tight = context_plan(g["nodes"], budget=1)
    assert len(tight["selected"]) < len(full["selected"])
    assert tight["excluded"] > 0  # the cut is visible, not silent


def test_query_reranks_the_plan_mechanically():
    g = build_graph(SURFACES)
    plan = context_plan(g["nodes"], budget=10_000_000,
                        query="gather perception intake")
    ids = [n["id"] for n in plan["selected"]]
    assert ids.index("lane:gather") < ids.index("lane:telos")
    sel = {n["id"]: n for n in plan["selected"]}
    assert sel["lane:gather"]["relevance"] > 0
    assert sel["lane:gather"]["effective_priority"] > \
           sel["lane:gather"]["priority"]
    # No query: no relevance keys, same behavior as before.
    plain = context_plan(g["nodes"], budget=10_000_000)
    assert all("relevance" not in n for n in plain["selected"])


def test_unreadable_surface_is_an_error_node():
    g = build_graph({"lanes": {"error": "lanes unavailable"}})
    errs = [n for n in g["nodes"] if n["kind"] == "error"]
    assert len(errs) == 1
    assert "lanes" in errs[0]["label"]
