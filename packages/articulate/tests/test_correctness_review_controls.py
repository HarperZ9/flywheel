"""Release-line controls from the 0.6.0 correctness review on main.

The review on main (branch review/correctness-060, commit a79e7fe) found that
main's ARTICULATE_LOCAL_ONLY switch sent text on a value it did not list
(C-7), and that main's editor command line raised StopIteration on an empty
file argument (C-12). The release line has its own switch in backends.py and
its own command line in cli.py. Both already behave correctly here. These
tests pin that, so a forward-port from main cannot bring either defect back.

The other review items test code that exists only on main: the fairness
release check, the fingerprint closure, quote blanking and citation anchors.
The release line keeps the v0.5.2 detector byte for byte
(scripts/check_release_ruleset.py), so those items have no counterpart here.
"""
import importlib
import os
import urllib.request

import pytest

from articulate import cli


@pytest.fixture
def backend(monkeypatch):
    module = importlib.import_module("articulate.backends")
    for key in list(os.environ):
        if key.startswith(("ARTICULATE_", "ANTHROPIC_", "OPENAI_")):
            monkeypatch.delenv(key)

    def forbidden(*args, **kwargs):
        pytest.fail("local-only crossed a prohibited boundary")

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", forbidden)
    monkeypatch.setattr(module, "_request", forbidden)
    monkeypatch.setattr(module.claude_cli, "resolve", forbidden)
    return module


# --- C-7: the switch fails closed on a value it does not list ---------------- #

@pytest.mark.parametrize("value", ["y", "Y", "2", "enabled", "local", " on "])
def test_an_unlisted_value_turns_local_only_on(backend, monkeypatch, value):
    monkeypatch.setenv("ARTICULATE_LOCAL_ONLY", value)
    assert backend.local_only()


@pytest.mark.parametrize("value", ["y", "enabled", "local"])
@pytest.mark.parametrize("choice", ["auto", "host", "anthropic", "claude-cli", "openai"])
def test_an_unlisted_value_refuses_every_hosted_route(backend, monkeypatch, value, choice):
    monkeypatch.setenv("ARTICULATE_LOCAL_ONLY", value)
    monkeypatch.setenv("ARTICULATE_OLLAMA_URL", "https://outside.example")

    def forbidden(*args, **kwargs):
        pytest.fail("a hosted route ran under local-only")

    _, info = backend.complete("p", "t", backend=choice, context="mcp",
                               sampling=forbidden, sampling_advertised=True)
    assert info.backend == "none"


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "OFF", " No "])
def test_control_the_explicit_off_values_leave_local_only_off(backend, monkeypatch, value):
    monkeypatch.setenv("ARTICULATE_LOCAL_ONLY", value)
    assert not backend.local_only()


# --- C-12: an empty file argument is "no such file", exit 2 ------------------ #

@pytest.mark.parametrize("command", ["judge", "fix", "polish", "plan"])
def test_an_empty_file_argument_exits_2(monkeypatch, capsys, command):
    monkeypatch.delenv("ARTICULATE_LOCAL_ONLY", raising=False)
    assert cli.main([command, ""]) == 2
    assert "No such file" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["judge", "fix", "polish", "plan"])
def test_an_empty_file_argument_under_local_only_starts_nothing(backend, monkeypatch,
                                                                 capsys, command):
    monkeypatch.setenv("ARTICULATE_LOCAL_ONLY", "1")
    assert cli.main([command, ""]) == 2


def test_an_empty_file_argument_fails_the_check_gate(capsys):
    assert cli.main(["check", "--gate", ""]) == 1
    assert "cannot screen" in capsys.readouterr().err
