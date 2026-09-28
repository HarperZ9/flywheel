"""`flywheel install` parses its arguments strictly and installs nothing unless they parse.

1.1.0 skipped any argument it did not know, so ``flywheel install --help``,
``flywheel install gather`` and ``flywheel install --lanes=gather`` each
installed every lane. install_lane is replaced here, so no package manager runs.
"""
from __future__ import annotations

import pytest

import harness.lanes as ln
from harness import cli_entry


@pytest.fixture
def installs(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(ln, "LANE_REGISTRY_PATH", tmp_path / "lanes.json")
    monkeypatch.setattr(ln, "install_lane", lambda name, profile="package": (
        seen.append((name, profile)) or {"installed": True}))
    return seen


@pytest.mark.parametrize("argv", [
    ["install", "--help"], ["install", "-h"], ["install", "--lanes", "gather", "--help"],
    ["install", "--bogus", "-h"]])
def test_help_prints_usage_and_installs_nothing(argv, installs, capsys):
    assert cli_entry.main(argv) == 0
    assert installs == []
    assert "usage: flywheel install" in capsys.readouterr().out


@pytest.mark.parametrize(("argv", "reason"), [
    (["install", "--bogus"], "unknown argument"),
    (["install", "gather"], "unknown argument"),
    (["install", "--lanes"], "needs a value"),
    (["install", "--profile"], "needs a value"),
    (["install", "--lanes", "--profile", "source"], "needs a value"),
    (["install", "--lanes="], "needs a value"),
    (["install", "--profile", "bogus"], "--profile must be"),
    (["install", "--lanes", ","], "names no lane"),
    (["install", "--lanes", "gather", "--lanes", "index"], "given twice"),
    (["install", "--lanes", "no-such-lane"], "unknown lane"),
])
def test_a_bad_argument_exits_2_with_the_error_and_usage(argv, reason, installs, capsys):
    assert cli_entry.main(argv) == 2
    assert installs == []
    err = capsys.readouterr().err
    assert reason in err
    assert "usage: flywheel install" in err


@pytest.mark.parametrize(("argv", "expected"), [
    (["install", "--lanes=gather"], [("gather", "package")]),
    (["install", "--lanes", "gather,index", "--profile", "source"],
     [("gather", "source"), ("index", "source")]),
    (["install", "--profile=package", "--lanes", "learn"], [("learn", "package")]),
])
def test_arguments_that_parse_install_exactly_what_they_name(argv, expected, installs):
    assert cli_entry.main(argv) == 0
    assert installs == expected
