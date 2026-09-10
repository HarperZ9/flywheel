"""Native Codex selection must reach argv without invoking a real CLI."""
import pytest

from harness import endpoint_registry, endpoints


@pytest.fixture
def ladder(monkeypatch):
    monkeypatch.delenv("CODEX_MODEL", raising=False)
    monkeypatch.delenv("CODEX_CLI", raising=False)
    build = endpoints.build_endpoints
    monkeypatch.setattr(endpoints, "build_endpoints", lambda **kw: build(
        providers=["codex"], modes=("plan",), only_configured=False))


def test_real_native_ladder_forwards_explicit_model(ladder):
    proposer = endpoint_registry.make_endpoint_proposer(
        "codex-cli", model="gpt-6-astra", extract=False)
    commands = []
    proposer.backend.runner = lambda cmd: (commands.append(cmd) or (0, "ok", ""))
    proposer.generate("test prompt", seed=1, temperature=0, max_new_tokens=8)
    assert proposer.backend.name == "codex-plan"
    assert commands[0][commands[0].index("--model") + 1] == "gpt-6-astra"
    assert "{model}" not in commands[0]
    for token in ("--sandbox", "read-only", "--ephemeral", "--output-last-message"):
        assert token in commands[0]


@pytest.mark.parametrize("override", [None, ""])
def test_default_preserves_environment(ladder, monkeypatch, override):
    monkeypatch.setenv("CODEX_MODEL", "configured-model")
    b = endpoint_registry.make_endpoint_proposer("codex-cli", model=override).backend
    assert b.model == "configured-model"


def test_default_preserves_builtin(ladder):
    assert endpoint_registry.make_endpoint_proposer("codex-cli").backend.model == (
        endpoints.PROVIDERS["codex"]["model"])


def test_override_does_not_mutate_shared_backend(monkeypatch):
    original = endpoints.CliBackend("codex-plan", ["codex", "exec", "--model",
                                                 "{model}", "{prompt}"], "original")
    monkeypatch.setattr(endpoints, "build_endpoints", lambda **kw: [original])
    first = endpoint_registry.make_endpoint_proposer("codex-cli", model="gpt-6-astra")
    other = endpoint_registry.make_endpoint_proposer("codex-cli", model="another-model")
    second = endpoint_registry.make_endpoint_proposer("codex-cli")
    assert first.backend.model == "gpt-6-astra"
    assert second.backend is original and original.model == "original"
    assert first.backend.argv == original.argv and first.backend.argv is not original.argv
    assert other.backend.model == "another-model" and first.backend.model == "gpt-6-astra"


@pytest.mark.parametrize("tail", [
    ["{prompt}"], ["--model={model}", "{prompt}"],
    ["{model}", "{prompt}"], ["--", "--model", "{model}", "{prompt}"],
    ["{prompt}", "--model", "{model}"],
    ["--model", "{model}", "--model", "other", "{prompt}"],
    ["--model", "{model}", "--model=other", "{prompt}"],
    ["--model", "{model}", "-mother", "{prompt}"],
    ["--model", "{model}", "--output-last-message", "{model}", "{prompt}"],
])
def test_incompatible_template_fails_before_command(monkeypatch, tail):
    calls = []
    backend = endpoints.CliBackend("codex-plan", ["codex", "exec", *tail],
                                   runner=lambda cmd: calls.append(cmd))
    monkeypatch.setattr(endpoints, "build_endpoints", lambda **kw: [backend])
    with pytest.raises(ValueError, match="model"):
        endpoint_registry.make_endpoint_proposer("codex-cli", model="gpt-6-astra")
    assert calls == []


@pytest.mark.parametrize("model", ["bad model", "x\ny", "x&whoami", "x%PATH%", "-m",
                                  "x'", 'x"', "x;", "x|", "x`", "a" * 161, 12])
def test_invalid_model_rejected_at_engine_boundary(ladder, model):
    with pytest.raises(ValueError, match="model"):
        endpoint_registry.make_endpoint_proposer("codex-cli", model=model)


def test_short_model_option_supported(monkeypatch):
    backend = endpoints.CliBackend("codex-plan", ["codex", "exec", "-m", "{model}",
                                                 "--", "{prompt}"])
    monkeypatch.setattr(endpoints, "build_endpoints", lambda **kw: [backend])
    assert endpoint_registry.make_endpoint_proposer(
        "codex-cli", model="org/model:tag@revision+1").backend.model == "org/model:tag@revision+1"
