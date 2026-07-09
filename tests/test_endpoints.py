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
