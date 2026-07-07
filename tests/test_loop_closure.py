"""loop-closure falsifier — the self-recursive loop is MEASURED, not asserted.

Honest properties: the fast/config links are closed and the core is EXECUTED (not
just claimed); the two known-open links (auto-context, auto-retrain) are reported
open, not papered over; and the closure verdict is honest about partial closure.
"""
from harness.loop_closure import measure_loop, loop_report


def test_core_loop_links_are_executed_and_closed(tmp_path):
    m = measure_loop(tmp_path)
    executed = set(m["executed_links"])
    # the core cycle must be genuinely executed, not structurally guessed
    assert "propose->verify" in executed
    assert "verify->memory" in executed
    assert "memory->serve" in executed
    # and those executed links are closed
    hs = {(h["frm"], h["to"]): h for h in m["handoffs"]}
    assert hs[("propose", "verify")]["closed"]
    assert hs[("verify", "memory")]["closed"]
    assert hs[("memory", "serve")]["closed"]


def test_open_links_are_reported_not_hidden(tmp_path):
    m = measure_loop(tmp_path)
    assert "memory->context" in m["open_links"], "auto-context-feedback is OPEN and must be named"
    assert "corpus->model" in m["open_links"], "auto-retrain is OPEN and must be named"
    assert m["fully_closed"] is False, "the loop is NOT fully closed — honest partial closure"


def test_closure_is_partial_and_high(tmp_path):
    m = measure_loop(tmp_path)
    # closed at fast + config altitudes, open at content + weight altitudes
    assert 0.5 < m["closure_fraction"] < 1.0
    assert "loop closure" in loop_report(m)
