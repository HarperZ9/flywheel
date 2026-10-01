"""Shared builders for the pre-action monitor tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from harness.preaction.contract import ProposedCall, RunContext


class Clock:
    """A settable UTC clock so expiry and grant windows are deterministic."""

    def __init__(self, start: str = "2026-10-01T12:00:00Z") -> None:
        self.now = datetime.fromisoformat(start.replace("Z", "+00:00"))

    def __call__(self) -> str:
        return self.now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


def call(tool: str, harness: str = "flywheel", path_id: str = "E1", **args) -> ProposedCall:
    return ProposedCall(tool=tool, args=dict(args), harness=harness, path_id=path_id)


def ctx(run_id: str = "run-1", **kw) -> RunContext:
    kw.setdefault("workspace", "/work/repo")
    return RunContext(run_id=run_id, **kw)


def monitor(home, clock=None, **kw):
    from harness.preaction.core import Monitor, MonitorConfig
    config = kw.pop("config", None) or MonitorConfig()
    return Monitor(home=home, config=config, clock=clock or Clock(), **kw)
