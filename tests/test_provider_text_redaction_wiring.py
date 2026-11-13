"""Provider text is scrubbed and gated on the paths that keep or print it.

Hermetic: transports are injected and no provider is touched. Every key here is
assembled at run time, so no credential-shaped literal sits in the source.

Load-bearing: (1) a key-shaped string in a usage block, a served model name or
kept reasoning text does not reach the record; (2) a clean record is exactly
what model_usage produced; (3) the error a hosted backend raises carries a
scrubbed body, and the budget reader still finds the limit through the narrow
field; (4) the request-gate reading names why a figure is absent and holds none
of the request's content.
"""
import json

import pytest

from harness import model_observation as mo
from harness import model_reasoning, model_usage
from harness.endpoint_opencode import OpenCodeBackend
from harness.endpoints import GeminiBackend, OpenAICompatBackend
from harness.endpoints_http import _guard, _response_error
from harness.limit_signal import provider_body_limit
from harness.local_agent import BackendError
from harness.model_dialects import OPENAI
from harness.provider_fault_boundary import limit_fields
from harness.run_budget_executor import BudgetedProposer

KEY = "sk-" + "ant-" + "x" * 40
PROJECT_KEY = "sk-" + "proj-" + "A" * 32
_MSG = [{"role": "user", "content": "the private prompt"}]


def _tx(obj, status=200):
    return lambda method, url, headers, body, timeout: (status, obj)


def _chat(backend):
    return backend.chat(_MSG, system="s", max_tokens=16, temperature=0, seed=0)


def test_a_key_in_the_usage_block_or_model_name_never_reaches_the_record():
    response = {"model": "gpt-x " + KEY,
                "usage": {"prompt_tokens": 3, "completion_tokens": 4,
                          "total_tokens": 7, "service_tier": KEY},
                "choices": [{"message": {"content": "ok"}}]}
    record = mo.observe(response, dialect=OPENAI)
    assert KEY not in json.dumps(record)
    assert record["usage"]["redacted_kinds"] == ["anthropic_api_key"]
    assert record["usage"]["reported"]["total_tokens"] == 7
    assert record["usage"]["counts"]["input"] == 3


def test_a_clean_usage_record_is_exactly_what_model_usage_produced():
    response = {"model": "gpt-x", "usage": {"prompt_tokens": 3,
                                            "completion_tokens": 4,
                                            "total_tokens": 7}}
    record = mo.observe(response, dialect=OPENAI, requested_model="gpt-x")
    assert record["usage"] == model_usage.capture(
        response, dialect=OPENAI, requested_model="gpt-x")
    assert "redacted_kinds" not in record["usage"]


def test_kept_reasoning_is_scrubbed_whole_and_its_digest_stays_on_the_original():
    chain = "step one " * 400 + "the key is " + KEY + " and then the answer"
    response = {"choices": [{"message": {"reasoning_content": chain}}]}
    reasoning = mo.observe(response, dialect=OPENAI,
                           keep_reasoning=True)["reasoning"]
    assert KEY not in reasoning["text"]
    assert reasoning["text"].endswith("and then the answer")   # nothing cut
    assert reasoning["text_redacted_kinds"] == ["anthropic_api_key"]
    assert reasoning["chars"] == len(chain)
    assert model_reasoning.matches(reasoning, chain) is True


def test_kept_reasoning_with_no_key_travels_unchanged():
    response = {"choices": [{"message": {"reasoning_content": "plain chain"}}]}
    reasoning = mo.observe(response, dialect=OPENAI,
                           keep_reasoning=True)["reasoning"]
    assert reasoning["text"] == "plain chain"
    assert "text_redacted_kinds" not in reasoning


def test_gemini_names_the_shut_gate_behind_its_missing_reasoning_text():
    out = _chat(GeminiBackend(
        name="gemini", base_url="https://gemini.invalid", model="g",
        api_key="placeholder", transport=_tx(
            {"candidates": [{"content": {"parts": [{"text": "answer"}]}}],
             "usageMetadata": {"promptTokenCount": 1, "thoughtsTokenCount": 9,
                               "totalTokenCount": 12}})))
    why = out["gates"]["absent"]["reasoning_text"]
    assert why["explained"] is True and why["by"] == ["include_thoughts"]
    assert "usage" not in out["gates"]["absent"]       # usage did come back
    assert "the private prompt" not in json.dumps(out["gates"])


def test_openai_gate_reading_follows_the_backend_kind():
    body = {"choices": [{"message": {"content": "ok"}}]}

    def gate(name):
        out = _chat(OpenAICompatBackend(
            name=name, base_url="https://p.invalid/v1", model="m",
            api_key="placeholder", transport=_tx(body)))
        return out["gates"]["gates"][0], out["gates"]["absent"]["usage"]

    plain, why = gate("codex")
    assert plain["gate"] == "stream_usage"
    assert plain["state"] == "not_applicable"          # the call did not stream
    assert why["explained"] is False                   # so no gate excuses it
    waived, _ = gate("openrouter")
    assert waived["waived_by_kind"] == "openrouter"


def test_no_gate_reading_without_the_request():
    assert "gates" not in mo.observe({}, dialect=OPENAI)


def test_the_error_carries_a_scrubbed_body_and_the_narrow_limit_fields():
    raw = {"error": {"type": "rate_limit_error", "code": "rate_limit_exceeded",
                     "message": "key " + PROJECT_KEY + " is throttled",
                     "param": {"echo": PROJECT_KEY}}}
    error = _response_error("codex", 429, raw, kind="openai")
    carried = json.dumps([error.body, error.limit_fields, error.fault,
                          str(error)])
    assert PROJECT_KEY not in carried
    assert "[redacted:openai_project_key:" in error.body["error"]["message"]
    assert error.limit_fields == {"error": {"type": "rate_limit_error",
                                            "code": "rate_limit_exceeded"}}
    assert provider_body_limit(error.limit_fields) == provider_body_limit(raw)
    assert error.fault["category"] == "rate_limit"


def test_limit_fields_keep_only_strings_and_whole_numbers():
    assert limit_fields({"error": {"type": ["x"], "code": True, "status": 429,
                                   "message": "free text"}}) == {
        "error": {"status": 429}}
    assert limit_fields({"error": "bare string"}) == {}
    assert limit_fields(None) == {}


def test_the_budget_reader_finds_the_limit_through_the_narrow_field():
    seen = []

    class Budget:
        def charge_model_call(self): pass
        def record_usage(self, usage): pass
        def observe_provider_response(self, status, body):
            seen.append((status, body))

    class Inner:
        def generate(self, prompt, **kwargs):
            raise _response_error(
                "codex", 200, {"error": {"type": "insufficient_quota",
                                         "message": "key " + PROJECT_KEY}})

    with pytest.raises(BackendError):
        BudgetedProposer(Inner(), Budget()).generate("p")
    status, body = seen[0]
    assert status == 200
    assert body == {"error": {"type": "insufficient_quota"}}
    assert provider_body_limit(body) is not None       # a 200 with a limit inside


def test_an_unreachable_host_error_is_scrubbed():
    def refuse(*_args):
        raise OSError("proxy rejected Authorization: Bearer " + PROJECT_KEY)

    with pytest.raises(BackendError) as exc:
        _guard(refuse, "POST", "https://p.invalid", {}, b"", 1.0, "codex")
    assert PROJECT_KEY not in str(exc.value)
    assert "codex unreachable" in str(exc.value)


def test_an_empty_reply_does_not_quote_a_key_from_finish_reason():
    backend = OpenAICompatBackend(
        name="codex", base_url="https://p.invalid/v1", model="m",
        api_key="placeholder", transport=_tx(
            {"choices": [{"message": {"content": None},
                          "finish_reason": "blocked " + PROJECT_KEY}]}))
    with pytest.raises(BackendError) as exc:
        _chat(backend)
    assert PROJECT_KEY not in str(exc.value)
    assert "no message content" in str(exc.value)


def test_an_opencode_server_error_is_read_and_scrubbed():
    backend = OpenCodeBackend(
        name="opencode-plan", base_url="http://127.0.0.1:9", provider_id="openai",
        model="m", transport=_tx({"error": "bad key " + PROJECT_KEY}, 401))
    with pytest.raises(BackendError) as exc:
        _chat(backend)
    message = str(exc.value)
    assert PROJECT_KEY not in message
    assert "opencode-plan returned 401" in message
    assert "category=auth" in message
