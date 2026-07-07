"""superproject integration falsifier — the harness organs map onto the flagship spine.

Five organs (perception, verification, structure, orchestration, reconciliation), each a
flagship peer plus its native harness cluster, composing over the flagships' own
next-action routing. The spine must be CLOSED (no dangling route) and telos the reconciler.
"""
from harness.superproject import spine, probe_live, MANIFEST, compose_report

LIVE = {f: {"status": "MATCH"} for f in ("gather", "index", "crucible", "forum", "telos")}


def test_five_organs_each_with_flagship_and_native_modules():
    assert set(MANIFEST) == {"perception", "verification", "structure",
                             "orchestration", "reconciliation"}
    for o in MANIFEST.values():
        assert o.flagship and o.version and o.harness_modules   # grounded, not empty


def test_spine_is_closed_no_dangling_route():
    s = spine()
    assert s["closed"] is True                 # every route target is itself a flagship
    assert s["reconciler"] == "telos"
    assert s["routes"]["telos"] == "telos"      # telos reconciles the five-tool workflow


def test_probe_live_all_five_when_doctors_healthy():
    p = probe_live(LIVE)
    assert p["n_organs"] == 5 and p["live"] == 5 and p["all_live"] is True
    assert p["spine_closed"] is True


def test_graceful_without_mcp_edge():
    # MCP is the optional edge: with no doctors, organs read as 'declared', never crash
    p = probe_live()
    assert p["all_live"] is None
    assert all(r["health"] == "declared" for r in p["organs"])
    assert "CLOSED" in compose_report()
