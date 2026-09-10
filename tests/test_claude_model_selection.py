"""Claude CLI model selection must reach the actual process argv."""
import pytest

from harness import endpoint_registry, endpoints
from harness.endpoints import CliBackend
from harness.local_agent import BackendError


_REQUESTED = "claude-opus-4-1-20250805"
_OTHER = "claude-sonnet-4-5-20250929"


@pytest.fixture
def real_claude_plan_ladder(monkeypatch):
    monkeypatch.delenv("CLAUDE_CLI", raising=False)
    monkeypatch.delenv("CLAUDE_MODEL", raising=False)
    build = endpoints.build_endpoints

    def claude_plan_only(**_kwargs):
        return build(
            providers=["claude"],
            modes=("plan",),
            only_configured=False,
        )

    monkeypatch.setattr(endpoints, "build_endpoints", claude_plan_only)


def _model_arg(argv):
    return argv[argv.index("--model") + 1]


def _capture_command(proposer):
    commands = []
    proposer.backend.runner = lambda cmd: commands.append(cmd) or (0, "ok", "")
    out = proposer.generate(
        "route this through the selected model",
        seed=7,
        temperature=0,
        max_new_tokens=16,
    )
    assert out.text == "ok"
    assert len(commands) == 1
    return commands[0]


def test_real_claude_ladder_resolves_the_claude_plan_backend_by_default(
    real_claude_plan_ladder,
):
    proposer = endpoint_registry.make_endpoint_proposer(
        "claude-cli",
        extract=False,
    )

    assert isinstance(proposer.backend, CliBackend)
    assert proposer.backend.name == "claude-plan"
    assert proposer.backend.model == endpoints.PROVIDERS["claude"]["model"]
    assert _model_arg(_capture_command(proposer)) == endpoints.PROVIDERS[
        "claude"
    ]["model"]


def test_real_claude_ladder_forwards_explicit_model_to_cli_argv(
    real_claude_plan_ladder,
):
    proposer = endpoint_registry.make_endpoint_proposer(
        "claude-cli",
        model=_REQUESTED,
        extract=False,
    )
    command = _capture_command(proposer)

    assert isinstance(proposer.backend, CliBackend)
    assert proposer.backend.name == "claude-plan"
    assert _model_arg(command) == _REQUESTED
    assert endpoints.PROVIDERS["claude"]["model"] not in command
    assert "{model}" not in command
    assert command.index("--model") > command.index("-p")


def test_none_and_empty_model_preserve_configured_environment_default(
    monkeypatch,
    real_claude_plan_ladder,
):
    monkeypatch.setenv("CLAUDE_MODEL", "claude-configured-default")
    for override in (None, ""):
        proposer = endpoint_registry.make_endpoint_proposer(
            "claude-cli",
            model=override,
            extract=False,
        )
        assert proposer.backend.model == "claude-configured-default"
        assert _model_arg(_capture_command(proposer)) == "claude-configured-default"


def test_explicit_model_does_not_mutate_shared_claude_plan_backend(monkeypatch):
    shared = CliBackend(
        "claude-plan",
        ["claude", "-p", "{prompt}", "--model", "{model}"],
        "configured-default",
    )
    monkeypatch.setattr(endpoints, "build_endpoints", lambda **_kwargs: [shared])

    first = endpoint_registry.make_endpoint_proposer(
        "claude-cli",
        model=_REQUESTED,
        extract=False,
    )
    second = endpoint_registry.make_endpoint_proposer(
        "claude-cli",
        model=_OTHER,
        extract=False,
    )
    default = endpoint_registry.make_endpoint_proposer(
        "claude-cli",
        extract=False,
    )

    assert first.backend.model == _REQUESTED
    assert second.backend.model == _OTHER
    assert shared.model == "configured-default"
    assert default.backend is shared
    assert _model_arg(_capture_command(first)) == _REQUESTED
    assert _model_arg(_capture_command(second)) == _OTHER
    assert _model_arg(_capture_command(default)) == "configured-default"


def test_invalid_claude_model_ids_are_rejected_safely(
    real_claude_plan_ladder,
):
    invalid_models = [
        "bad model DO_NOT_LEAK",
        "bad;DO_NOT_LEAK",
        "bad\nDO_NOT_LEAK",
        "-bad",
        "a" * 161,
        12,
    ]
    for model in invalid_models:
        with pytest.raises(ValueError) as failure:
            endpoint_registry.make_endpoint_proposer(
                "claude-cli",
                model=model,
                extract=False,
            )
        message = str(failure.value)
        assert "model" in message.lower()
        assert "DO_NOT_LEAK" not in message


def test_custom_claude_command_without_model_placeholder_is_rejected(
    monkeypatch,
    real_claude_plan_ladder,
):
    monkeypatch.setenv("CLAUDE_CLI", "claude -p {prompt}")

    with pytest.raises(ValueError, match="model"):
        endpoint_registry.make_endpoint_proposer(
            "claude-cli",
            model=_REQUESTED,
            extract=False,
        )


def test_custom_claude_command_rejects_undocumented_short_model_option(
    monkeypatch,
    real_claude_plan_ladder,
):
    monkeypatch.setenv("CLAUDE_CLI", "claude -p {prompt} -m {model}")

    with pytest.raises(ValueError, match="model"):
        endpoint_registry.make_endpoint_proposer(
            "claude-cli",
            model=_REQUESTED,
            extract=False,
        )


def test_custom_claude_command_with_duplicate_or_ambiguous_model_is_rejected(
    monkeypatch,
    real_claude_plan_ladder,
):
    bad_commands = [
        "claude -p {prompt} --model {model} --model {model}",
        "claude -p {prompt} --model {model} --model other-default",
        "claude -p {prompt} --model={model}",
        "claude -p {prompt} --model other-default {model}",
    ]
    for command in bad_commands:
        monkeypatch.setenv("CLAUDE_CLI", command)
        with pytest.raises(ValueError, match="model"):
            endpoint_registry.make_endpoint_proposer(
                "claude-cli",
                model=_REQUESTED,
                extract=False,
            )


def test_custom_claude_command_rejects_model_after_argument_boundary(
    monkeypatch,
    real_claude_plan_ladder,
):
    monkeypatch.setenv("CLAUDE_CLI", "claude -p {prompt} -- --model {model}")

    with pytest.raises(ValueError, match="model"):
        endpoint_registry.make_endpoint_proposer(
            "claude-cli",
            model=_REQUESTED,
            extract=False,
        )


def test_cli_failure_does_not_retry_with_the_default_model(
    real_claude_plan_ladder,
):
    proposer = endpoint_registry.make_endpoint_proposer(
        "claude-cli",
        model=_REQUESTED,
        extract=False,
    )
    commands = []

    def failing_runner(cmd):
        commands.append(cmd)
        return 1, "", "provider refused requested model"

    proposer.backend.runner = failing_runner

    with pytest.raises(BackendError, match="claude-plan cli exit 1"):
        proposer.generate(
            "a failed requested model must not fall back",
            seed=1,
            temperature=0,
            max_new_tokens=8,
        )

    assert len(commands) == 1
    assert _model_arg(commands[0]) == _REQUESTED
    assert endpoints.PROVIDERS["claude"]["model"] not in commands[0]
