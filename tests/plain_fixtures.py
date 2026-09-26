"""Plaintext and legacy stores planted for the deletion tests: a fold index
note, a legacy agent run and its bench row, a gateway trace that names a CLI
profile folder, a sealed operation result, and a v1 receipt that cites a
frozen page. Every value is synthetic."""
from __future__ import annotations

import json

from delete_fixtures import JOURNEY, OWNER

RUN_ID = "0123456789abcdef"
OPERATION = "op_" + "d" * 32
PROFILE = "native-cli-profile-abc123"


def plant_note(run_root, text) -> str:
    from harness.memory_api import memory_note
    return memory_note(run_root, text)["span_hash"]


def plant_legacy_run(run_root, text) -> str:
    runs = run_root / "agent_runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / f"{RUN_ID}.json").write_text(json.dumps({"goal": text, "test_cmd": "pytest",
                                                     "verdict": "PASS"}))
    bench = run_root / "bench"
    bench.mkdir(parents=True, exist_ok=True)
    rows = [{"task_id": f"trace-{RUN_ID}", "prompt": text, "gate_cmd": "pytest"},
            {"task_id": "trace-" + "f" * 16, "prompt": "kept task", "gate_cmd": "pytest"}]
    (bench / "trace-tasks.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    return RUN_ID


def plant_profile_trace(home, text) -> str:
    from harness.gateway_agent_trace import AgentTrace
    state = home / "state"
    state.mkdir(parents=True, exist_ok=True)
    trace = AgentTrace(state, OWNER, JOURNEY, OPERATION)
    trace.append("progress", {"type": "cli_profile", "profile_dir": PROFILE})
    trace.append("result", {"final": text})
    (state / PROFILE / "AppData").mkdir(parents=True)
    (state / PROFILE / "AppData" / "session.log").write_text(text)
    results = state / "gateway-operations" / "v1" / "owners" / OWNER / "results"
    results.mkdir(parents=True, exist_ok=True)
    (results / ("9" * 64 + ".json")).write_text(json.dumps(
        {"operation_ref": OPERATION, "result": {"final": text}}))
    return trace.ref


def plant_v1_receipt(home, text, snapshot_sha="c" * 64) -> str:
    from harness.store import put_entity
    return put_entity("turn-receipt", {
        "schema": "flywheel.turn-receipt/v1", "prompt_sha256": "a" * 64,
        "sources_frozen": [{"url": "https://example.invalid/p", "sha256": snapshot_sha}],
        "degraded": [{"url": "https://example.invalid/q", "reason": text}]}, home=home)["eid"]
