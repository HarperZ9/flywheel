"""The raw lane in the lane roster: a bundled adapter lane with no MCP server.

Claims under test:
- the registry declares raw as a bundled 0.5.0 perception lane with an adapter
  and no MCP argv;
- with no binary installed, the roster reads missing with TOOLCHAIN_MISSING and
  the install command; once the pinned binary is in place it reads declared;
- the runtime never invents an MCP launch for it, frozen or from source: the
  code is ``lane_adapter_only``, and the card sentence names the adapter;
- ``install_lane("raw")`` goes to the lane's own installer, not the
  "bundled, no install needed" answer the other bundled lanes give;
- paired mutation: an adapter lane routed to the generic bundled path gets a
  launch, which the no-launch check catches.
"""
from __future__ import annotations

import pytest

import harness.lanes as ln
from harness import lane_runtime_frozen as lrf, raw_lane_install as inst
from harness.lane_roster_row import roster_rows
from harness.lane_tool_policy import ADAPTER_LANES
from harness.lanes_registry import LANES


def test_the_registry_declares_raw_as_a_bundled_adapter_lane():
    lane = LANES["raw"]
    assert (lane.kind, lane.version, lane.organ) == ("bundled", inst.VERSION, "perception")
    assert lane.adapter_module == "harness.raw_lane"
    assert lane.mcp_command() == [] and ln.resolve_mcp_command("raw") == []


def _no_launch_known_answer() -> None:
    runtime = ln.resolve_lane_runtime("raw")
    assert runtime.launch is None
    assert runtime.blocking_codes == ("lane_adapter_only",)


def test_no_mcp_launch_from_source(monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    _no_launch_known_answer()


def test_no_mcp_launch_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    monkeypatch.setattr(ln, "_frozen", lambda: True)
    _no_launch_known_answer()


def test_paired_mutation_the_generic_bundled_path_is_caught(monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    real = lrf.select_bundled_launch

    def generic(lane, python_executable):
        return real(type(lane)(**{**lane.__dict__, "adapter_module": ""}), python_executable)
    monkeypatch.setattr(lrf, "select_bundled_launch", generic)
    with pytest.raises(AssertionError):
        _no_launch_known_answer()


def test_missing_binary_reads_toolchain_missing_with_the_install_command(monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    row = ln.lane_status("raw", probe=True)
    assert row["status"] == "missing"
    assert row["detail"].startswith("TOOLCHAIN_MISSING")
    assert "flywheel install --lanes raw" in row["detail"]
    card = roster_rows([row], probed=True)[0]
    assert (card["state"], card["code"]) == ("cannot_launch", "lane_adapter_only")
    assert card["sentence"] == ADAPTER_LANES["raw"]


def test_a_pinned_binary_reads_declared(monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    plat = inst.platform_key() or "linux-x64"
    path = inst.binary_path(None, inst.PINS, plat)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"stand-in")
    monkeypatch.setattr(inst, "matches_pin", lambda p, digest: p == path)
    monkeypatch.setattr(inst, "platform_key", lambda *a: plat)
    row = ln.lane_status("raw", probe=True)
    assert row["status"] == "declared" and "no MCP server" in row["detail"]


def test_install_lane_routes_to_the_lane_installer(monkeypatch):
    seen = []
    monkeypatch.setattr(inst, "install", lambda: seen.append(1) or {"installed": False,
                                                                      "code": "TOOLCHAIN_MISSING"})
    assert ln.install_lane("raw")["code"] == "TOOLCHAIN_MISSING"
    assert seen == [1]
