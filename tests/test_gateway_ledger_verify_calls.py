"""`flywheel gateway-ledger verify` checks the call records, not only the chain of hashes.

Sixth review round of 2.0.0, finding S2 of the fourth independent review
(probe r4probes/p2_verify_semantics.py). The rule that every end entry has a
started entry before it, that a call has one end, that a call id is started
once and that an end agrees with its start was checked only by the tests'
helper `gateway_messages_support.recorded`. The shipped verifier exited 0 for
a ledger that shows a served call with no start.

Each case appends entries through `GatewayLedger`, so the chain of hashes
holds, closes it, and runs the command with no gateway running. The helper
now calls the same code as the command (`gateway_call_audit.audit`), and the last
test holds the two to the same answer on every case.
"""
import pytest

from harness import gateway_ledger, gateway_ledger_cli
from tests import gateway_messages_support as support

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release
S, E, F = "endpoint_call_started", "endpoint_call", "endpoint_call_failed"
A, B = "a" * 24, "b" * 24


def start(call, key="k1"):
    return (S, call, {"endpoint": "openai", "interface": "anthropic-messages",
                      "prompt_sha": "p" * 16, "key": key, "key_fp": "fp-" + key, "call": call,
                      "reserved": [10, 64]})


def end(call, kind=E, key="k1", **more):
    return (kind, "r" * 16, {"endpoint": "openai", "interface": "anthropic-messages",
                             "prompt_sha": "p" * 16, "key": key, "key_fp": "fp-" + key,
                             "call": call, **more})


SETTLED = ("endpoint_call_settled", A, {"call": A, "settled_by": "operator", "charged_tokens": 0})
OTHER = (E, "r" * 16, {"endpoint": "other", "prompt_sha": "q" * 16, "key": "k2",
                       "key_fp": "fp-k2", "call": A})
# name -> (entries, exit code of `verify`, the finding it names or "")
CASES = {
    "control: start then end": ([start(A), end(A)], 0, ""),
    "control: two calls, interleaved": ([start(A), start(B), end(B), end(A, F, reason="x")], 0, ""),
    "control: a late end": ([start(A), end(A, F, reason="ledger_failed", late=True)], 0, ""),
    "control: start, no end": ([start(A)], 3, ""),
    "an end with no start": ([end(A)], 4, "end_without_start"),
    "an end that names no call": ([(E, "r" * 16, {"endpoint": "openai"})], 4, "end_without_start"),
    "two ends for one start": ([start(A), end(A), end(A, F, reason="x")], 4, "second_end"),
    "a call id started twice, one end": ([start(A), start(A), end(A)], 4, "repeated_start"),
    "a call id started again after its end": ([start(A), end(A), start(A)], 4, "repeated_start"),
    "an end that differs from its start": ([start(A), OTHER], 4, "end_differs_from_start"),
    "a start whose content is not its call id": (
        [(S, B, start(A)[2]), end(A)], 4, "malformed_start"),
    "a settled entry for a call that never started": ([SETTLED], 4, "end_without_start"),
    "a refused entry with the call id does not close the call": (
        [start(A), ("endpoint_call_refused", "key_budget_exceeded",
                    {"interface": "anthropic-messages", "key": "k1", "call": A})], 3, ""),
    "an unknown kind with the call id does not close the call": (
        [start(A), ("note", "hello", {"call": A})], 3, ""),
}


def build(home, rows) -> None:
    ledger = gateway_ledger.GatewayLedger(home)
    for kind, content, meta in rows:
        ledger.append(kind, content, meta)
    ledger.close()


def run(capsys, home, *argv) -> tuple:
    capsys.readouterr()
    code = gateway_ledger_cli.main(list(argv), environ={"FLYWHEEL_HOME": str(home)})
    said = capsys.readouterr()
    return code, said.out + said.err


@pytest.mark.parametrize("name", sorted(CASES))
def test_verify_names_a_call_record_that_breaks_the_rules(tmp_path, capsys, name):
    rows, expected, finding = CASES[name]
    build(tmp_path, rows)
    code, text = run(capsys, tmp_path, "verify")
    assert code == expected, text
    assert "gateway ledger verifies" in text    # the chain of hashes holds in every case
    if finding:
        assert f"CALL RECORD FAULT {finding}: call " in text and "call record fault(s)" in text
    else:
        assert "CALL RECORD FAULT" not in text
    shown, said = run(capsys, tmp_path, "show")
    assert shown == expected
    assert ("CALL RECORD FAULT" in said) is bool(finding)


def test_a_changed_byte_is_still_a_broken_chain_and_exits_1(tmp_path, capsys):
    build(tmp_path, [start(A), end(A), start(B), end(B)])
    segment = gateway_ledger.segments(tmp_path)[0]
    lines = segment.read_bytes().split(b"\n")
    lines[2] = lines[2].replace(b'"openai"', b'"openaj"', 1)
    segment.write_bytes(b"\n".join(lines))
    code, text = run(capsys, tmp_path, "verify")
    assert code == 1 and "BROKEN: line 3 does not verify" in text


def test_a_fault_outranks_an_unsettled_call_and_both_are_named(tmp_path, capsys):
    build(tmp_path, [start(A), end(B)])
    code, text = run(capsys, tmp_path, "verify")
    assert code == 4 and "end_without_start" in text and f"UNSETTLED call {A}" in text


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_tests_helper_and_the_command_agree(tmp_path, capsys, name):
    """`recorded` passes exactly when `verify` exits 0: they run the same check."""
    rows, expected, _finding = CASES[name]
    build(tmp_path, rows)
    entries = [entry for segment in gateway_ledger.check(tmp_path) for entry in segment["rows"]]
    code, _text = run(capsys, tmp_path, "verify")
    assert code == expected
    if code == 0:
        assert [entry.kind for entry in support.recorded(entries)] == [
            kind for kind, _content, _meta in rows if kind != S]
    else:
        with pytest.raises(AssertionError):
            support.recorded(entries)
