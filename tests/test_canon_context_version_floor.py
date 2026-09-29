"""The context bridge never ingests or queries through a canon older than its pin.

Outside a frozen build the context child runs ``python -m canon.context_mcp``
with whatever flywheel-canon the engine's interpreter has installed; it does not
pass through the lane runtime's version floor. canon 0.4.1 and older stored an
MCP ingest unredacted and cut query excerpts before scrubbing them
(GHSA-48rq-xjfx-6j4f), and the bridge sends capture events without redaction of
its own. So capture and preflight refuse with ``CANON_CONTEXT_OUTDATED`` when
the installed canon is below the pin; health still answers. A frozen build
ships the pinned payload and is not judged by the host's packages.
"""
from __future__ import annotations

import pytest

from harness import canon_context_runtime as runtime
from harness.lanes_registry import LANES


@pytest.mark.parametrize(("installed", "refused"), [
    ("0.4.1", True), ("0.3.0", True), (LANES["canon"].version, False), ("9.0.0", False),
    ("", False)])
def test_the_floor_follows_the_canon_pin(installed, refused):
    code = runtime.context_version_refusal(frozen=False, installed=installed)
    assert (code == "CANON_CONTEXT_OUTDATED") is refused


def test_a_frozen_build_uses_its_pinned_payload():
    assert runtime.context_version_refusal(frozen=True, installed="0.1.0") is None


def test_ingest_and_query_refuse_before_a_child_starts(monkeypatch):
    from harness import context_memory_bridge as bridge
    monkeypatch.setattr(runtime, "is_frozen_process", lambda: False)
    monkeypatch.setattr("harness.lane_runtime_support.installed_version",
                        lambda lane: "0.4.1")
    started = []
    monkeypatch.setattr(bridge.subprocess, "run", lambda *a, **k: started.append(a))
    client = bridge.CanonContextMcpClient(env={"CANON_CONTEXT_DB": "C:/x/context.db"},
                                          timeout_s=1.0)
    for call in (client.ingest, client.query):
        with pytest.raises(bridge.ContextMemoryError) as refused:
            call({})
        assert refused.value.code == "CANON_CONTEXT_OUTDATED"
    assert started == []
