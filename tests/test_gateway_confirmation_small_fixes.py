"""Smaller items of the 2.0 confirmation review, each with its control.

  verify, no segment     a head record with no segment file is a broken ledger
  verify, mid-append     a problem is read once more before it is reported
  unfinished stream      charged the provider's output count when one arrived,
                         and for tool-call arguments and thinking, not text only
  key name `owner`       reserved: it is the ledger's name for the gateway token
  show                   control characters in a recorded string are escaped

A real gateway on a loopback port with a stub upstream where a call is made.
No provider is called.
"""
import json

import pytest

from harness import (endpoints_assemble, gateway_keys, gateway_ledger, gateway_ledger_cli,
                     gateway_unaccounted)
from harness.gateway_messages_wire import sse
from tests import gateway_messages_support as support
from tests.gateway_keys_support import MESSAGES, keyed, post, served  # noqa: F401

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release


def _cli(home, *argv) -> int:
    return gateway_ledger_cli.main(list(argv), environ={"FLYWHEEL_HOME": str(home)})


def _filled(home, count: int = 3) -> None:
    ledger = gateway_ledger.GatewayLedger(home)
    for index in range(count):
        ledger.append("endpoint_call", f"sha{index}", {"key": "owner"})
    ledger.close()


# --- verify ---------------------------------------------------------------------------

def test_verify_fails_when_the_head_record_is_there_and_its_segment_is_not(tmp_path, capsys):
    _filled(tmp_path)
    (tmp_path / "gateway-ledger" / "segment-000001.jsonl").unlink()
    assert _cli(tmp_path, "verify") == 1
    assert "segments were removed" in capsys.readouterr().out
    # A gateway that starts on it records the break, and verify keeps failing.
    again = gateway_ledger.GatewayLedger(tmp_path)
    again.append("endpoint_call", "later", {"key": "owner"})
    again.close()
    assert "segments were removed" in again.found_broken
    found, = gateway_ledger.check(tmp_path)
    assert found["header"]["previous_state"] == "broken" and found["entries"] == 1
    assert _cli(tmp_path, "verify") == 1
    assert "records a break" in capsys.readouterr().out


def test_control_a_home_with_no_ledger_and_an_intact_one_still_pass(tmp_path, capsys):
    assert _cli(tmp_path / "new", "verify") == 0
    assert "no gateway ledger yet" in capsys.readouterr().out
    _filled(tmp_path / "used")
    assert _cli(tmp_path / "used", "verify") == 0


def test_verify_reads_once_more_before_it_reports_a_problem(tmp_path, monkeypatch, capsys):
    """A gateway appending during the first read can look like a removed entry."""
    _filled(tmp_path)
    real, reads = gateway_ledger.check, []
    monkeypatch.setattr(gateway_ledger_cli, "RETRY_AFTER", 0.0)

    def racing(home):
        reads.append(home)
        found = real(home)
        if len(reads) == 1:                 # what a read between segment and head gives
            found[-1].update(ok=False, problem="the file holds 2 entries and the head "
                             "record 3: entries were removed")
        return found
    monkeypatch.setattr(gateway_ledger, "check", racing)
    assert _cli(tmp_path, "verify") == 0 and len(reads) == 2
    assert "verifies" in capsys.readouterr().out


def test_control_a_ledger_broken_on_disk_fails_after_the_second_read_too(
        tmp_path, monkeypatch, capsys):
    _filled(tmp_path)
    path = tmp_path / "gateway-ledger" / "segment-000001.jsonl"
    lines = path.read_bytes().split(b"\n")
    path.write_bytes(b"\n".join(lines[:-2]) + b"\n")     # the last entry removed whole
    reads = []
    real = gateway_ledger.check
    monkeypatch.setattr(gateway_ledger_cli, "RETRY_AFTER", 0.0)
    monkeypatch.setattr(gateway_ledger, "check", lambda home: reads.append(home) or real(home))
    assert _cli(tmp_path, "verify") == 1 and len(reads) == 2
    assert "entries were removed" in capsys.readouterr().out


# --- an unfinished stream --------------------------------------------------------------

def _anthropic(*events) -> bytes:
    start = {"type": "message_start", "message": {
        "id": "msg_01Fixture", "type": "message", "role": "assistant", "content": [],
        "model": "claude-sonnet-5", "stop_reason": None, "stop_sequence": None,
        "usage": {"input_tokens": 468, "output_tokens": 1}}}
    return b"".join(sse(event["type"], event) for event in (start, *events))


_TOOL = [
    {"type": "content_block_start", "index": 0,
     "content_block": {"type": "tool_use", "id": "toolu_01", "name": "write_file", "input": {}}},
    {"type": "content_block_delta", "index": 0,
     "delta": {"type": "input_json_delta", "partial_json": '{"path": "n.txt", "content": '}},
    {"type": "content_block_delta", "index": 0,
     "delta": {"type": "input_json_delta", "partial_json": '"one two three four five six"}'}},
]
_DELTA = {"type": "message_delta", "delta": {"stop_reason": "tool_use", "stop_sequence": None},
          "usage": {"output_tokens": 57}}


def _cut_stream(keyed, served, body: bytes):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, _upstream, ledger = served([support.stream_answer(body)], provider="anthropic")
    status, _headers, _body = post(url, "/v1/messages", raw, {**MESSAGES, "stream": True})
    assert status == 200
    entry, = ledger.entries
    assert entry.meta["reason"] == "stream_incomplete" and entry.meta["estimated"] is True
    return keys.row("ci-bot")["totals"], entry


def test_a_stream_cut_after_the_provider_reported_its_output_is_charged_that_count(
        keyed, served):
    """`message_delta` carried output_tokens 57; only `message_stop` is missing."""
    stop = {"type": "content_block_stop", "index": 0}
    totals, entry = _cut_stream(keyed, served, _anthropic(*_TOOL, stop, _DELTA))
    assert (totals["input_tokens"], totals["output_tokens"]) == (468, 57)
    assert entry.meta["charged_tokens"] == 468 + 57


def test_tool_call_arguments_received_before_a_cut_are_charged(keyed, served):
    """No text arrived, so the charge for output was once zero."""
    totals, _entry = _cut_stream(keyed, served, _anthropic(*_TOOL))
    assert totals["input_tokens"] == 468
    assert totals["output_tokens"] >= 8, "the argument text counts as output"


def test_arguments_and_reasoning_count_in_the_other_formats():
    openai = endpoints_assemble.OpenAIAssembler()
    openai.feed("", {"choices": [{"index": 0, "delta": {
        "reasoning_content": "think it through",
        "tool_calls": [{"index": 0, "id": "c1", "function": {
            "name": "write_file", "arguments": '{"path": "n.txt"}'}}]}}]})
    assert "n.txt" in gateway_unaccounted._beside_text(openai)
    assert "think it through" in gateway_unaccounted._beside_text(openai)
    openai.feed("", {"choices": [], "usage": {"prompt_tokens": 451, "completion_tokens": 9}})
    assert gateway_unaccounted._reported(openai) == {"input": 451, "output": 9}
    gemini = endpoints_assemble.GeminiAssembler()
    gemini.feed("", {"candidates": [{"content": {"parts": [
        {"text": "weigh it", "thought": True},
        {"functionCall": {"name": "write_file", "args": {"path": "n.txt"}}}]}}],
        "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 4}})
    assert "weigh it" in gateway_unaccounted._beside_text(gemini)
    assert "n.txt" in gateway_unaccounted._beside_text(gemini)
    assert gateway_unaccounted._reported(gemini) == {"input": 12, "output": 4}


def test_control_text_alone_is_charged_its_estimate(keyed, served):
    """The provider's input count, and the estimate of the text received: 5 words,
    and 9 as a quarter of its characters. The larger is charged (third review, D1)."""
    totals, _entry = _cut_stream(keyed, served, support.raw("upstream/anthropic_cut.sse"))
    assert (totals["input_tokens"], totals["output_tokens"]) == (468, 9)


# --- the key name `owner` ---------------------------------------------------------------

@pytest.mark.parametrize("name", ["owner", "Owner", "OWNER"])
def test_no_key_can_take_the_gateway_tokens_ledger_name(keyed, name):
    keys, store = keyed
    with pytest.raises(gateway_keys.KeysError, match="owner"):
        keys.create(name)
    assert keys.rows() == {} and store.saved == {}


def test_control_a_name_that_only_contains_owner_is_allowed(keyed):
    keys, _store = keyed
    keys.create("owner-ci")
    assert list(keys.rows()) == ["owner-ci"]


# --- show ---------------------------------------------------------------------------------

def test_show_escapes_control_characters_an_upstream_put_in_a_record(tmp_path, capsys):
    ledger = gateway_ledger.GatewayLedger(tmp_path)
    ledger.append("endpoint_call", "sha", {
        "key": "owner", "interface": "anthropic-messages",
        "model_ref": "openai:evil\x1b[2J\x07\r\nmodel\u202e", "response_sha": "ab"})
    ledger.close()
    assert _cli(tmp_path, "show") == 0
    shown = capsys.readouterr().out
    assert shown.count("\n") == 1, "one entry is one line"
    assert not any(ord(char) < 32 or ord(char) > 126 for char in shown.rstrip("\n"))
    assert "evil\\x1b[2J\\x07\\x0d\\x0amodel\\u202e" in shown
    # Control: --json already escaped them, and still carries the value whole.
    assert _cli(tmp_path, "show", "--json") == 0
    row = json.loads(capsys.readouterr().out)
    assert row["meta"]["model_ref"] == "openai:evil\x1b[2J\x07\r\nmodel\u202e"
