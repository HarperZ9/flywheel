"""Refusals on the gateway's Responses interface: malformed and unsupported requests.

Every row is refused with the documented error body, names the field or the
item type, writes no ledger entry and sends nothing upstream. The REFUSED rows
are the refused lines of the subset table in docs/GATEWAY-INTERFACES.md.

Wire format, read 2026-11-14. platform.openai.com refused the fetch (403), so:
  https://github.com/openai/openai-openapi (manual_spec branch, openapi.yaml):
      CreateResponse (the request fields), Error and ErrorResponse
  openai Python SDK 2.36.0, types/responses: response_create_params,
      response_input_item_param (the item types), tool_param (the tool types)
  https://developers.openai.com/api/docs/guides/error-codes
      `invalid_request_error`
"""
import pytest

from harness import gateway_responses, gateway_turn
from harness.local_session import SessionLedger
from tests import gateway_responses_support as support
from tests.hosted_stream_fixtures import plain_object

MODEL = "gpt-5.3-codex"


def _ask(monkeypatch, provider, body, *, plain=()):
    ledger = SessionLedger()
    backend = support.replayed(monkeypatch, provider, plain=plain)
    body = support.load(body) if isinstance(body, str) else body
    return gateway_responses.handle(body, {}, ledger), backend, ledger


_is_error = support.is_error


def _refused_cleanly(monkeypatch, body, names) -> None:
    answer, backend, ledger = _ask(monkeypatch, "openai", body,
                                   plain=[plain_object("openai", "turn2")])
    assert _is_error(answer, 400, "invalid_request_error")
    assert names in answer.body["error"]["message"]
    assert ledger.entries == []               # refused before the upstream: no entry at all
    assert support.nothing_sent(backend)


def _with(**fields) -> dict:
    return {"model": MODEL, "input": "hi", **fields}


MALFORMED = [
    ({"input": "hi"}, "model"),
    ({"model": MODEL}, "input"),
    (_with(input=[]), "input"),
    (_with(input=["hi"]), "input.0"),
    (_with(input=[{"role": "tool", "content": "x"}]), "input.0.role"),
    (_with(input=[{"role": "user", "content": 7}]), "input.0.content"),
    (_with(input=[{"role": "user", "content": [{"type": "input_text"}]}]),
     "input.0.content.0.text"),
    (_with(input=[{"type": "function_call", "call_id": "c1", "name": "t",
                   "arguments": "{not json"}]), "input.0.arguments"),
    (_with(instructions=["Be brief."]), "instructions"),
    (_with(tools=[{"type": "function"}]), "tools.0"),
    (_with(tool_choice="sometimes"), "tool_choice"),
    (_with(tool_choice={"type": "function"}), "tool_choice.name"),
    (_with(temperature="hot"), "temperature"),
    (_with(max_output_tokens=0), "max_output_tokens"),
    (["not", "an", "object"], "JSON object"),
]


@pytest.mark.parametrize("body, names", MALFORMED)
def test_malformed_request_is_refused_before_any_upstream_call(monkeypatch, body, names):
    _refused_cleanly(monkeypatch, body, names)


def _part(kind: str) -> dict:
    return _with(input=[{"role": "user", "content": [{"type": kind, "file_id": "file_x"}]}])


# One row per refused line of the subset table in docs/GATEWAY-INTERFACES.md.
REFUSED = [
    (_with(previous_response_id="resp_abc"), "previous_response_id"),
    (_with(conversation="conv_abc"), "conversation"),
    (_with(background=True), "background"),
    (_with(prompt={"id": "pmpt_abc"}), "prompt"),
    (_with(text={"format": {"type": "json_schema", "name": "n", "schema": {}}}), "text.format"),
    (_with(tools=[{"type": "web_search"}]), "'web_search'"),
    (_with(tools=[{"type": "file_search", "vector_store_ids": ["vs_1"]}]), "'file_search'"),
    (_with(tools=[{"type": "computer_use_preview"}]), "'computer_use_preview'"),
    (_with(tools=[{"type": "code_interpreter", "container": {"type": "auto"}}]),
     "'code_interpreter'"),
    (_with(tools=[{"type": "mcp", "server_label": "s"}]), "'mcp'"),
    (_with(tools=[{"type": "image_generation"}]), "'image_generation'"),
    (_with(tools=[{"type": "custom", "name": "t"}]), "'custom'"),
    (_with(tool_choice={"type": "web_search"}), "tool_choice"),
    (_part("input_image"), "'input_image'"),
    (_part("input_file"), "'input_file'"),
    (_part("input_audio"), "'input_audio'"),
    (_with(input=[{"type": "item_reference", "id": "msg_abc"}]), "'item_reference'"),
    (_with(input=[{"type": "computer_call_output", "call_id": "c"}]), "'computer_call_output'"),
    (_with(input=[{"type": "web_search_call", "id": "ws_1"}]), "'web_search_call'"),
]


@pytest.mark.parametrize("body, names", REFUSED)
def test_each_refused_feature_names_itself_and_sends_nothing(monkeypatch, body, names):
    _refused_cleanly(monkeypatch, body, names)


def test_refusal_names_the_field_in_param(monkeypatch):
    answer, _backend, _ledger = _ask(monkeypatch, "openai", _with(previous_response_id="r"))
    assert answer.body["error"]["param"] == "previous_response_id"
    assert answer.headers["x-request-id"].startswith("req_")


def test_ignored_fields_change_nothing_that_goes_upstream(monkeypatch):
    plain, backend, _ledger = _ask(monkeypatch, "openai", "requests/text.json",
                                   plain=[plain_object("openai", "turn2")])
    extra = {"store": True, "metadata": {"run": "7"}, "reasoning": {"effort": "low"},
             "include": ["reasoning.encrypted_content"], "truncation": "auto", "user": "u1",
             "prompt_cache_key": "k", "service_tier": "auto", "background": False,
             "text": {"format": {"type": "text"}}, "previous_response_id": None}
    answer, loaded, _ledger = _ask(monkeypatch, "openai",
                                   {**support.load("requests/text.json"), **extra},
                                   plain=[plain_object("openai", "turn2")])
    assert answer.status == plain.status == 200
    assert loaded.transport.requests[0]["body"] == backend.transport.requests[0]["body"]
    assert answer.body["store"] is False and answer.body["metadata"] == {"run": "7"}


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_function_call_output_the_conversation_never_produced_is_refused(monkeypatch, provider):
    answer, backend, ledger = _ask(monkeypatch, provider, "requests/orphan_output.json",
                                   plain=[plain_object(provider, "turn2")])
    assert _is_error(answer, 400, "invalid_request_error")
    assert "call_id" in answer.body["error"]["message"]
    assert answer.body["error"]["param"] == "input.3.call_id"
    assert ledger.entries == [] and support.nothing_sent(backend)


def test_function_call_output_after_user_text_is_refused(monkeypatch):
    body = support.load("requests/tool_result.json")
    body["input"].insert(3, {"role": "user", "content": "wait"})
    answer, backend, _ledger = _ask(monkeypatch, "openai", body)
    assert _is_error(answer, 400, "invalid_request_error")
    assert "input.4" in answer.body["error"]["message"] and support.nothing_sent(backend)


def test_unknown_model_with_no_upstream_set_is_not_found(monkeypatch):
    monkeypatch.delenv(gateway_turn.UPSTREAM_ENV, raising=False)
    ledger = SessionLedger()
    answer = gateway_responses.handle(support.load("requests/text.json"), {}, ledger,
                                      environ={})
    assert _is_error(answer, 404, "invalid_request_error")
    assert answer.body["error"]["param"] == "model"
    assert gateway_turn.UPSTREAM_ENV in answer.body["error"]["message"]
    assert ledger.entries == []


@pytest.mark.parametrize("model", ["claude-cli", "codex-cli:gpt-5", "opencode", "serve"])
def test_flattened_prompt_endpoints_are_refused(model):
    answer = gateway_responses.handle(_with(model=model), {}, SessionLedger(), environ={})
    assert _is_error(answer, 400, "invalid_request_error")
    assert "flattened prompt" in answer.body["error"]["message"]
