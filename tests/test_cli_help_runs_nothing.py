"""Falsifiers: `--help` on an umbrella command prints usage and runs nothing.

Before this, `flywheel gate --help` ran the gate and wrote its artifacts, and
`flywheel up --help` printed the lane roster on its way to the gateway."""
import os
import re
from pathlib import Path

import pytest

from harness import cli_entry

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("command", sorted(cli_entry._UMBRELLA_USAGE))
@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_prints_usage_and_writes_nothing(command, flag, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    called = []
    monkeypatch.setattr(cli_entry, "_launch_gateway", lambda argv: called.append(argv) or 0)
    code = cli_entry._dispatch_umbrella(command, [flag])
    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith(f"usage: flywheel {command}")
    assert not called, "help must not start the gateway"
    assert os.listdir(tmp_path) == [], "help must not write files"


def test_relay_missing_message_names_the_pip_fix():
    from harness import relay_bridge
    assert "flywheel install --lanes relay" in relay_bridge._NOT_FOUND


def _version():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version\s*=\s*"(.+?)"', text, re.M).group(1)


def test_readme_badge_names_the_current_version():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    badge = re.search(r"badge/version-([0-9][0-9A-Za-z.]*)-", text)
    assert badge, "README has no version badge"
    assert badge.group(1) == _version(), "bump the README badge with the version sites"


def test_getting_started_pins_no_release():
    text = (ROOT / "GETTING-STARTED.md").read_text(encoding="utf-8")
    pinned = re.findall(r"releases/(?:tag|download)/v\d", text)
    assert not pinned, "link the latest release instead of pinning one that goes stale"
