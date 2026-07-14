"""Which other loops close? Each candidate loop is run against the real
local mechanisms; a loop CLOSES iff every handoff executes and chains a
receipt AND the final edge feeds the first. An open edge is named with its
reason — a diagram that cannot execute is not a closed loop."""

from harness.loops import (LOOPS, measure_all_loops, measure_closure)


def test_learning_loop_closes(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    doc = measure_closure(LOOPS["learning"])
    assert doc["closed"] is True, doc["edges"]
    assert all(e["receipt"] for e in doc["edges"])
    # the feedback edge must read back what the loop itself wrote
    assert doc["edges"][-1]["to"] == doc["edges"][0]["from"]


def test_learning_loop_closes_on_repeat_measurement(tmp_path, monkeypatch):
    """A loop that only closes on a virgin store is not a closed loop. The
    second turn must bank fresh evidence to schedule, not rediscover the
    residue of the first turn's retest (content-addressed eid reuse)."""
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    first = measure_closure(LOOPS["learning"])
    second = measure_closure(LOOPS["learning"])
    assert first["closed"] is True, first["edges"]
    assert second["closed"] is True, second["edges"]


def test_economics_loop_closes(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    doc = measure_closure(LOOPS["economics"])
    assert doc["closed"] is True, doc["edges"]


def test_invention_loop_closes_with_a_kernel(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    # inject a kernel that accepts even theorems, refutes odd — the loop
    # must select survivors and seed the next round from them
    def kernel(code):
        return {"passed": ("rfl" in code and "= 2" in code),
                "toolchain": "injected"}
    doc = measure_closure(LOOPS["invention"], ctx={"kernel": kernel})
    assert doc["closed"] is True, doc["edges"]
    assert doc["survivors"] >= 1


def test_a_broken_edge_reports_open_not_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))

    def dead_kernel(code):
        raise ConnectionError("kernel unavailable")

    doc = measure_closure(LOOPS["invention"], ctx={"kernel": dead_kernel})
    assert doc["closed"] is False
    open_edges = [e for e in doc["edges"] if not e["executed"]]
    assert open_edges
    assert "kernel unavailable" in open_edges[0]["note"]


def test_measure_all_reports_every_candidate(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    doc = measure_all_loops(ctx={"kernel": lambda c: {"passed": True,
                                                      "toolchain": "inj"}})
    names = {l["name"] for l in doc["loops"]}
    assert {"learning", "economics", "invention", "research"} <= names
    # each loop reports a verdict; none is silently skipped
    assert all("closed" in l for l in doc["loops"])
    assert doc["closed_count"] == sum(1 for l in doc["loops"] if l["closed"])
