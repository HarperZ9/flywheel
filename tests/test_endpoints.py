"""Falsifiers for the multi-endpoint ladder (codex/claude/gemini/deepseek).

Hermetic: transports and the CLI runner are injected, so no network and no real
provider is touched. Load-bearing: (1) each provider's native response shape is
parsed to text; (2) a credential-less endpoint is simply absent (health False),
never a silent default; (3) an error response is a typed BackendError; (4) the
CLI (subscription) backend runs the operator's client and surfaces failures;
(5) build_endpoints assembles only the modes whose credentials are present.
"""
import pytest

from harness.endpoints import (
    AnthropicBackend,
    CliBackend,
    GeminiBackend,
    OpenAICompatBackend,
    OpenCodeBackend,
    build_endpoints,
)
from harness.local_agent import BackendError

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


def test_gemini_parses_candidates():
    b = GeminiBackend("gemini", "https://x/v1beta", "gemini-2.5-flash", key_env="GEMINI_API_KEY",
                      transport=_tx(200, {"candidates": [{"content": {"parts": [{"text": "gm"}]}}]}))
    out = b.chat(_MSG, system="", max_tokens=10, temperature=0, seed=0)
    assert out["text"] == "gm"


def test_gemini_key_in_header_never_in_url(monkeypatch):
    # Falsifier: a query-string key leaks into access/proxy logs and history. The
    # key must ride the x-goog-api-key HEADER and NEVER appear in the request URL.
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-canary-secret-value")
    sink = {}
    b = GeminiBackend("gemini", "https://x/v1beta", "gemini-2.5-flash", key_env="GEMINI_API_KEY",
                      transport=_tx(200, {"candidates": [{"content": {"parts": [{"text": "gm"}]}}]}, sink))
    b.chat(_MSG, system="", max_tokens=10, temperature=0, seed=0)
    assert sink["headers"]["x-goog-api-key"] == "AIza-canary-secret-value"
    assert "AIza-canary-secret-value" not in sink["url"], "key leaked into the URL"
    assert "?key=" not in sink["url"] and "key=" not in sink["url"]


def test_error_response_is_typed_backend_error():
    b = OpenAICompatBackend("codex", "https://api.openai.com/v1", "gpt-4o",
                            key_env="OPENAI_API_KEY",
                            transport=_tx(401, {"error": "invalid key"}))
    with pytest.raises(BackendError, match="codex returned 401"):
        b.chat(_MSG, system="", max_tokens=10, temperature=0, seed=0)


def test_health_gates_on_credential(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert GeminiBackend("gemini", "u", "m").health() is False
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert GeminiBackend("gemini", "u", "m").health() is True


def test_cli_backend_runs_client_and_surfaces_failure():
    ok = CliBackend("claude-max", ["claude", "-p", "{prompt}"],
                    runner=lambda cmd: (0, "answer from cli\n", ""))
    assert ok.chat(_MSG, system="s", max_tokens=10, temperature=0, seed=0)["text"] == "answer from cli"
    # the prompt placeholder is substituted, not passed literally
    seen = {}
    CliBackend("x", ["c", "{prompt}"], runner=lambda cmd: seen.update(cmd=cmd) or (0, "", "")
               ).chat(_MSG, system="", max_tokens=1, temperature=0, seed=0)
    assert "{prompt}" not in seen["cmd"] and any("user: hi" in a for a in seen["cmd"])
    bad = CliBackend("y", ["c", "{prompt}"], runner=lambda cmd: (1, "", "boom"))
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


def test_opencode_plan_uses_desktop_server_env_aliases(monkeypatch):
    for name in (
        "OPENCODE_BASE_URL",
        "OPENCODE_PASSWORD",
        "OPENCODE_USERNAME",
        "OPENCODE_PORT",
        "OPENCODE_SERVER_PASSWORD",
        "OPENCODE_SERVER_USERNAME",
    ):
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setenv("OPENCODE_PORT", "4096")
    monkeypatch.setenv("OPENCODE_SERVER_USERNAME", "opencode")
    monkeypatch.setenv("OPENCODE_SERVER_PASSWORD", "sidecar-secret")
    lad = build_endpoints(providers=["opencode"], modes=("plan",))

    assert len(lad) == 1
    assert isinstance(lad[0], OpenCodeBackend)
    assert lad[0].base_url == "http://127.0.0.1:4096"
    assert lad[0].health() is True
    assert "Authorization" in lad[0]._headers()


def test_direct_api_key_overrides_ambient_credential(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ambient-marker-must-not-be-used")
    sink = {}
    backend = AnthropicBackend(
        "claude", "https://api.anthropic.com", "model", api_key="exact-value",
        transport=_tx(200, {"content": [{"type": "text", "text": "ok"}]}, sink))
    backend.chat(_MSG, system="", max_tokens=8, temperature=0, seed=0)
    assert sink["headers"]["x-api-key"] == "exact-value"
    assert "exact-value" not in repr(backend)


def test_explicit_empty_key_never_falls_back_to_ambient(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-marker-must-not-be-used")
    sink = {}
    backend = OpenAICompatBackend(
        "local", "http://127.0.0.1:9/v1", "model", key_env="OPENAI_API_KEY",
        api_key="", transport=_tx(
            200, {"choices": [{"message": {"content": "ok"}}]}, sink))
    backend.chat(_MSG, system="", max_tokens=8, temperature=0, seed=0)
    assert "Authorization" not in sink["headers"]


def test_ox_alpha_dormant_without_key(monkeypatch):
    # The slot points at OpenRouter's OpenAI-compatible API, but stays OFF
    # the ladder until the operator sets OX_ALPHA_API_KEY. No credential,
    # no dispatch, never a silent default.
    for v in ("OX_ALPHA_API_KEY", "OX_ALPHA_BASE_URL", "OX_ALPHA_MODEL"):
        monkeypatch.delenv(v, raising=False)
    assert build_endpoints(providers=["ox-alpha"],
                           modes=("api", "provider", "cloud")) == []


def test_ox_alpha_joins_ladder_when_configured(monkeypatch):
    monkeypatch.setenv("OX_ALPHA_API_KEY", "k")
    lad = build_endpoints(providers=["ox-alpha"], modes=("api",))
    assert [b.name for b in lad] == ["ox-alpha"]
    b = lad[0]
    sink = {}
    b.transport = _tx(200, {"choices": [{"message": {"content": "hey"}}]}, sink)
    out = b.chat(_MSG, system="", max_tokens=8, temperature=0, seed=0)
    assert out["text"] == "hey"
    assert out["model_ref"] == "ox-alpha:stealth/ox-alpha"
    assert sink["url"].startswith(
        "https://openrouter.ai/api/v1/chat/completions")
    assert sink["headers"]["Authorization"] == "Bearer k"


def test_ox_alpha_model_and_base_overridable(monkeypatch):
    monkeypatch.setenv("OX_ALPHA_API_KEY", "k")
    monkeypatch.setenv("OX_ALPHA_MODEL", "stealth/ox-alpha-next")
    monkeypatch.setenv("OX_ALPHA_BASE_URL", "https://gateway.example/v1")
    lad = build_endpoints(providers=["ox-alpha"], modes=("api",))
    sink = {}
    lad[0].transport = _tx(200, {"choices": [{"message": {"content": "x"}}]},
                           sink)
    lad[0].chat(_MSG, system="", max_tokens=4, temperature=0, seed=0)
    assert sink["url"].startswith("https://gateway.example/v1/chat/completions")


def test_openai_compat_null_content_is_a_typed_error_not_none_text():
    # Reasoning models can spend the whole completion budget and return
    # content: null with HTTP 200. The backend must refuse honestly instead
    # of returning text=None and letting the loop ship an empty reply.
    b = OpenAICompatBackend("ox-alpha", "https://openrouter.ai/api/v1",
                            "stealth/ox-alpha", key_env="OX_ALPHA_API_KEY",
                            transport=_tx(200, {"choices": [{"message": {
                                "role": "assistant", "content": None}}]}))
    with pytest.raises(BackendError):
        b.chat(_MSG, system="", max_tokens=8, temperature=0, seed=0)
