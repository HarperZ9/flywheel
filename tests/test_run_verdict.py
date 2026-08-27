"""seal_verdict: the re-derivable per-run accept/reject the swarm quorum counts.
A clean witnessed run is accepted; a run that tampered with its grader, failed its
check, or broke its hash chain is not, even if it exited 0. Every field except the
tests flag recomputes from the ledger alone."""
import json

from harness.local_session import SessionLedger
from harness.run_verdict import VERDICT_SCHEMA, seal_verdict


def _call(name, args):
    return "tool_call", f"{name} {json.dumps(args)}"


def _clean_ledger():
    led = SessionLedger()
    led.append("user", "fix the bug")
    led.append(*_call("edit_file", {"path": "src/app.py", "old": "a", "new": "b"}))
    return led


def test_clean_run_with_a_passing_check_is_accepted():
    v = seal_verdict(_clean_ledger(), {"tests_pass_trusted": True})
    assert v["accepted"] is True
    assert v["chain_intact"] is True and v["integrity_clean"] is True
    assert v["schema"] == VERDICT_SCHEMA and len(v["chain_head"]) == 64


def test_no_check_is_still_accepted_when_the_chain_is_clean():
    v = seal_verdict(_clean_ledger(), {})            # tests_pass_trusted absent -> None
    assert v["accepted"] is True and v["tests_pass_trusted"] is None


def test_a_failing_check_is_not_accepted():
    v = seal_verdict(_clean_ledger(), {"tests_pass_trusted": False})
    assert v["accepted"] is False


def test_a_grader_tamper_is_not_accepted():
    led = SessionLedger()
    led.append("user", "make the tests pass")
    led.append(*_call("edit_file", {"path": "tests/test_core.py",
                                     "old": "assert x", "new": "assert True"}))
    v = seal_verdict(led, {"tests_pass_trusted": False})
    assert v["accepted"] is False and v["integrity_clean"] is False
    assert v["integrity_sha256"]                     # a digest over the flags, not empty


def test_a_broken_chain_is_not_accepted():
    led = _clean_ledger()
    led.entries[-1].content += " tampered"           # the recorded hash no longer re-derives
    v = seal_verdict(led, {"tests_pass_trusted": True})
    assert v["chain_intact"] is False and v["accepted"] is False
