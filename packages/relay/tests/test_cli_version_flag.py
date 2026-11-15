"""`relay --version` prints the running package's version and exits 0."""
from __future__ import annotations

import pytest

import relay
from relay import local_agent_cli


def test_version_flag_prints_the_package_version(capsys):
    with pytest.raises(SystemExit) as stop:
        local_agent_cli.main(["--version"])
    assert stop.value.code == 0
    assert capsys.readouterr().out.strip() == f"relay {relay.__version__}"


def test_version_flag_starts_no_backend(monkeypatch, capsys):
    # The flag answers before any endpoint is built or probed.
    def refuse(*args, **kwargs):
        raise AssertionError("--version must not build endpoints")

    monkeypatch.setattr("relay.endpoints.build_endpoints", refuse, raising=False)
    with pytest.raises(SystemExit) as stop:
        local_agent_cli.main(["--version"])
    assert stop.value.code == 0
