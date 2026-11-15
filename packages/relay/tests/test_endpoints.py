"""Falsifiers for the multi-endpoint ladder (codex/claude/gemini/deepseek).

Hermetic: transports and the CLI runner are injected, so no network and no real
provider is touched. Load-bearing: (1) each provider's native response shape is
parsed to text; (2) a credential-less endpoint is simply absent (health False),
never a silent default; (3) an error response is a typed BackendError; (4) the
CLI (subscription) backend runs the operator's client and surfaces failures;
(5) build_endpoints assembles only the modes whose credentials are present.
"""
import json

import pytest

from relay.endpoints import (
    AnthropicBackend,
    CliBackend,
    GeminiBackend,
    OpenAICompatBackend,
    build_endpoints,
)
from relay.local_agent import BackendError

_MSG = [{"role": "user", "content": "hi"}]


def _tx(status, obj, sink=None):
    def t(method, url, headers, body, timeout):
        if sink is not None:
            sink.update({"url": url, "headers": headers})
        return status, obj
    return t


def test_openai_compat_parses_and_labels():
    b = OpenAICompatBackend("deepseek", "https://api.deepseek.com/v1", "deepseek-chat",
                            key_env="DEEPSEEK_API_KEY",
                            transport=_tx(200, {"choices": [{"message": {"content": "yo"}}]}))
    out = b.chat(_MSG, system="s", max_tokens=10, temperature=0, seed=0)
    assert out["text"] == "yo" and out["model_ref"] == "deepseek:deepseek-chat"


def test_anthropic_parses_content_blocks(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    sink = {}
    b = AnthropicBackend("claude", "https://api.anthropic.com", "claude-sonnet-4-5",
                         transport=_tx(200, {"content": [{"type": "text", "text": "hello"}]}, sink))
    out = b.chat(_MSG, system="be brief", max_tokens=10, temperature=0, seed=0)
    assert out["text"] == "hello"
    assert sink["headers"]["x-api-key"] == "sk-test" and "anthropic-version" in sink["headers"]


def test_hosted_backends_surface_truncation_not_a_fake_end_turn(monkeypatch):
    # A hosted backend's own truncation signal must reach translate_response so a
    # length-cut answer is reported as max_tokens, never relabeled to end_turn.
    from relay.messages_api import translate_response
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    b = AnthropicBackend("claude", "https://api.anthropic.com", "claude-sonnet-4-5",
                         transport=_tx(200, {"content": [{"type": "text", "text": "cut"}],
                                             "stop_reason": "max_tokens"}))
    gen = b.chat(_MSG, system="", max_tokens=1, temperature=0, seed=0)
    assert gen["stop_reason"] == "max_tokens" and gen["seed"] is None
    resp = translate_response(gen, {"prompt": "p", "requested_model": "claude-sonnet-4-5"},
                              gen["model_ref"])
    assert resp["stop_reason"] == "max_tokens"


def test_gemini_parses_candidates():
    b = GeminiBackend("gemini", "https://x/v1beta", "gemini-2.5-flash", key_env="GEMINI_API_KEY",
                      transport=_tx(200, {"candidates": [{"content": {"parts": [{"text": "gm"}]}}]}))
    out = b.chat(_MSG, system="", max_tokens=10, temperature=0, seed=0)
    assert out["text"] == "gm"


def test_error_response_is_typed_backend_error():
    b = OpenAICompatBackend("codex", "https://api.openai.com/v1", "gpt-4o",
                            key_env="OPENAI_API_KEY",
                            transport=_tx(401, {"error": "invalid key"}))
    with pytest.raises(BackendError, match="codex returned 401"):
        b.chat(_MSG, system="", max_tokens=10, temperature=0, seed=0)


def test_non_2xx_with_a_valid_shape_still_fails_over():
    """Success is decided by the HTTP status, not by whether an error body happens to carry the
    success shape. A 429/500 whose JSON still parses as choices[0].message.content must raise so the
    router fails over, never be returned as a completion."""
    b = OpenAICompatBackend("codex", "https://api.openai.com/v1", "gpt-4o", key_env="OPENAI_API_KEY",
                            transport=_tx(429, {"choices": [{"message": {"content": "slow down"}}]}))
    with pytest.raises(BackendError, match="codex returned 429"):
        b.chat(_MSG, system="", max_tokens=10, temperature=0, seed=0)


def test_null_content_raises_instead_of_returning_none():
    """A 200 carrying content:null is not a completion. Returning text=None crashes the turn later,
    OUTSIDE the failover try, so the ladder never gets to try the next endpoint. It must raise."""
    b = OpenAICompatBackend("codex", "https://api.openai.com/v1", "gpt-4o", key_env="OPENAI_API_KEY",
                            transport=_tx(200, {"choices": [{"message": {"content": None}}]}))
    with pytest.raises(BackendError):
        b.chat(_MSG, system="", max_tokens=10, temperature=0, seed=0)


def test_provider_mode_never_sends_the_official_key_to_a_gateway(monkeypatch):
    """provider mode points at an arbitrary <PROVIDER>_PROVIDER_BASE_URL gateway. It must use only
    the dedicated <PROVIDER>_PROVIDER_KEY; it must never fall back to the provider's OFFICIAL API key,
    which would replay the operator's real credential to a third-party URL."""
    monkeypatch.delenv("CODEX_PROVIDER_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-official-secret")
    monkeypatch.setenv("CODEX_PROVIDER_BASE_URL", "https://openrouter.ai/api/v1")
    lad = build_endpoints(providers=["codex"], modes=("provider",), only_configured=False)
    assert [b.name for b in lad] == ["codex-provider"]
    # the gateway backend must NOT carry the official key env
    assert lad[0].key_env != "OPENAI_API_KEY"
    # and with no provider key set, nothing authenticates the gateway with the official secret
    sink = {}
    lad[0].transport = _tx(200, {"choices": [{"message": {"content": "ok"}}]}, sink)
    lad[0].chat(_MSG, system="", max_tokens=1, temperature=0, seed=0)
    assert "sk-official-secret" not in json.dumps(sink.get("headers", {}))


def test_health_gates_on_credential(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert GeminiBackend("gemini", "u", "m").health() is False
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert GeminiBackend("gemini", "u", "m").health() is True


def test_cli_backend_runs_client_and_surfaces_failure():
    ok = CliBackend("claude-max", ["claude", "-p"],
                    runner=lambda cmd, prompt: (0, "answer from cli\n", ""))
    assert ok.chat(_MSG, system="s", max_tokens=10, temperature=0, seed=0)["text"] == "answer from cli"
    # the prompt goes on stdin, never on argv, where a batch shim would reparse it
    seen = {}
    CliBackend("x", ["c", "-p"], runner=lambda cmd, prompt: seen.update(cmd=cmd, prompt=prompt)
               or (0, "", "")).chat(_MSG, system="", max_tokens=1, temperature=0, seed=0)
    assert seen["cmd"] == ["c", "-p"] and "user: hi" in seen["prompt"]
    bad = CliBackend("y", ["c"], runner=lambda cmd, prompt: (1, "", "boom"))
    with pytest.raises(BackendError, match="cli exit 1"):
        bad.chat(_MSG, system="", max_tokens=1, temperature=0, seed=0)


def test_cli_health_is_false_for_missing_binary():
    assert CliBackend("nope", ["definitely_not_on_path_xyz", "{prompt}"]).health() is False


def test_build_endpoints_assembles_only_configured(monkeypatch):
    for v in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
              "CODEX_PROVIDER_BASE_URL"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    lad = build_endpoints(providers=["codex", "deepseek"], modes=("api",))
    names = {b.name for b in lad}
    assert names == {"codex"}                       # deepseek has no key -> absent

    monkeypatch.setenv("CODEX_PROVIDER_BASE_URL", "https://openrouter.ai/api/v1")
    lad2 = build_endpoints(providers=["codex"], modes=("provider",))
    assert [b.name for b in lad2] == ["codex-provider"]


def test_build_endpoints_plan_mode_uses_cli():
    lad = build_endpoints(providers=["claude"], modes=("plan",), only_configured=False)
    assert lad and lad[0].name == "claude-plan" and isinstance(lad[0], CliBackend)


def test_glm_provider_is_openai_compatible(monkeypatch):
    monkeypatch.delenv("GLM_API_KEY", raising=False)
    assert build_endpoints(providers=["glm"], modes=("api",)) == []      # no key -> absent
    monkeypatch.setenv("GLM_API_KEY", "x")
    lad = build_endpoints(providers=["glm"], modes=("api",))
    assert len(lad) == 1 and lad[0].name == "glm"
    assert "bigmodel" in lad[0].base_url and lad[0].model == "glm-4.6"
