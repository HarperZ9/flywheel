"""The fault line a person reads says whether to try again, and when.

Hermetic: urlopen is replaced, so no network and no provider is touched.

Load-bearing: (1) a hosted backend's error now carries the retry deadline the
response headers named, which the transport used to drop; (2) a deadline never
moves from one failed response to another; (3) the line ends in one plain
sentence per retry reading; (4) nothing retries; (5) the CLI prints the line;
(6) FLYWHEEL_KEEP_REASONING=1 is the one switch outside code, default off.
"""
import io
import json
import urllib.error

import pytest

from harness import endpoints_http
from harness.code_session.cli import run_turn
from harness.endpoints import AnthropicBackend, GeminiBackend, OpenAICompatBackend
from harness.endpoints_http import _http, _response_error
from harness.local_agent import BackendError
from harness.model_observation import KEEP_REASONING_ENV
from harness.provider_retry_advice import NO_AUTO_RETRY, retry_advice, wait_reading

_MSG = [{"role": "user", "content": "hi"}]


def _fail_with(status, body, headers, calls=None):
    def urlopen(_request, timeout=0):
        if calls is not None:
            calls.append(1)
        raise urllib.error.HTTPError(
            "https://provider.invalid/v1/chat/completions", status, "failed",
            headers, io.BytesIO(json.dumps(body).encode("utf-8")))
    return urlopen


def _backend():
    return OpenAICompatBackend(name="codex", base_url="https://provider.invalid/v1",
                               model="m", api_key="placeholder")


def _chat(backend):
    return backend.chat(_MSG, system="", max_tokens=8, temperature=0, seed=0)


def test_a_hosted_backend_error_states_the_retry_deadline(monkeypatch):
    calls = []
    monkeypatch.setattr("urllib.request.urlopen", _fail_with(
        429, {"error": {"message": "slow down", "code": "rate_limit_exceeded"}},
        {"Retry-After": "30"}, calls))
    with pytest.raises(BackendError) as exc:
        _chat(_backend())
    message = str(exc.value)
    assert "retry-after relative_seconds=30.0s" in message
    assert message.endswith("Trying again could help. The provider asked for a "
                            "wait of 30 seconds first. " + NO_AUTO_RETRY)
    assert exc.value.fault["deadlines"][0]["seconds"] == 30.0
    assert len(calls) == 1                              # read, never acted on


def test_an_anthropic_reset_instant_is_stated_as_a_time_not_a_wait(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _fail_with(
        529, {"type": "error", "error": {"type": "overloaded_error",
                                         "message": "busy"}},
        {"anthropic-ratelimit-requests-reset": "2026-11-13T10:00:00Z"}))
    backend = AnthropicBackend(name="claude", base_url="https://provider.invalid",
                               model="m", api_key="placeholder")
    with pytest.raises(BackendError) as exc:
        _chat(backend)
    assert "The provider named 2026-11-13 10:00:00 UTC as the time its limit " \
           "resets." in str(exc.value)


def test_a_deadline_never_moves_to_another_response(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _fail_with(
        429, {"error": {"code": "rate_limit_exceeded"}}, {"retry-after": "30"}))
    status, obj = _http("POST", "https://provider.invalid", {}, b"{}", 1.0)
    other = _response_error("codex", status, dict(obj), kind="openai")
    assert "retry-after" not in str(other)              # equal body, not the same one
    assert "The provider gave no wait time." in str(other)
    assert endpoints_http._fault_headers(obj) == {}     # and it is read only once


def test_an_injected_transport_reports_no_deadline_it_was_not_given():
    backend = OpenAICompatBackend(
        name="codex", base_url="https://provider.invalid/v1", model="m",
        api_key="placeholder",
        transport=lambda *_a: (500, {"error": {"message": "boom"}}))
    with pytest.raises(BackendError) as exc:
        _chat(backend)
    assert "category=server_error" in str(exc.value)
    assert "Trying again could help. The provider gave no wait time." in str(exc.value)


@pytest.mark.parametrize("record, expected", [
    ({"retriable": True, "deadlines": [{"seconds": 1.0}, {"seconds": 4.5}]},
     "Trying again could help. The provider asked for a wait of 1 second first. "
     + NO_AUTO_RETRY),
    ({"retriable": True, "deadlines": [{"seconds": 4.5}]},
     "Trying again could help. The provider asked for a wait of 4.5 seconds "
     "first. " + NO_AUTO_RETRY),
    ({"retriable": False, "category": "auth", "deadlines": [{"seconds": 7.0}]},
     "Trying again will not help until the credential is replaced or corrected."),
    ({"retriable": False, "category": "quota"},
     "Trying again will not help until the account's quota or billing changes."),
    ({"retriable": False, "category": "server_error",
      "retriable_source": "provider_header"},
     "Trying again will not help: the provider said not to retry."),
    ({"retriable": None, "category": "unknown"},
     "Whether trying again could help is unknown: the provider gave no retry "
     "signal for this failure. " + NO_AUTO_RETRY),
])
def test_the_sentence_for_each_retry_reading(record, expected):
    assert retry_advice(record) == expected


def test_an_unread_deadline_header_never_becomes_a_stated_wait():
    rows = [{"header": "retry-after", "read": False, "verbatim": "soon"}]
    assert wait_reading(rows) == {"seconds": None, "epoch": None}
    assert "gave no wait time" in retry_advice({"retriable": True,
                                                "deadlines": rows})


def test_the_cli_prints_the_fault_line_with_its_advice(capsys):
    line = str(_response_error(
        "codex", 429, {"error": {"code": "rate_limit_exceeded"}}, kind="openai"))

    class Session:
        def turn(self, text):
            raise BackendError(line)

    assert run_turn(Session(), "hi") == 1
    printed = capsys.readouterr().err
    assert printed.strip() == "[error] " + line
    assert "Trying again could help." in printed


@pytest.mark.parametrize("value, kept", [("1", True), ("", False),
                                         ("0", False), ("true", False)])
def test_keep_reasoning_has_one_environment_switch(monkeypatch, value, kept):
    monkeypatch.setenv(KEEP_REASONING_ENV, value)
    for cls in (OpenAICompatBackend, AnthropicBackend, GeminiBackend):
        assert cls(name="n", base_url="https://p.invalid", model="m",
                   api_key="placeholder").keep_reasoning is kept


def test_keep_reasoning_defaults_off_and_an_explicit_choice_wins(monkeypatch):
    monkeypatch.delenv(KEEP_REASONING_ENV, raising=False)
    assert _backend().keep_reasoning is False
    monkeypatch.setenv(KEEP_REASONING_ENV, "1")
    off = OpenAICompatBackend(name="codex", base_url="https://p.invalid/v1",
                              model="m", api_key="placeholder",
                              keep_reasoning=False)
    assert off.keep_reasoning is False


def test_the_environment_switch_lets_reasoning_text_travel(monkeypatch):
    body = {"choices": [{"message": {"content": "ok",
                                     "reasoning_content": "the chain"}}]}
    monkeypatch.setenv(KEEP_REASONING_ENV, "1")
    kept = OpenAICompatBackend(name="codex", base_url="https://p.invalid/v1",
                               model="m", api_key="placeholder",
                               transport=lambda *_a: (200, body))
    assert _chat(kept)["reasoning"]["text"] == "the chain"
    monkeypatch.delenv(KEEP_REASONING_ENV)
    default = OpenAICompatBackend(name="codex", base_url="https://p.invalid/v1",
                                  model="m", api_key="placeholder",
                                  transport=lambda *_a: (200, body))
    assert "text" not in _chat(default)["reasoning"]
