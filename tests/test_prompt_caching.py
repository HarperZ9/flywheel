"""Provider prompt caching: what is sent, and what is reported back.

Replies are replayed; no test calls a provider. The token counts asserted
here are the ones written into the replayed replies, read back through the
provider's own usage fields. Sources for those fields and for the request
marks are in harness/endpoints_cache.py.

Not run: token counts with caching on and off for a fixed 20-turn script
against a live provider. That measurement needs paid calls.
"""
import copy
import json

import pytest

from harness import endpoints_cache
from harness.code_session import slash
from harness.code_session.backends import build_agent
from harness.code_session.session import new_session
from harness.code_session.streaming import streamed_send
from tests.hosted_stream_fixtures import (CALL, MESSAGES, NATIVE, backend, drain, plain_object,
                                          stream_bytes)

MARK = {"type": "ephemeral"}
# One cached reply per provider: the usage block as that provider reports a cache read.
CACHED = {
    "anthropic": {"usage": {"input_tokens": 12, "cache_creation_input_tokens": 96,
                            "cache_read_input_tokens": 1840, "output_tokens": 11}},
    "openai": {"usage": {"prompt_tokens": 1900, "completion_tokens": 9, "total_tokens": 1909,
                         "prompt_tokens_details": {"cached_tokens": 1792}}},
    "gemini": {"usageMetadata": {"promptTokenCount": 4300, "candidatesTokenCount": 10,
                                 "totalTokenCount": 4310, "cachedContentTokenCount": 4096}},
}
WANT = {"anthropic": {"cache_read_tokens": 1840, "cache_write_tokens": 96},
        "openai": {"cache_read_tokens": 1792},
        "gemini": {"cache_read_tokens": 4096}}


def _cached(provider: str, name: str = "turn2") -> dict:
    return {**copy.deepcopy(plain_object(provider, name)), **copy.deepcopy(CACHED[provider])}


def _session(tmp_path, made, *, cache=True, native="off"):
    session = new_session(build_agent([made]), str(tmp_path), mode="auto",
                          runner=lambda cmd, root: (True, "[exit 0]"))
    session.toolbox.cache, session.toolbox.mode = cache, native
    return session


@pytest.mark.parametrize("provider", sorted(CACHED))
def test_cache_counts_come_from_the_providers_usage_fields(tmp_path, provider):
    made = backend(provider, plain=[_cached(provider)])
    session = _session(tmp_path, made)
    result = session.turn("what changed?")
    for key, value in WANT[provider].items():
        assert session.usage[key] == value and result.usage[key] == value
    assert set(session.usage) - {"model_calls", "input_tokens", "output_tokens",
                                 "uncounted_calls"} == set(WANT[provider])
    said = slash.dispatch(session, "/cost")
    assert f"{WANT[provider]['cache_read_tokens']} read from cache" in said
    assert ("written to cache" in said) is ("cache_write_tokens" in WANT[provider])


@pytest.mark.parametrize("provider", sorted(CACHED))
def test_a_reply_with_no_cache_figure_reports_none(tmp_path, provider):
    """Control: a count appears only when the provider sent one. Zero is never made up."""
    made = backend(provider, plain=[plain_object(provider, "turn2")])
    session = _session(tmp_path, made)
    session.turn("what changed?")
    assert "cache_read_tokens" not in session.usage and "cache_write_tokens" not in session.usage
    assert "cache" not in slash.dispatch(session, "/cost")
    gen = backend(provider, plain=[plain_object(provider, "turn2")]).chat(MESSAGES, **CALL)
    assert set(gen["token_usage"]) == {"input_tokens", "output_tokens"}


def test_cache_counts_add_up_across_calls_and_a_malformed_count_is_left_out(tmp_path):
    bad = _cached("anthropic")
    bad["usage"]["cache_read_input_tokens"] = "1840"          # a string is not a count
    made = backend("anthropic", plain=[_cached("anthropic", "turn1"), _cached("anthropic"), bad])
    session = _session(tmp_path, made)
    session.turn("write a note")                              # two model calls
    assert session.usage["cache_read_tokens"] == 3680 and session.usage["cache_write_tokens"] == 192
    session.turn("again")
    assert session.usage["cache_read_tokens"] == 3680         # the third reply added nothing
    assert session.usage["cache_write_tokens"] == 192         # and no part of its cache figure
    assert session.usage["uncounted_calls"] == 0              # its input and output still count


def test_anthropic_requests_carry_two_marks_and_other_providers_none(tmp_path):
    sent = {}
    for provider in sorted(CACHED):
        made = backend(provider, plain=[_cached(provider)])
        (tmp_path / provider).mkdir()
        _session(tmp_path / provider, made).turn("what changed?")
        sent[provider] = made.transport.requests[0]["body"]
    body = sent["anthropic"]
    assert body["cache_control"] == MARK
    assert [b["cache_control"] for b in body["system"]] == [MARK] and len(body["system"]) == 1
    assert body["system"][0]["type"] == "text" and body["system"][0]["text"].startswith("You are")
    assert json.dumps(body).count('"cache_control"') == 2     # within the provider's limit of 4
    assert isinstance(body["messages"][0]["content"], str)    # the conversation is untouched
    for provider in ("openai", "gemini"):
        assert "cache_control" not in json.dumps(sent[provider])


def test_the_marks_ride_with_native_tools_and_keep_the_tools_in_the_cached_prefix(tmp_path):
    made = backend("anthropic", plain=[_cached("anthropic", NATIVE["anthropic"]),
                                       _cached("anthropic")])
    _session(tmp_path, made, native="on").turn("write a note")
    first, second = [r["body"] for r in made.transport.requests]
    for body in (first, second):
        assert body["cache_control"] == MARK and body["tools"]
        assert body["system"][0]["cache_control"] == MARK
        assert body["system"][0]["text"].endswith("do not write TOOL lines yourself.")
        assert "cache_control" not in json.dumps(body["tools"])
    assert first["system"] == second["system"] and first["tools"] == second["tools"]


def test_the_switch_and_a_backend_outside_a_session_send_no_marks(tmp_path, monkeypatch):
    made = backend("anthropic", plain=[_cached("anthropic")])
    session = _session(tmp_path, made, cache=False)
    session.turn("what changed?")
    assert "cache_control" not in json.dumps(made.transport.requests[0]["body"])
    assert session.usage["cache_read_tokens"] == 1840         # still reported when it happens
    outside = backend("anthropic", plain=[_cached("anthropic")])
    outside.chat(MESSAGES, **CALL)
    assert "cache_control" not in json.dumps(outside.transport.requests[0]["body"])
    assert endpoints_cache.on_from_env({}) is True
    assert endpoints_cache.on_from_env({"FLYWHEEL_PROMPT_CACHE": "0"}) is False
    monkeypatch.setenv("FLYWHEEL_PROMPT_CACHE", "0")
    fresh = new_session(build_agent([backend("anthropic")]), str(tmp_path), mode="auto")
    assert fresh.toolbox.cache is False


def test_the_config_hash_records_the_switch(tmp_path):
    hashes = []
    for cache in (True, False):
        made = backend("anthropic", plain=[_cached("anthropic")])
        session = _session(tmp_path, made, cache=cache)
        session.turn("what changed?")
        config = json.loads(session.ledger.entries[-1].content)
        assert config["prompt_cache"] is cache
        hashes.append(session.config_sha256)
    assert hashes[0] != hashes[1]


def test_a_host_that_refuses_cache_control_is_asked_again_without_it(tmp_path, monkeypatch,
                                                                    caplog):
    monkeypatch.setattr(endpoints_cache, "_NO_CACHE", set())
    refusal = (400, {"error": {"type": "invalid_request_error",
                               "message": "cache_control: Extra inputs are not permitted"}})
    made = backend("anthropic", plain=[refusal, _cached("anthropic"), _cached("anthropic")])
    session = _session(tmp_path, made)
    with caplog.at_level("WARNING", logger="harness.endpoints_cache"):
        assert session.turn("what changed?").final.startswith("Wrote n.txt.")
    session.turn("and now?")
    marks = ["cache_control" in json.dumps(r["body"]) for r in made.transport.requests]
    assert marks == [True, False, False] and "refused cache_control" in caplog.text


def test_a_streamed_reply_reports_the_same_cache_counts(tmp_path):
    plain_usage = CACHED["anthropic"]["usage"]
    start = {k: v for k, v in plain_usage.items() if k != "output_tokens"}
    stream = stream_bytes("anthropic", "turn2").replace(
        b'"usage":{"input_tokens":468,"output_tokens":1}',
        ('"usage":' + json.dumps({**start, "output_tokens": 1})).encode()).replace(
        b'"usage":{"output_tokens":11}',
        ('"usage":' + json.dumps(plain_usage)).encode())
    assert stream.count(b"cache_read_input_tokens") == 2
    made = backend("anthropic", streams=[stream], plain=[_cached("anthropic")])
    _pieces, streamed = drain(made.chat_streamed(MESSAGES, **CALL))
    plain = made.chat(MESSAGES, **CALL)
    assert streamed["token_usage"] == plain["token_usage"] == {
        "input_tokens": 12, "output_tokens": 11, **WANT["anthropic"]}
    session = _session(tmp_path, backend("anthropic", streams=[stream]))
    with streamed_send(session.agent, lambda piece: None):
        session.turn("what changed?")
    assert session.usage["cache_read_tokens"] == 1840
    request = session.agent.backends[0].stream_transport.requests[0]["body"]
    assert request["cache_control"] == MARK and request["stream"] is True
