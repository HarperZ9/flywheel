"""The engine's own claude and codex CLI runs carry capture off.

Correctness review F5 of 1.1.0: the subscription tiers (``claude -p`` and
``codex exec``, the claude-plan and codex-plan endpoints) ran with the engine's
own environment, so a Rowan task, an agent run or a bench replay routed there
fired the owner's user-level capture hooks, and custody recorded Flywheel's
own routed prompts as the owner's turns next to the gateway trace that already
holds them. The cross-harness peers get the same rule.
"""
from __future__ import annotations

import subprocess

import pytest

from harness import endpoints
from harness.cross_harness_process import _child_env


@pytest.mark.parametrize("provider", ["claude", "codex"])
def test_a_cli_tier_run_carries_capture_off(provider, monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(cmd, 0, b"ok", b"")
    monkeypatch.setattr(endpoints.subprocess, "run", fake_run)
    monkeypatch.setenv("FLYWHEEL_CAPTURE", "on")
    backend = endpoints.CliBackend(name=f"{provider}-plan",
                                   argv=list(endpoints.PROVIDERS[provider]["cli"]),
                                   model="m")
    try:
        backend.chat([{"role": "user", "content": "hi"}], system="", max_tokens=8,
                     temperature=0.0, seed=0)
    except endpoints.BackendError:
        pass                                   # codex reads its output file; not the point
    env = seen.get("env")
    assert env is not None, "the CLI ran with the engine's environment as is"
    assert env["FLYWHEEL_CAPTURE"] == "off"
    assert "PATH" in {k.upper() for k in env}


def test_a_cross_harness_peer_carries_capture_off(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_CAPTURE", "on")
    assert _child_env()["FLYWHEEL_CAPTURE"] == "off"
