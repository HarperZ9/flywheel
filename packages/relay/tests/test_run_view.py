"""The witnessed-run visualizer: a run a stranger can see is unbroken.

The load-bearing test is the tampered one -- flipping a byte snaps exactly one
edge red and flips the verdict to REFUTED, localized to the mutated seq. That is
the demo, and the thing no competitor can draw.
"""
import json

from relay.local_session import SessionLedger
from relay.run_view import BROKEN, OK, load_run, render, verify_edges


def _accepted_run():
    led = SessionLedger()
    led.append("user", "add a hello function")
    led.append("assistant", "read hello.py first")
    led.append("tool_call", 'read_file {"path": "hello.py"}')
    led.append("tool_result", "def UNIQUEMARK(): pass", {"tool": "read_file", "ok": True})
    led.append("assistant", "Done, the function is present.")
    result = {"verified": True, "check_passed": True, "check_trusted": True, "accepted": True}
    return led, result


# --- 1. golden run: every edge OK, header ALLOW ---

def test_golden_run_all_edges_ok_and_verdict_allow():
    led, result = _accepted_run()
    edges = verify_edges(led)
    assert [e.status for e in edges] == [OK] * len(led.entries)
    out = render(led, result, color=False)
    assert "ALLOW" in out and "accepted=True" in out
    assert "REFUTED" not in out and BROKEN not in out


def test_load_run_roundtrips_a_saved_ledger(tmp_path):
    led, _ = _accepted_run()
    path = tmp_path / "run.jsonl"
    led.save(str(path))
    view = load_run(str(path))
    assert [e.entry_hash for e in view.ledger.entries] == [e.entry_hash for e in led.entries]
    assert all(e.status == OK for e in verify_edges(view.ledger))


# --- 2. tampered run: one BROKEN edge, localized, REFUTED ---

def test_tampered_content_localizes_the_break_and_refutes():
    led, result = _accepted_run()
    led.entries[3].content = led.entries[3].content.replace("UNIQUEMARK", "GAMED")  # flip node 3
    edges = verify_edges(led)
    broken = [e for e in edges if e.status == BROKEN]
    assert len(broken) == 1 and broken[0].seq == 3  # localized, not a blanket fail
    out = render(led, result, color=False)
    assert "REFUTED" in out
    assert "hash chain broken at seq 3" in out


def test_tampered_file_is_shown_broken_not_refused(tmp_path):
    led, _ = _accepted_run()
    path = tmp_path / "run.jsonl"
    led.save(str(path))
    text = path.read_text(encoding="utf-8").replace("UNIQUEMARK", "GAMED")  # a byte flip on disk
    path.write_text(text, encoding="utf-8")
    view = load_run(str(path))  # verify=False: inspect a broken chain, do not raise
    broken = [e for e in verify_edges(view.ledger) if e.status == BROKEN]
    assert len(broken) == 1 and broken[0].seq == 3


# --- 3. integrity overlay: edited grader file, header untrusted ---

def test_integrity_overlay_flags_an_edited_test_file():
    led = SessionLedger()
    led.append("user", "make the tests pass")
    led.append("assistant", "edit the test")
    led.append("tool_call", 'edit_file {"path": "tests/test_core.py", "new": "assert True"}')
    result = {"verified": True, "check_passed": True, "check_trusted": False, "accepted": False}
    out = render(led, result, color=False)
    assert "edited_protected_file" in out
    assert "REFUTED" in out  # a gamed grader refutes the run


# --- 4. intent overlay: claim of prior work with nothing behind it ---

def test_intent_overlay_flags_a_claimed_history():
    led = SessionLedger()
    led.append("user", "add a test")
    led.append("assistant", "I previously ran the full suite, so it is green.")
    out = render(led, color=False)
    assert "claimed_history" in out


# --- 5. no-color determinism ---

def test_no_color_render_is_byte_stable():
    led, result = _accepted_run()
    a = render(led, result, color=False)
    b = render(led, result, color=False)
    assert a == b
    assert "\x1b[" not in a  # no ANSI escapes in the plain-text timeline


def test_render_without_result_reports_chain_intact_but_no_certificate():
    led, _ = _accepted_run()
    out = render(led, None, color=False)
    assert "CHAIN INTACT" in out
    assert "no accept certificate" in out


def test_json_ledger_shape_is_what_verify_reads(tmp_path):
    # guard: the saved shape carries the fields verify_edges re-derives.
    led, _ = _accepted_run()
    path = tmp_path / "run.jsonl"
    led.save(str(path))
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert {"seq", "kind", "content", "meta", "prev_hash", "entry_hash"} <= set(row)
