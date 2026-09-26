"""Per-lane smoke for the frozen gateway: a real reply, not an exit code.

Each bundled lane is launched the way the gateway launches it (the same
admission, child environment and admitted-tool list), then must answer
``initialize``, ``tools/list``, its health tool, and its main tool on a test
fixture from ``lane_smoke_fixtures``. The furthest step a lane clears is its
level. ``packaging/lane-smoke-expectations.json`` records, per registry lane,
the level measured today (``expected``) and the target class (``bar``).

Verdicts: ``PASS`` when every lane reaches the main action; ``BELOW_BAR_EXPECTED``
when every lane matches its row and some lane is below the bar; ``FAIL`` when a
lane falls under its row, rises above a row nobody raised, or ships without a
row. A lane below the bar never yields ``PASS``.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import tempfile
from typing import Mapping

from harness.mcp_client import LaunchSpec, MCPClient, MCPError

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTATIONS = REPO_ROOT / "packaging" / "lane-smoke-expectations.json"
SCHEMA = "flywheel.frozen-lane-smoke/v2"
LEVELS = ("no_frozen_launch", "cannot_launch", "starts", "health", "main")
BAR_LEVEL = "main"
CLASSES = ("A", "B", "C", "A/B", "A/B-untested", "A/C", "B-untested")
_SYSTEM_VARS = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "SYSTEMDRIVE"}
DOES_NOT_PROVE = [
    "model-backed or provider-backed task success",
    "result correctness beyond one fixture assertion per lane",
    "lanes the frozen build has no launch for (they report no_frozen_launch)",
    "installer, desktop UI or clean-machine behavior",
]


@dataclass(frozen=True)
class LanePlan:
    launch: LaunchSpec | None          # None: admission refused the lane
    health_tool: str
    blocking_codes: tuple[str, ...] = ()


def load_expectations(path: Path = EXPECTATIONS) -> dict[str, dict]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if tuple(document.get("levels", ())) != LEVELS:
        raise ValueError("lane smoke expectations name other levels")
    return {str(lane): dict(row) for lane, row in document["lanes"].items()}


def _manifest_rows(executable: Path, repo_root: Path) -> dict[str, dict]:
    from harness.bundled_lane_descriptor import load_manifest_rows
    shipped = executable.parent / "_internal" / "packaging" / "python-lane-payloads.jsonl"
    if shipped.is_file():
        return load_manifest_rows(shipped)
    return load_manifest_rows(repo_root / "packaging" / "python-lane-payloads.jsonl")


def smoke_environ(home: Path) -> dict[str, str]:
    """The engine environment an installed app would have, under a scratch home."""
    env = {k: v for k, v in os.environ.items() if k.upper() in _SYSTEM_VARS}
    for name in ("FLYWHEEL_HOME", "USERPROFILE", "HOME", "TEMP", "TMP",
                 "APPDATA", "LOCALAPPDATA"):
        env[name] = str(home)
    env["PATH"] = str(Path(os.environ.get("SystemRoot", "/")) / "System32")
    return env


def bundled_lane_plans(executable: Path, home: Path, *,
                       repo_root: Path = REPO_ROOT) -> dict[str, LanePlan]:
    """Admit every lane in the build's manifest through the gateway's own path."""
    from harness.bundled_lane_admission import admit_bundled_lane
    from harness.bundled_lane_descriptor import resolve_expected
    rows = _manifest_rows(executable, repo_root)
    environ = smoke_environ(home)
    plans: dict[str, LanePlan] = {}
    for lane in sorted(rows):
        expected = resolve_expected(lane, manifest_rows=rows) or {}
        # The child re-checks the import itself; this interpreter need not have it.
        admission = admit_bundled_lane(
            lane, executable=str(executable), environ=environ,
            manifest_rows=rows, importable_fn=lambda _module: True)
        plans[lane] = LanePlan(admission.launch, str(expected.get("health_tool", "")),
                               tuple(admission.blocking_codes))
    return plans


def _exit_code(client: MCPClient) -> int | None:
    proc = getattr(getattr(client, "_t", None), "proc", None)
    if proc is None:
        return None
    try:
        return proc.wait(timeout=2)
    except Exception:
        return None


def _call_json(client: MCPClient, tool: str, args: dict) -> tuple[bool, object]:
    reply = client.call_text(tool, args)
    try:
        return bool(reply["ok"]), json.loads(reply["text"])
    except (TypeError, ValueError):
        return bool(reply["ok"]), reply["text"]


def _main_step(client: MCPClient, plan: LanePlan, listed: set[str],
               home: Path, lane: str) -> tuple[str, str]:
    from scripts.lane_smoke_fixtures import FIXTURES
    fixture = FIXTURES.get(lane)
    if fixture is None:
        return "health", "no_fixture"
    work = home / "fixtures" / lane
    calls = fixture.calls(home, work)
    allowed = plan.launch.allowed_tools if plan.launch else None
    reply: object = None
    for tool, args in calls:
        if allowed is not None and tool not in allowed:
            return "health", "main_not_admitted"
        if tool not in listed:
            return "health", "main_tool_missing"
        ok, reply = _call_json(client, tool, args)
        if not ok:
            return "health", "main_call_failed"
    return ("main", "ok") if fixture.check(reply) else ("health", "main_assertion_failed")


def _session(client: MCPClient, plan: LanePlan, home: Path, lane: str) -> tuple[str, str]:
    allowed = plan.launch.allowed_tools if plan.launch else None
    try:
        names = {str(tool.get("name")) for tool in client.list_tools()}
    except MCPError:
        return "cannot_launch", "tools_list_failed"
    listed = names if allowed is None else names & set(allowed)
    if plan.health_tool not in listed:
        return "starts", "health_tool_missing"
    try:
        ok, _ = _call_json(client, plan.health_tool, {})
    except MCPError:
        return "starts", "health_call_failed"
    if not ok:
        return "starts", "health_call_failed"
    try:
        return _main_step(client, plan, listed, home, lane)
    except MCPError:
        return "health", "main_call_failed"


def probe_lane(lane: str, plan: LanePlan, home: Path, *, timeout: float) -> dict:
    """Run one lane through its steps; record the furthest level it clears."""
    if plan.launch is None:
        return {"level": "cannot_launch", "reason": "admission_blocked",
                "codes": list(plan.blocking_codes)}
    workdir = home / "lanes" / lane
    workdir.mkdir(parents=True, exist_ok=True)
    launch = plan.launch if plan.launch.cwd else replace(plan.launch, cwd=str(workdir))
    try:
        client = MCPClient(launch, timeout=timeout, client_name="flywheel-lane-smoke")
    except OSError:
        return {"level": "cannot_launch", "reason": "spawn_failed"}
    try:
        try:
            client.start()
        except MCPError:
            return {"level": "cannot_launch", "reason": "initialize_failed",
                    "exit_code": _exit_code(client)}
        level, reason = _session(client, plan, home, lane)
        return {"level": level, "reason": reason}
    finally:
        client.close()


def _verdict(lanes: dict[str, dict], unexpected: list[str]) -> dict:
    failures = sorted(set(unexpected) | {
        lane for lane, row in lanes.items() if row["level"] != row["expected"]})
    below = sorted(lane for lane, row in lanes.items() if row["level"] != BAR_LEVEL)
    verdict = "FAIL" if failures else ("BELOW_BAR_EXPECTED" if below else "PASS")
    return {"verdict": verdict, "failures": failures, "below_bar": below}


def run_lane_smoke(plans: Mapping[str, LanePlan], expectations: Mapping[str, dict], *,
                   home: Path, timeout: float = 30.0) -> dict:
    """Probe every planned lane and compare each level with its expectation row."""
    lanes: dict[str, dict] = {}
    for lane in sorted(set(expectations) | set(plans)):
        plan = plans.get(lane)
        measured = (probe_lane(lane, plan, home, timeout=timeout) if plan is not None
                    else {"level": "no_frozen_launch", "reason": "no_frozen_launch"})
        row = expectations.get(lane, {})
        lanes[lane] = {"level": measured["level"], "expected": row.get("expected"),
                       "bar": row.get("bar"), "reason": measured["reason"],
                       **{k: v for k, v in measured.items() if k not in ("level", "reason")}}
    unexpected = [lane for lane in plans if lane not in expectations]
    return {"schema": SCHEMA, "bar_level": BAR_LEVEL, **_verdict(lanes, unexpected),
            "lanes": lanes, "does_not_prove": list(DOES_NOT_PROVE)}


def bundled_lane_smoke(executable: Path, *, repo_root: Path = REPO_ROOT,
                       expectations_path: Path = EXPECTATIONS,
                       timeout: float = 30.0) -> dict:
    """Run the lane smoke against a frozen executable under a scratch home."""
    executable = Path(executable).resolve()
    expectations = load_expectations(expectations_path)
    with tempfile.TemporaryDirectory(prefix="flywheel-lane-smoke-") as directory:
        home = Path(directory).resolve()
        plans = bundled_lane_plans(executable, home, repo_root=repo_root)
        return run_lane_smoke(plans, expectations, home=home, timeout=timeout)
