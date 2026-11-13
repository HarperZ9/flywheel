"""Provider fault readers are wired at existing model-call boundaries."""
from __future__ import annotations

import io
import json
import urllib.error

import pytest

from harness.endpoints import CliBackend, OpenAICompatBackend
from harness.local_agent import BackendError
from harness.proposer import EnterpriseProposer

PROJECT_KEY = "sk-proj-" + "A" * 32
OPENROUTER_KEY = "sk-or-v1-" + "B" * 32


def _http_error(status: int, body: dict, headers: dict | None = None):
    return urllib.error.HTTPError(
        "https://provider.invalid/v1/chat/completions",
        status,
        "provider failed",
        headers or {},
        io.BytesIO(json.dumps(body).encode("utf-8")),
    )


def test_enterprise_http_error_is_redacted_and_carries_advisory_deadline(monkeypatch):
    def fail(_request, timeout=300):
        raise _http_error(
            401,
            {"error": {"message": f"Incorrect API key provided: {PROJECT_KEY}",
                         "code": "invalid_api_key"}},
            {"retry-after": "7"},
        )

    monkeypatch.setattr("urllib.request.urlopen", fail)
    proposer = EnterpriseProposer(
        base_url="https://provider.invalid/v1", model="gpt-x",
        api_key="not-the-failing-key", model_ref="openai")

    with pytest.raises(BackendError) as exc:
        proposer.generate("prompt", seed=1, temperature=0, max_new_tokens=8)

    message = str(exc.value)
    assert PROJECT_KEY not in message
    assert "[redacted:openai_project_key:" in message
    assert "provider fault" in message
    assert "status=401" in message
    assert "category=auth" in message
    assert "retriable=False" in message
    assert "retry-after relative_seconds=7.0s" in message


def test_openrouter_body_code_is_not_reported_as_transport_status():
    backend = OpenAICompatBackend(
        name="openrouter", base_url="https://openrouter.invalid/v1",
        model="auto", api_key="not-secret",
        transport=lambda *_args: (
            200,
            {"error": {"code": 429,
                         "message": f"upstream throttled {OPENROUTER_KEY}"}},
        ),
    )

    with pytest.raises(BackendError) as exc:
        backend.chat([{"role": "user", "content": "hi"}], system="",
                     max_tokens=8, temperature=0, seed=2)

    message = str(exc.value)
    assert OPENROUTER_KEY not in message
    assert "[redacted:openrouter_api_key:" in message
    assert "status=200" in message
    assert "body_code=429" in message
    assert "OPENROUTER_CODE_IS_NOT_THE_STATUS_LINE" in message


def test_retry_and_deadline_observations_do_not_trigger_automatic_retry(monkeypatch):
    calls = 0

    def fail(_request, timeout=300):
        nonlocal calls
        calls += 1
        raise _http_error(
            429,
            {"error": {"message": "slow down", "code": "rate_limit_exceeded"}},
            {"retry-after": "3"},
        )

    monkeypatch.setattr("urllib.request.urlopen", fail)
    proposer = EnterpriseProposer(
        base_url="https://provider.invalid/v1", model="gpt-x",
        api_key="placeholder", model_ref="openai")

    with pytest.raises(BackendError) as exc:
        proposer.generate("prompt", seed=3, temperature=0, max_new_tokens=8)

    assert calls == 1
    message = str(exc.value)
    assert "category=rate_limit" in message
    assert "retriable=True" in message
    assert "retry-after relative_seconds=3.0s" in message


def test_cli_backend_redacts_stderr_before_raising():
    backend = CliBackend(
        "claude-plan", ["claude", "-p", "{prompt}"], "claude-sonnet",
        runner=lambda _cmd: (1, "", f"bad provider key {PROJECT_KEY}"),
    )

    with pytest.raises(BackendError) as exc:
        backend.chat([{"role": "user", "content": "hi"}], system="",
                     max_tokens=8, temperature=0, seed=4)

    message = str(exc.value)
    assert PROJECT_KEY not in message
    assert "[redacted:openai_project_key:" in message
