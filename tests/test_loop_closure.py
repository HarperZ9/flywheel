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


def test_content_link_now_closed_weight_link_still_open(tmp_path):
    m = measure_loop(tmp_path)
    # memory->context is now CLOSED (evolutionary_flywheel.auto_retrieved, compounds)
    assert "memory->context" not in m["open_links"]
    # corpus->model (auto-retrain) remains the one honest open link
    assert "corpus->model" in m["open_links"], "auto-retrain is OPEN and must be named"
    assert m["fully_closed"] is False, "one link (auto-retrain) still open — honest"


def test_closure_is_high_but_not_complete(tmp_path):
    m = measure_loop(tmp_path)
    # 8/9 now: closed at fast + config + content, open only at the weight altitude
    assert m["closure_fraction"] >= 0.85 and m["closure_fraction"] < 1.0
    assert m["open_links"] == ["corpus->model"]
    assert "loop closure" in loop_report(m)
