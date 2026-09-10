"""Executed closure must survive ablation and distinguish proposal-only edges."""
import pytest
from harness.loop_closure import measure_loop, loop_report


@pytest.fixture(scope="module")
def measured(tmp_path_factory):
    return measure_loop(tmp_path_factory.mktemp("closure"))


def test_core_and_memory_edges_are_executed(measured):
    hs = {(h["frm"], h["to"]): h for h in measured["handoffs"]}
    for edge in [("propose", "verify"), ("verify", "memory"),
                 ("memory", "serve"), ("memory", "context")]:
        assert hs[edge]["closed"] and hs[edge]["verified"]
    evidence = measured["memory_control"]
    assert evidence["enabled_accepted"] and not evidence["disabled_accepted"]
    assert evidence["prompt_changed"] and evidence["source_in_actual_input"]


def test_proposals_and_export_do_not_close_feedback(measured):
    hs = {(h["frm"], h["to"]): h for h in measured["handoffs"]}
    for edge in [("evolve", "propose"), ("corpus", "model")]:
        assert not hs[edge]["closed"] and not hs[edge]["verified"]
    assert not measured["fully_closed"]
    assert measured["closure_fraction"] < 1
    assert "loop closure" in loop_report(measured)


def test_disabled_retrieval_cannot_be_reported_closed(tmp_path, monkeypatch):
    from harness import evolutionary_flywheel
    monkeypatch.setattr(evolutionary_flywheel, "auto_retrieved", lambda pool, task, prereqs: task)
    result = measure_loop(tmp_path)
    edge = next(h for h in result["handoffs"] if h["frm"] == "memory" and h["to"] == "context")
    assert not edge["closed"]
    assert not result["memory_control"]["enabled_accepted"]
    assert "memory->context" in result["open_links"]
