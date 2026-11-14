"""The served `usage` field carries the provider's token counts, or null.

In 1.x the gateway chat completion and the agent response put whitespace word
counts in `usage`, where OpenAI and Anthropic clients read tokens. In 2.0
`usage` holds what the provider reported and the word counts sit in
`x_usage_estimate`, named as an estimate. A missing count stays missing.
"""
import pytest

from harness import gateway, token_usage
from harness.code_session.backends import build_agent
from harness.endpoint_registry import BackendProposer
from harness.endpoints import AnthropicBackend, OpenAICompatBackend
from harness.messages_api import translate_response
from harness.proposer import ProposerOutput

PROMPT = "one two three four five"            # five words
REPLY = "alpha beta"                          # two words
ESTIMATE = {"method": "whitespace_words", "prompt_words": 5, "completion_words": 2}


def _transport(obj):
    return lambda method, url, headers, body, timeout: (200, obj)


class _Proposer:
    model_ref = "stub"

    def __init__(self, usage):
        self.usage = usage

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        return ProposerOutput(REPLY, self.model_ref, seed, "h", "stub", usage=self.usage)


def _chat(monkeypatch, proposer):
    monkeypatch.setattr(gateway, "_resolve_proposer", lambda model, url: (proposer, None, 200))
    body, code, *_ = gateway.openai_chat(
        {"model": "flywheel", "messages": [{"role": "user", "content": PROMPT}]}, "http://x")
    assert code == 200
    return body


@pytest.mark.parametrize("kept", [
    {"dialect": "openai", "provenance": "provider_reported",
     "counts": {"input": 1200, "output": 34, "total": 1234}},
    {"prompt_eval_count": 1200, "eval_count": 34},
    {"prompt": 1200, "completion": 34, "total": 1234},
    {"prompt_tokens": 1200, "completion_tokens": 34},
    {"input_tokens": 1200, "output_tokens": 34},
])
def test_gateway_usage_is_the_provider_count_in_every_kept_shape(monkeypatch, kept):
    body = _chat(monkeypatch, _Proposer(kept))
    assert body["usage"] == {"prompt_tokens": 1200, "completion_tokens": 34,
                             "total_tokens": 1234}
    assert body["x_usage_estimate"] == ESTIMATE


@pytest.mark.parametrize("kept", [
    None, {}, {"counts": {"input": 1200}}, {"prompt_tokens": -1, "completion_tokens": 2},
    {"prompt_tokens": "1200", "completion_tokens": 34}, {"prompt": True, "completion": 2},
    {"dialect": "openai", "provenance": "absent", "refused": "USAGE_NOT_AN_OBJECT"},
])
def test_gateway_usage_is_null_when_the_provider_reported_none(monkeypatch, kept):
    """Control: 1.x answered {5, 2, 7} here. A body that still filled `usage`
    from the word count would pass a looser "usage is present" check."""
    body = _chat(monkeypatch, _Proposer(kept))
    assert "usage" in body and body["usage"] is None
    assert body["x_usage_estimate"] == ESTIMATE


def test_the_estimate_never_stands_in_for_the_count(monkeypatch):
    body = _chat(monkeypatch, _Proposer({"prompt_tokens": 1200, "completion_tokens": 34}))
    words = body["x_usage_estimate"]
    assert set(words) == {"method", "prompt_words", "completion_words"}
    assert not {"prompt_tokens", "completion_tokens", "input_tokens"} & set(words)
    assert body["usage"]["prompt_tokens"] != words["prompt_words"]


def test_a_hosted_backend_count_reaches_the_gateway_body(monkeypatch):
    backend = OpenAICompatBackend(
        name="o", base_url="http://x", model="m", api_key="k",
        transport=_transport({"choices": [{"message": {"content": REPLY}}],
                              "usage": {"prompt_tokens": 900, "completion_tokens": 8}}))
    body = _chat(monkeypatch, BackendProposer(backend))
    assert body["usage"] == {"prompt_tokens": 900, "completion_tokens": 8, "total_tokens": 908}


def test_messages_response_usage_is_the_provider_count():
    gen = {"text": REPLY, "token_usage": {"input_tokens": 77, "output_tokens": 9,
                                          "cache_read_tokens": 60}}
    resp = translate_response(gen, {"prompt": PROMPT}, "stub:m")
    assert resp["usage"] == {"input_tokens": 77, "output_tokens": 9}
    assert resp["x_usage_estimate"] == ESTIMATE


def test_messages_response_usage_is_null_without_a_count():
    resp = translate_response({"text": REPLY}, {"prompt": PROMPT}, "stub:m")
    assert "usage" in resp and resp["usage"] is None
    assert resp["x_usage_estimate"] == ESTIMATE


def test_the_agent_response_agrees_with_its_own_token_field():
    backend = AnthropicBackend(
        name="a", base_url="http://x", model="m", api_key="k",
        transport=_transport({"content": [{"type": "text", "text": REPLY}],
                              "usage": {"input_tokens": 11, "output_tokens": 2}}))
    resp = build_agent([backend]).send("hello there")
    assert resp["usage"] == {"input_tokens": 11, "output_tokens": 2}
    assert resp["x_token_usage"] == {"input_tokens": 11, "output_tokens": 2}
    assert resp["x_usage_estimate"]["method"] == token_usage.ESTIMATE_METHOD


def test_an_uncounted_agent_response_has_null_usage_and_no_token_field():
    backend = OpenAICompatBackend(
        name="o", base_url="http://x", model="m", api_key="k",
        transport=_transport({"choices": [{"message": {"content": REPLY}}]}))
    resp = build_agent([backend]).send("hello there")
    assert resp["usage"] is None and "x_token_usage" not in resp


def test_shapes_refuse_a_pair_that_is_not_two_whole_counts():
    for bad in (None, {}, {"input_tokens": 1}, {"input_tokens": 1.5, "output_tokens": 2},
                {"input_tokens": False, "output_tokens": 2}, "7"):
        assert token_usage.openai_usage(bad) is None
        assert token_usage.anthropic_usage(bad) is None
