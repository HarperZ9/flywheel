"""A lane's own closed refusal answers as the engine's fixed refusal.

gather 1.9.1 refuses a network or device path itself (NON_LOCAL_PATH), after
the engine's own path guard, and gather and forum refuse a call whose launch
lacks a grant (GRANT_REQUIRED). The lane call route passes no tool text on
(fixed codes, closed reason slugs), so these read as the engine's refusal
shape: LANE_TOOL_ERROR with ``argument_refused`` or ``lane_grant_required``,
whichever check caught it. Any other lane error keeps the generic answer.

The last tests start the real gather 1.9.1 from its tag's source, where a
checkout is present (FLYWHEEL_LANE_CHECKOUT_ROOT, default C:/dev). The engine
refuses a reserved device name in a path argument itself, before the lane
starts (tests/test_lane_reserved_device_names.py). Inside gather.run's inline
config it leaves one to gather, since a config also holds text that is not a
path, and gather refuses it.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

import harness.plugins  # noqa: F401  bound before a test patches resolve_mcp_launch
from harness.lane_call_route import public_result
from harness.lane_caller import LANE_REFUSALS, call_lane_tool, lane_refusal
from harness.mcp_client import LaunchSpec

GATHER_PIN = "6b5d4dd5920a248bafaeefef4f596e67a42889fb"
CHECKOUT_ROOT = Path(os.environ.get("FLYWHEEL_LANE_CHECKOUT_ROOT", "C:/dev"))
DETAIL = "The path names a Windows device or namespace path"


def _refused(code: str, detail: str = DETAIL) -> dict:
    body = {"code": code, "retryable": False, "kind": "device", "argument": "path",
            "detail": detail}
    return {"content": [{"type": "text", "text": json.dumps(body)}], "isError": True,
            "structuredContent": body}


def test_each_closed_code_maps_to_one_reason_slug():
    assert {code: slug for code, (slug, _msg) in LANE_REFUSALS.items()} == {
        "NON_LOCAL_PATH": "argument_refused", "GRANT_REQUIRED": "lane_grant_required"}
    got = lane_refusal("gather", "gather.docs", _refused("NON_LOCAL_PATH"))
    assert got == {"code": "LANE_TOOL_ERROR", "status": "unavailable", "name": "gather",
                   "tool": "gather.docs", "reason": "argument_refused",
                   "error": "the lane refused a network or device path"}
    assert lane_refusal("forum", "gate_edit", _refused("GRANT_REQUIRED"))["reason"] == \
        "lane_grant_required"


@pytest.mark.parametrize("raw", [
    _refused("NOT_FOUND"),                                           # another closed code
    {"content": [{"type": "text", "text": "NON_LOCAL_PATH"}], "isError": True},  # text only
    {"isError": True, "structuredContent": {"code": ["NON_LOCAL_PATH"]}},
    {"isError": True, "structuredContent": "NON_LOCAL_PATH"},
    None,
])
def test_anything_else_is_not_a_lane_refusal(raw):
    assert lane_refusal("gather", "gather.docs", raw) is None


def test_the_route_answers_a_lane_refusal_as_a_client_error():
    body, status = public_result("gather", "gather.docs",
                                 lane_refusal("gather", "gather.docs",
                                              _refused("NON_LOCAL_PATH")), 20)
    assert (status, body["code"], body["reason"]) == (400, "LANE_TOOL_ERROR",
                                                      "argument_refused")


def _fake_lane(monkeypatch, result: dict) -> None:
    import harness.lanes as lanes
    import harness.mcp_client as mcp_client

    class _Client:
        def __init__(self, command, **_kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

        def call_text(self, name, args):
            texts = [c.get("text", "") for c in result.get("content", [])]
            return {"ok": not result.get("isError"), "text": "\n".join(texts), "raw": result}

    launch = LaunchSpec(("python.exe", "-m", "gather.cli", "mcp"))
    monkeypatch.setattr(lanes, "resolve_mcp_launch", lambda name, *a, **k: launch)
    monkeypatch.setattr(mcp_client, "MCPClient", _Client)


def test_the_call_route_passes_no_lane_text_with_a_refusal(monkeypatch):
    # A path the engine's own guard passes, so the refusal is the lane's.
    _fake_lane(monkeypatch, _refused("NON_LOCAL_PATH", detail="secret-looking lane text"))
    got = call_lane_tool("gather", "gather.docs", {"path": "C:/docs/a.md"})
    assert got["reason"] == "argument_refused"
    assert "secret-looking" not in json.dumps(got)


def test_another_lane_error_keeps_the_generic_answer(monkeypatch):
    _fake_lane(monkeypatch, _refused("NOT_FOUND"))
    got = call_lane_tool("gather", "gather.docs", {"path": "C:/docs/a.md"})
    assert set(got) == {"error"} and got["error"].startswith("gather.gather.docs error: ")
    body, status = public_result("gather", "gather.docs", got, 20)
    assert (status, body["reason"]) == (502, "tool_reported_error")


def _gather_source(tmp_path: Path) -> Path:
    checkout = CHECKOUT_ROOT / "public" / "gather"
    if not (checkout / ".git").exists():
        pytest.skip(f"no gather checkout under {CHECKOUT_ROOT}")
    probe = subprocess.run(
        ["git", "-C", str(checkout), "cat-file", "-e", f"{GATHER_PIN}^{{commit}}"],
        capture_output=True, check=False)
    if probe.returncode != 0:
        pytest.skip("the gather checkout lacks the pinned commit")
    data = subprocess.run(["git", "-C", str(checkout), "archive", GATHER_PIN, "src"],
                          capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(tmp_path / "gather", filter="data")
    return tmp_path / "gather" / "src"


def _gather_launch(monkeypatch, tmp_path: Path) -> list:
    """Point the engine at the real gather 1.9.1; returns the list of launches."""
    import harness.lanes as lanes
    src = _gather_source(tmp_path)
    work = tmp_path / "lane"
    work.mkdir()
    env = {**{k: v for k, v in os.environ.items() if k.upper() in ("PATH", "SYSTEMROOT")},
           "PYTHONPATH": str(src), "PYTHONUTF8": "1"}
    launch = LaunchSpec((sys.executable, "-m", "gather.cli", "mcp"), cwd=str(work),
                        env_overrides=tuple(env.items()), inherit_env=False)
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "home"))
    launched: list = []
    monkeypatch.setattr(lanes, "resolve_mcp_launch",
                        lambda name, *a, **k: launched.append(name) or launch)
    return launched


@pytest.mark.timeout(180)
def test_gather_1_9_1_refuses_a_device_name_the_engine_guard_leaves_to_it(monkeypatch, tmp_path):
    from harness.lane_tier_gate import argument_refusal
    launched = _gather_launch(monkeypatch, tmp_path)
    config = {"jobs": [{"source": "docs", "target": r"C:\docs\CON.md"}]}
    assert argument_refusal("gather", "gather.run", {"config": config}) is None
    got = call_lane_tool("gather", "gather.run", {"config": config}, governance_tier="T2",
                         timeout=60)
    assert launched == ["gather"]
    assert (got.get("code"), got.get("reason")) == ("LANE_TOOL_ERROR", "argument_refused")
    assert got["error"] == "the lane refused a network or device path"


@pytest.mark.timeout(180)
def test_the_engine_refuses_a_device_name_path_before_gather_starts(monkeypatch, tmp_path):
    from harness.lane_tier_gate import argument_refusal
    launched = _gather_launch(monkeypatch, tmp_path)
    path = r"C:\docs\CON.md"
    assert argument_refusal("gather", "gather.docs", {"path": path})["reason"] ==         "argument_refused"
    got = call_lane_tool("gather", "gather.docs", {"path": path}, timeout=60)
    assert (got.get("code"), got.get("reason")) == ("LANE_TOOL_ERROR", "argument_refused")
    assert got["error"] == "the engine refused an argument of this lane tool"
    assert launched == []
