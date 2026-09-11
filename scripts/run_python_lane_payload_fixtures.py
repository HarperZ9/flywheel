"""Run bounded installed-wheel fixture workflows for Python lane payloads."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

SCHEMA = "flywheel.python-lane-fixtures/v1"
PROTOCOL = "2025-06-18"


def fixture_catalog() -> list[dict[str, Any]]:
    return [
        {"lane": "gather", "tool": "gather.docs", "network": "none", "workflow": "read synthetic local document"},
        {"lane": "crucible", "tool": "crucible.assess", "network": "none", "workflow": "assess synthetic thesis and measurements"},
        {"lane": "index", "tool": "index.map", "network": "none", "workflow": "map a tiny synthetic Python workspace"},
        {"lane": "forum", "tool": "forum.route", "network": "none", "workflow": "route a synthetic verification request"},
        {"lane": "plexus", "tool": "plexus_plan", "network": "none", "workflow": "plan a built-in interop target"},
        {"lane": "mneme", "tool": "mneme.remember+mneme.recall", "network": "none", "workflow": "store and recall synthetic memory"},
        {"lane": "canon", "tool": "canon.validate", "network": "none", "workflow": "validate a synthetic canon record"},
    ]


class FixtureError(RuntimeError):
    pass


def _server_command(python: str, module: str, callable_name: str) -> list[str]:
    code = (
        "import importlib, sys; "
        f"m=importlib.import_module({module!r}); "
        f"raise SystemExit(getattr(m, {callable_name!r})())"
    )
    return [python, "-c", code]


def _call_tool(*, python: str, command: list[str], name: str, arguments: dict[str, Any],
               cwd: Path, env: dict[str, str] | None = None,
               timeout: int = 30) -> tuple[str, Any]:
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": PROTOCOL, "capabilities": {},
                    "clientInfo": {"name": "flywheel-python-lane-fixture", "version": "1"}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": name, "arguments": arguments}},
    ]
    child_env = os.environ.copy()
    if env:
        child_env.update(env)
    cwd.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        command, input="\n".join(json.dumps(msg, sort_keys=True) for msg in messages) + "\n",
        capture_output=True, text=True, check=False, timeout=timeout, cwd=str(cwd), env=child_env)
    if proc.returncode != 0:
        raise FixtureError(f"{name}: server exited {proc.returncode}: {proc.stderr or proc.stdout}")
    responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    response = next((item for item in responses if item.get("id") == 2), None)
    if response is None:
        raise FixtureError(f"{name}: no tool response; stdout={proc.stdout!r} stderr={proc.stderr!r}")
    if "error" in response:
        raise FixtureError(f"{name}: JSON-RPC error {response['error']}")
    result = response["result"]
    if result.get("isError") is True:
        raise FixtureError(f"{name}: tool returned isError: {result}")
    text = result["content"][0]["text"]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = text
    return text, parsed


def _receipt(lane: str, tool: str, parsed: Any, raw_text: str) -> dict[str, Any]:
    excerpt = raw_text[:700]
    return {
        "lane": lane,
        "tool": tool,
        "ok": True,
        "result_sha256": "sha256:" + sha256(raw_text.encode("utf-8")).hexdigest(),
        "evidence_excerpt": excerpt,
        "parsed_type": type(parsed).__name__,
    }


def _run_gather(python: str, lane_dir: Path) -> dict[str, Any]:
    lane_dir.mkdir(parents=True, exist_ok=True)
    sample = lane_dir / "sample.txt"
    sample.write_text("Synthetic Gather fixture: bounded local document.\n", encoding="utf-8")
    text, parsed = _call_tool(
        python=python,
        command=_server_command(python, "gather.mcp", "serve"),
        name="gather.docs",
        arguments={"path": str(sample)},
        cwd=lane_dir,
    )
    if parsed.get("schema") != "gather.catalog-digest/v1" or not parsed.get("verified"):
        raise FixtureError("gather.docs did not return a verified catalog digest")
    row = _receipt("gather", "gather.docs", parsed, text)
    row["assertions"] = {"schema": parsed["schema"], "catalog_rows": len(parsed.get("catalog", []))}
    return row


def _run_crucible(python: str, lane_dir: Path) -> dict[str, Any]:
    lane_dir.mkdir(parents=True, exist_ok=True)
    thesis = lane_dir / "thesis.json"
    measurements = lane_dir / "measurements.json"
    thesis.write_text(json.dumps({
        "title": "Binary search comparison bounds",
        "disposition": "publishable",
        "claims": [
            {"text": "binary search over a sorted array of 1024 elements does at most 11 comparisons",
             "falsification": "a measured worst-case comparison count above 11 for n=1024"},
            {"text": "binary search over a sorted array of 1024 elements does at most 3 comparisons",
             "falsification": "a measured worst-case comparison count above 3 for n=1024"},
        ],
    }, indent=2), encoding="utf-8")
    measurements.write_text(json.dumps({"measurements": [
        {"claim": "binary search over a sorted array of 1024 elements does at most 11 comparisons",
         "deviation": 0.0, "tolerance": 0.5, "method": "comparison-count",
         "evidence": ["worst-case probes for n=1024 is floor(log2(1024)) + 1 = 11"]},
        {"claim": "binary search over a sorted array of 1024 elements does at most 3 comparisons",
         "deviation": 8.0, "tolerance": 0.5, "method": "comparison-count",
         "evidence": ["worst case is 11, claimed bound 3, excess 8"]},
    ]}, indent=2), encoding="utf-8")
    text, parsed = _call_tool(
        python=python,
        command=_server_command(python, "crucible.mcp", "serve"),
        name="crucible.assess",
        arguments={"thesis": str(thesis), "measurements": str(measurements)},
        cwd=lane_dir,
    )
    verdicts = parsed.get("verdicts") or []
    if len(verdicts) < 2:
        raise FixtureError("crucible.assess did not return both verdicts")
    row = _receipt("crucible", "crucible.assess", parsed, text)
    row["assertions"] = {"verdict_count": len(verdicts), "assessment": bool(parsed.get("assessment"))}
    return row


def _run_index(python: str, lane_dir: Path) -> dict[str, Any]:
    workspace = lane_dir / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "alpha.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
    text, parsed = _call_tool(
        python=python,
        command=_server_command(python, "index_graph.mcp", "serve"),
        name="index.map",
        arguments={"root": str(workspace)},
        cwd=lane_dir,
    )
    if "alpha.py" not in text:
        raise FixtureError("index.map did not include the synthetic file")
    row = _receipt("index", "index.map", parsed, text)
    row["assertions"] = {"mentions_alpha_py": True}
    return row


def _run_forum(python: str, lane_dir: Path) -> dict[str, Any]:
    text, parsed = _call_tool(
        python=python,
        command=[python, "-m", "forum.mcp_surface"],
        name="forum.route",
        arguments={"text": "Route this fixture: verify a claim against local evidence."},
        cwd=lane_dir,
    )
    if not isinstance(parsed, dict) or not parsed:
        raise FixtureError("forum.route did not return a JSON object")
    row = _receipt("forum", "forum.route", parsed, text)
    row["assertions"] = {"keys": sorted(parsed)[:8], "state_root": str(lane_dir.as_posix())}
    return row


def _run_plexus(python: str, lane_dir: Path) -> dict[str, Any]:
    text, parsed = _call_tool(
        python=python,
        command=_server_command(python, "plexus.mcp", "serve"),
        name="plexus_plan",
        arguments={"goal": "crucible"},
        cwd=lane_dir,
    )
    if "crucible" not in text:
        raise FixtureError("plexus_plan did not bind the crucible goal")
    row = _receipt("plexus", "plexus_plan", parsed, text)
    row["assertions"] = {"mentions_goal": True, "order_count": len(parsed.get("order", []))}
    return row


def _run_mneme(python: str, lane_dir: Path) -> dict[str, Any]:
    env = {"MNEME_STATE": str((lane_dir / "mneme.db").as_posix())}
    command = _server_command(python, "mneme.mcp", "serve")
    remember_text, remember_parsed = _call_tool(
        python=python,
        command=command,
        name="mneme.remember",
        arguments={"session": "fixture-session",
                   "turns": [{"role": "user", "text": "The fixture codename is blue-otter."}],
                   "user": "fixture"},
        cwd=lane_dir,
        env=env,
    )
    recall_text, recall_parsed = _call_tool(
        python=python,
        command=command,
        name="mneme.recall",
        arguments={"query": "blue-otter", "top_k": 3, "user": "fixture"},
        cwd=lane_dir,
        env=env,
    )
    if "blue-otter" not in recall_text:
        raise FixtureError("mneme.recall did not surface the remembered fact")
    combined = json.dumps({"remember": remember_parsed, "recall": recall_parsed}, sort_keys=True)
    row = _receipt("mneme", "mneme.remember+mneme.recall", recall_parsed, combined)
    row["assertions"] = {"recall_mentions_fixture": True}
    return row


def _run_canon(python: str, lane_dir: Path) -> dict[str, Any]:
    source_hash = sha256(b"canon payload fixture").hexdigest()
    record = {
        "canon_schema": "canon.record/v1",
        "kind": "personality-block",
        "id": "fixture-personality",
        "scope": "global",
        "data": {"title": "Fixture", "body": "Synthetic fixture block."},
        "provenance": {"harness": "payload-fixture", "source_hash": source_hash,
                       "native_id": None, "session_id": None, "create_ord": 1,
                       "create_time": None, "model_slug": None},
        "temporal": {"valid_until": None, "supersedes": None},
    }
    text, parsed = _call_tool(
        python=python,
        command=_server_command(python, "canon.local_mcp", "serve"),
        name="canon.validate",
        arguments={"record": record},
        cwd=lane_dir,
    )
    if parsed.get("ok") is not True:
        raise FixtureError(f"canon.validate failed: {parsed}")
    row = _receipt("canon", "canon.validate", parsed, text)
    row["assertions"] = {"record_id": parsed.get("id"), "ok": True}
    return row


RUNNERS = {"gather": _run_gather, "crucible": _run_crucible, "index": _run_index,
           "forum": _run_forum, "plexus": _run_plexus, "mneme": _run_mneme,
           "canon": _run_canon}


def run_all(python: str, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for fixture in fixture_catalog():
        lane = fixture["lane"]
        lane_dir = out / lane
        try:
            result = RUNNERS[lane](python, lane_dir)
        except Exception as exc:
            result = {"lane": lane, "tool": fixture["tool"], "ok": False,
                      "error": f"{type(exc).__name__}: {exc}"}
        result["network"] = fixture["network"]
        result["workflow"] = fixture["workflow"]
        results.append(result)
    verdict = "PASS" if all(row.get("ok") is True for row in results) else "FAIL"
    report = {"schema": SCHEMA, "verdict": verdict, "python": python,
              "output_root": str(out.as_posix()), "fixtures": results}
    report_path = out / "python-lane-fixture-report.json"
    report["report_path"] = str(report_path.as_posix())
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--out", default="D:/fw-ship-sweep-20260910/all-lanes-payloads/fixture-run")
    args = parser.parse_args(argv)
    if args.list:
        print(json.dumps({"schema": SCHEMA, "fixtures": fixture_catalog()}, sort_keys=True))
        return 0
    report = run_all(args.python, Path(args.out))
    print(json.dumps({"verdict": report["verdict"], "report_path": report["report_path"]}, sort_keys=True))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
