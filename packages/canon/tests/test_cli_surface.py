"""test_cli_surface.py -- what `canon --help` and `canon --version` tell a user.

0.3.0 and 0.4.0 shipped a top-level help that called the tool a "bootstrap
command surface" and described every command as "<name> placeholder", and no
version flag: `canon --version` failed as invalid arguments. These tests hold
the first screen a new user sees to a real description of each command and
subcommand, and the version flag to the one number the package declares.
"""
from __future__ import annotations

import argparse
import io
import json

import pytest

import canon
from canon.cli import COMMANDS, build_parser, run_cli


def _run(argv: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    code = run_cli(argv, stdin=io.StringIO(""), stdout=stdout, stderr=stderr, environ={})
    return code, stdout.getvalue(), stderr.getvalue()


def _command_lines(help_text: str) -> dict[str, str]:
    """Map each listed command to the help text printed beside it."""
    found = {}
    for line in help_text.splitlines():
        words = line.split(None, 1)
        if len(words) == 2 and words[0] in COMMANDS and line.startswith("    "):
            found[words[0]] = words[1].strip()
    return found


def test_top_level_help_describes_the_tool():
    code, out, _ = _run(["--help"])
    assert code == 0
    assert "bootstrap command surface" not in out
    assert "memory bank" in out and "instruction file" in out


def test_top_level_help_describes_every_command():
    code, out, _ = _run(["--help"])
    assert code == 0
    assert "placeholder" not in out
    lines = _command_lines(out)
    assert sorted(lines) == sorted(COMMANDS)
    for command, text in lines.items():
        assert len(text.split()) >= 4, f"{command}: {text!r} is not a description"


@pytest.mark.parametrize("command", COMMANDS)
def test_each_command_help_leads_with_the_same_description(command):
    _, top, _ = _run(["--help"])
    code, out, _ = _run([command, "--help"])
    assert code == 0
    first_words = " ".join(_command_lines(top)[command].split()[:4]).lower()
    assert first_words in " ".join(out.split()).lower()


def _subcommands(parser: argparse.ArgumentParser, path: tuple[str, ...] = ()):
    """Yield (path, help) for every subcommand below `parser`, at any depth."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            helps = {choice.dest: choice.help for choice in action._choices_actions}
            for name, child in action.choices.items():
                yield (*path, name), helps.get(name) or ""
                yield from _subcommands(child, (*path, name))


ALL_SUBCOMMANDS = list(_subcommands(build_parser()))
NESTED = [path for path, _ in ALL_SUBCOMMANDS if len(path) > 1]


def test_every_command_and_subcommand_has_a_description():
    assert {path[0] for path, _ in ALL_SUBCOMMANDS} == set(COMMANDS)
    assert NESTED, "the walk found no nested subcommands"
    for path, text in ALL_SUBCOMMANDS:
        name = " ".join(path)
        assert "placeholder" not in text, name
        assert len(text.split()) >= 3, f"{name}: {text!r} is not a description"


@pytest.mark.parametrize("path", NESTED, ids=" ".join)
def test_each_subcommand_help_leads_with_its_description(path):
    text = dict(ALL_SUBCOMMANDS)[path]
    code, out, _ = _run([*path, "--help"])
    assert code == 0
    assert " ".join(text.split()).lower() in " ".join(out.split()).lower()


@pytest.mark.parametrize("flag", ["--version", "-V"])
def test_version_flag_prints_the_package_version(flag):
    code, out, err = _run([flag])
    assert code == 0
    assert out == f"canon {canon.__version__}\n"
    assert err == ""


def test_version_flag_wins_over_a_command_and_starts_nothing():
    # `canon --version mcp` must not start the stdio server.
    code, out, _ = _run(["--version", "mcp"])
    assert code == 0 and out == f"canon {canon.__version__}\n"


@pytest.mark.parametrize("argv", [["--json", "--version"], ["--version", "--json"]])
def test_json_version_is_a_result_object(argv):
    code, out, _ = _run(argv)
    assert code == 0
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["command"] == "version"
    assert payload["data"] == {"distribution": "flywheel-canon", "version": canon.__version__}


def test_an_unknown_top_level_option_is_still_a_usage_error():
    code, _, err = _run(["--bogus"])
    assert code == 2
    assert "invalid arguments" in err
