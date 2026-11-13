"""Falsifiers for the boundary observation, including through the real backends.

Hermetic: transports are injected, so no network and no provider is touched.
Load-bearing: (1) reasoning text does NOT travel by default, because fifteen
call sites take a backend return and one of them seals it into a durable
artifact; (2) it travels when a caller asks, so the gate is a choice and not a
wall; (3) every backend now returns the provider's usage instead of discarding
it, which is what endpoint_registry was already reading and never receiving;
(4) a Gemini thought part stays out of the answer text, which is the defect this
layer exposed in GeminiBackend; (5) an unmapped kind produces a record that
says unmapped rather than one that guesses a schema.
"""
import json

from harness import model_observation as mo
from harness.endpoints import AnthropicBackend, GeminiBackend, OpenAICompatBackend
from harness.model_dialects import ANTHROPIC, GEMINI, OLLAMA, OPENAI

CHAIN = "the private chain of thought"
_MSG = [{"role": "user", "content": "hi"}]


def _tx(obj, status=200):
    """The transport contract hands back a parsed object, as the ladder tests
    already exercise it."""
    def t(method, url, headers, body, timeout):
        return status, obj
    return t


def _chat(backend):
    return backend.chat(_MSG, system="s", max_tokens=16, temperature=0, seed=0)


# --- the retention decision -------------------------------------------------

def test_reasoning_text_does_not_travel_by_default():
    record = mo.observe(
        {"choices": [{"message": {"reasoning_content": CHAIN}}]},
        dialect=OPENAI)
    assert record["reasoning"]["present"] is True
    assert record["reasoning"]["redacted"] is True
    assert CHAIN not in json.dumps(record)


def test_reasoning_text_travels_when_a_caller_asks_for_it():
    record = mo.observe(
        {"choices": [{"message": {"reasoning_content": CHAIN}}]},
        dialect=OPENAI, keep_reasoning=True)
    assert record["reasoning"]["text"] == CHAIN


def test_both_keys_are_always_present_so_no_caller_has_to_branch():
    for dialect in (OPENAI, ANTHROPIC, GEMINI, OLLAMA, None):
        record = mo.observe({}, dialect=dialect)
        assert set(record) == {"usage", "reasoning"}


def test_an_unmapped_kind_says_unmapped_rather_than_guessing_a_schema():
    assert mo.dialect_for("cohere") is None
    record = mo.observe({"usage": {"prompt_tokens": 100}}, dialect=None)
    assert record["usage"]["provenance"] == "absent"
    assert "UNMAPPED" in record["usage"]["refused"]
    assert "counts" not in record["usage"]


def test_dialect_for_maps_the_compatible_servers_onto_the_openai_schema():
    for kind in ("openai", "deepseek", "vllm", "llamacpp", "openrouter"):
        assert mo.dialect_for(kind) == OPENAI
    assert mo.dialect_for("anthropic") == ANTHROPIC
    assert mo.dialect_for("gemini") == GEMINI
    assert mo.dialect_for("ollama") == OLLAMA
    assert mo.dialect_for(None) is None


def test_attach_adds_the_keys_and_leaves_the_existing_return_alone():
    out = {"text": "hi", "model_ref": "a:b", "seed": 1}
    same = mo.attach(out, {}, dialect=OPENAI)
    assert same is out
    assert out["text"] == "hi"
    assert "usage" in out and "reasoning" in out


# --- through the real backends ----------------------------------------------

def test_openai_backend_now_returns_the_providers_usage():
    """endpoint_registry already read out['usage'] into ProposerOutput. No
    backend had ever put it there."""
    backend = OpenAICompatBackend(
        "deepseek", "http://x", "deepseek-chat", key_env="NONE", api_key="k",
        transport=_tx({"model": "deepseek-chat-v3",
                       "choices": [{"message": {"content": "ok",
                                                "reasoning_content": CHAIN}}],
                       "usage": {"prompt_tokens": 100, "completion_tokens": 50,
                                 "prompt_tokens_details": {"cached_tokens": 40}}}))
    out = _chat(backend)
    assert out["text"] == "ok"
    assert out["usage"]["counts"] == {"input": 100, "output": 50, "cache_read": 40}
    assert out["usage"]["served_model"] == "deepseek-chat-v3"
    assert out["usage"]["served_matches_requested"] is False


def test_anthropic_backend_returns_usage_and_withholds_the_thinking_text():
    backend = AnthropicBackend(
        "anthropic", "http://x", "claude-sonnet-4", key_env="NONE", api_key="k",
        transport=_tx({"model": "claude-sonnet-4",
                       "content": [{"type": "thinking", "thinking": CHAIN},
                                   {"type": "text", "text": "ok"}],
                       "usage": {"input_tokens": 100, "output_tokens": 50,
                                 "cache_read_input_tokens": 40}}))
    out = _chat(backend)
    assert out["text"] == "ok"
    assert out["usage"]["counts"]["cache_read"] == 40
    assert out["reasoning"]["present"] is True
    assert CHAIN not in json.dumps(out)


def test_gemini_backend_keeps_the_thought_part_out_of_the_answer():
    """Joining every part put the chain of thought inside the returned text,
    where every caller downstream stored it as the reply."""
    backend = GeminiBackend(
        "gemini", "http://x", "gemini-2.5-flash", key_env="NONE", api_key="k",
        transport=_tx({"modelVersion": "gemini-2.5-flash-002",
                       "candidates": [{"content": {"parts": [
                           {"text": CHAIN, "thought": True},
                           {"text": "ok"}]}}],
                       "usageMetadata": {"promptTokenCount": 100,
                                         "candidatesTokenCount": 50,
                                         "thoughtsTokenCount": 30,
                                         "totalTokenCount": 180}}))
    out = _chat(backend)
    assert out["text"] == "ok"
    assert CHAIN not in json.dumps(out)
    assert out["usage"]["counts"]["reasoning"] == 30


def test_gemini_backend_carries_the_reasoning_text_when_asked():
    backend = GeminiBackend(
        "gemini", "http://x", "gemini-2.5-flash", key_env="NONE", api_key="k",
        keep_reasoning=True,
        transport=_tx({"candidates": [{"content": {"parts": [
            {"text": CHAIN, "thought": True}, {"text": "ok"}]}}]}))
    out = _chat(backend)
    assert out["text"] == "ok"
    assert out["reasoning"]["text"] == CHAIN


def test_a_provider_that_sent_no_usage_reports_absent_not_zero():
    backend = OpenAICompatBackend(
        "local", "http://x", "qwen", key_env="NONE", api_key="k",
        transport=_tx({"choices": [{"message": {"content": "ok"}}]}))
    out = _chat(backend)
    assert out["usage"]["provenance"] == "absent"
    assert out["usage"]["reported"] is None
    assert "counts" not in out["usage"]
