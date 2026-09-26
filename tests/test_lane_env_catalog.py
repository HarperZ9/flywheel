"""The agent-run MCP catalog keeps lanes on the strict plugin environment.

restricted_catalog_launch builds the launch an admitted agent.run MCP server gets,
and cache_mcp_discovery_receipt writes that launch, env values included, into a
discovery receipt on disk. Before lane launches were confined, a lane launch
reached this path with inherit_env=True and was rebuilt from the strict plugin
set (7 names on Windows, 5 on POSIX). A confined lane launch arrives with
inherit_env=False, and it must not slip past that rebuild: the lane env and any
lanes.json env_allow grant would otherwise reach agent-run servers and be stored
at rest in the receipt. The granted value here is an obvious fake.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

import harness.lanes as ln
from harness import plugins

OWNER = "owner_" + "a" * 32
POLICY = {"reason": "test bounded discovery", "timeout_s": 10, "network": False}
REPO = Path(__file__).resolve().parents[1]
FAKE_GRANTED = "fake-granted-value-not-a-real-key-7f3a"
LAUNCH_OWN = {"PYTHONPATH", "PYTHONSAFEPATH"}


@pytest.fixture
def granted_index(tmp_path, monkeypatch):
    registry = tmp_path / "lanes.json"
    registry.write_text(json.dumps({"index": {"env_allow": ["FAKE_GRANTED_TOKEN"]}}),
                        encoding="utf-8")
    monkeypatch.setattr(ln, "LANE_REGISTRY_PATH", registry)
    monkeypatch.setenv("FAKE_GRANTED_TOKEN", FAKE_GRANTED)
    monkeypatch.setenv("USERPROFILE" if os.name == "nt" else "USER", "someone")
    monkeypatch.setenv("FLYWHEEL_WORKSPACE_ROOT", str(REPO.resolve()))
    monkeypatch.setattr(ln, "resolve_source_repo", lambda lane: None)
    monkeypatch.setattr(ln, "_importable", lambda top: True)
    monkeypatch.setattr(ln, "_installed_version", lambda lane: lane.version)
    monkeypatch.setattr(ln, "_frozen", lambda: False)
    lane_launch = ln.resolve_mcp_launch("index")
    assert lane_launch.inherit_env is False
    assert "FAKE_GRANTED_TOKEN" in dict(lane_launch.env_overrides)  # the direct lane launch
    return tmp_path


def _strict_names():
    return plugins._WINDOWS_ENV if os.name == "nt" else plugins._POSIX_ENV


def test_catalog_launch_keeps_the_strict_env_and_drops_grants(granted_index):
    from harness.gateway_agent_mcp_cache import restricted_catalog_launch
    launch, kind = restricted_catalog_launch("index", ["index.doctor"])
    names = {key.upper() for key, _ in launch.env_overrides}
    assert kind == "lane"
    assert launch.inherit_env is False
    assert "FAKE_GRANTED_TOKEN" not in names
    assert names - LAUNCH_OWN <= _strict_names(), sorted(names - _strict_names())
    assert FAKE_GRANTED not in json.dumps(launch.env_overrides)


def test_discovery_receipt_never_stores_a_granted_value(granted_index):
    from harness.gateway_agent_mcp_cache import cache_mcp_discovery_receipt

    class Client:
        def __init__(self, *_args, **_kwargs):
            self.server_info = {"name": "index", "version": "1"}
            self.protocol_version = "2025-06-18"

        def start(self):
            return self

        def list_tools(self):
            return [{"name": "index.doctor", "description": "Doctor.",
                     "inputSchema": {"type": "object", "properties": {},
                                     "additionalProperties": False}}]

        def close(self):
            pass

    state = granted_index / "state"
    receipt = cache_mcp_discovery_receipt(
        "index", server_id="index", owner_ref=OWNER, state_root=state,
        tools=["index.doctor"], timeout_s=10, discovery_authorization=POLICY,
        client_factory=Client)
    stored = [path for path in state.rglob("*") if path.is_file()]
    assert stored
    for path in stored:
        assert FAKE_GRANTED.encode() not in path.read_bytes(), path.name
    names = {key.upper() for key, _ in receipt["launch"]["env_overrides"]}
    assert "FAKE_GRANTED_TOKEN" not in names


def test_bundled_lane_launch_still_passes_through(monkeypatch):
    from harness.credential_handles import CredentialBindings
    from harness.mcp_client import LaunchSpec
    bundled = LaunchSpec((sys.executable, "--bundled-lane-mcp", "relay"),
                         env_overrides=(("APPDATA", "a"), ("PATH", "p")),
                         inherit_env=False, allowed_tools=("relay.status",))
    assert plugins._restricted_launch(bundled, CredentialBindings({}), (),
                                      lane=True) is bundled
