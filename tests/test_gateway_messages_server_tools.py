"""Messages pass-through carries the provider's own tools (server tools).

An Anthropic upstream can run tools itself: web search, web fetch, code
execution. The reply then holds a `server_tool_use` block and the tool's
result block (`web_search_tool_result`, `bash_code_execution_tool_result` and
others). Those are the provider's blocks, not a result the client was
supposed to produce, so the gateway delivers them as sent, records the call
as served and charges the key from the reported usage.

Wire formats, read 2026-11-14:
  https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool
      response blocks `server_tool_use` {id "srvtoolu_...", name, input} and
      `web_search_tool_result` {tool_use_id, content}; the Streaming section:
      `content_block_start` for `server_tool_use` (id and name), then
      `input_json_delta` with `partial_json`, then the result block whole in
      one `content_block_start`; `usage.server_tool_use.web_search_requests`
  https://platform.claude.com/docs/en/agents-and-tools/tool-use/server-tools
      "A `server_tool_use` block that Claude calls directly streams like a
      client `tool_use` block"; "The result block arrives complete in a
      single `content_block_start` event, with no deltas"
  https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool
      result block types `bash_code_execution_tool_result` and
      `text_editor_code_execution_tool_result`

The fixtures upstream/anthropic_server_tool.{sse,json} were written by hand in
those shapes. No provider was called.
"""
import json

import pytest

from harness.endpoints_assemble import AnthropicAssembler
from tests import gateway_messages_support as support
from tests.gateway_keys_support import MESSAGES, keyed, post, served  # noqa: F401

TOOLS = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]
REPORTED = 6039 + 931                    # the fixture's input and output counts
STREAM = support.raw("upstream/anthropic_server_tool.sse")
PLAIN = support.load("upstream/anthropic_server_tool.json")


def _event(name: str, data: dict) -> bytes:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()


def _start(index: int, block: dict) -> bytes:
    return _event("content_block_start", {"type": "content_block_start", "index": index,
                                          "content_block": block})


def _stop(index: int) -> bytes:
    return _event("content_block_stop", {"type": "content_block_stop", "index": index})


HEAD = _event("message_start", {"type": "message_start", "message": {
    "id": "msg_fixture", "type": "message", "role": "assistant", "model": "claude-sonnet-5",
    "content": [], "stop_reason": None, "stop_sequence": None,
    "usage": {"input_tokens": 20, "output_tokens": 1}}})
TAIL = (_event("message_delta", {"type": "message_delta", "delta": {
    "stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 7}})
    + _event("message_stop", {"type": "message_stop"}))


def _keyed_gateway(keyed, served, answers):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    keys.mark("ci-bot", server_tools=["web_search"])
    url, upstream, ledger = served(answers, provider="anthropic")
    return keys, raw, url, upstream, ledger


def test_a_streamed_server_tool_reply_is_delivered_recorded_and_charged(keyed, served):
    keys, raw, url, upstream, ledger = _keyed_gateway(
        keyed, served, [support.stream_answer(STREAM)])
    status, _headers, body = post(url, "/v1/messages", raw,
                                  {**MESSAGES, "stream": True, "tools": TOOLS})
    assert status == 200
    sent, last = STREAM.rsplit(b"event: message_stop", 1)
    assert body.startswith(sent), "every upstream event before message_stop, byte for byte"
    events = support.events(body)
    assert [name for name, _data in events].count("error") == 0
    assert events[-1][0] == "message_stop" and events[-1][1]["x_receipt"]["receipt_id"]
    assert upstream.requests[0]["body"]["tools"] == TOOLS
    assert support.kinds(ledger) == ["endpoint_call"]
    meta = ledger.entries[0].meta
    assert meta["charged_tokens"] == REPORTED and meta["usage_reported"] is True
    assert meta["server_tool_use"] == {"web_search_requests": 1}
    assert keys.row("ci-bot")["totals"]["tokens"] == REPORTED


def test_a_plain_server_tool_reply_is_delivered_recorded_and_charged(keyed, served):
    keys, raw, url, _upstream, ledger = _keyed_gateway(
        keyed, served, [support.json_answer(PLAIN)])
    status, _headers, body = post(url, "/v1/messages", raw, {**MESSAGES, "tools": TOOLS})
    assert status == 200
    assert body["content"] == PLAIN["content"], "the provider's blocks, unchanged"
    assert body["usage"] == PLAIN["usage"] and body["x_receipt"]["receipt_id"]
    assert support.kinds(ledger) == ["endpoint_call"]
    assert ledger.entries[0].meta["server_tool_use"] == {"web_search_requests": 1}
    assert keys.row("ci-bot")["totals"]["tokens"] == REPORTED


def test_the_streamed_and_the_plain_reply_record_the_same_response_hash(keyed, served):
    _keys, raw, url, _upstream, ledger = _keyed_gateway(
        keyed, served, [support.stream_answer(STREAM), support.json_answer(PLAIN)])
    body = {**MESSAGES, "tools": TOOLS}
    assert post(url, "/v1/messages", raw, {**body, "stream": True})[0] == 200
    assert post(url, "/v1/messages", raw, body)[0] == 200
    first, second = ledger.entries
    assert first.meta["response_sha"] == second.meta["response_sha"]


@pytest.mark.parametrize("kind", ["bash_code_execution_tool_result",
                                  "text_editor_code_execution_tool_result",
                                  "web_fetch_tool_result", "mcp_tool_result",
                                  "a_block_type_added_next_year"])
def test_any_provider_block_type_passes_through_untouched(keyed, served, kind):
    block = {"type": kind, "tool_use_id": "srvtoolu_fixture02", "content": {"type": "x"}}
    stream = (HEAD + _start(0, block)
              + _event("content_block_delta", {"type": "content_block_delta", "index": 0,
                                               "delta": {"type": "a_delta_added_next_year"}})
              + _stop(0) + _start(1, {"type": "text", "text": ""})
              + _event("content_block_delta", {"type": "content_block_delta", "index": 1,
                                               "delta": {"type": "text_delta", "text": "Done."}})
              + _stop(1) + TAIL)
    _keys, _raw, url, _upstream, ledger = _keyed_gateway(
        keyed, served, [support.stream_answer(stream)])
    status, _headers, body = post(url, "/v1/messages", support.TOKEN,
                                  {**MESSAGES, "stream": True})
    assert status == 200 and json.dumps(block).encode() in body
    assert support.events(body)[-1][0] == "message_stop"
    assert support.kinds(ledger) == ["endpoint_call"]


def test_control_a_reply_that_claims_a_client_tool_result_is_still_refused(keyed, served):
    """The exact type `tool_result` is the client's to produce. It stays refused."""
    claimed = {**PLAIN, "content": [{"type": "text", "text": "Here."}, {
        "type": "tool_result", "tool_use_id": "toolu_fixture03", "content": "made up"}]}
    _keys, _raw, url, _upstream, ledger = _keyed_gateway(
        keyed, served, [support.json_answer(claimed)])
    status, _headers, body = post(url, "/v1/messages", support.TOKEN)
    assert status == 502 and "tool result" in body["error"]["message"]
    assert [(e.kind, e.meta["reason"]) for e in ledger.entries] == [
        ("endpoint_call_failed", "tool_result_claimed")]


def test_the_coding_session_still_refuses_every_result_block():
    """The session never offers server tools, so its rule stays the broad one."""
    from harness.endpoints_tools_wire import _anthropic_in
    for kind in ("tool_result", "web_search_tool_result"):
        assert _anthropic_in({"content": [{"type": kind}]}, {})[2] is True


def _fed(*events) -> AnthropicAssembler:
    assembler = AnthropicAssembler()
    for name, data in support.events(HEAD + b"".join(events) + TAIL):
        assembler.feed(name, data)
    return assembler


def _json_delta(index: int, text: str) -> bytes:
    return _event("content_block_delta", {"type": "content_block_delta", "index": index,
                                          "delta": {"type": "input_json_delta",
                                                    "partial_json": text}})


def test_the_assembler_collects_a_server_tool_input():
    made = _fed(_start(0, {"type": "server_tool_use", "id": "srvtoolu_fixture04",
                           "name": "web_search"}),
                _json_delta(0, "{\"query\":"), _json_delta(0, "\"x\"}"), _stop(0))
    assert made.complete()
    assert made.response()["content"][0]["input"] == {"query": "x"}


def test_the_assembler_keeps_a_provider_block_whose_input_is_not_json():
    made = _fed(_start(0, {"type": "server_tool_use", "id": "srvtoolu_fixture05",
                           "name": "web_search"}), _json_delta(0, "{not json"), _stop(0))
    assert made.complete() and "input" not in made.response()["content"][0]


def test_control_the_assembler_still_refuses_a_client_tool_call_that_is_not_json():
    with pytest.raises(ValueError):
        _fed(_start(0, {"type": "tool_use", "id": "toolu_fixture06", "name": "read",
                        "input": {}}), _json_delta(0, "{not json"), _stop(0))
