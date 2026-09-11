"""Validate Python flagship lane payload source pins and descriptor candidates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.evidence_json import canonical_sha256

EXPECTED_LANES = ("gather", "crucible", "index", "forum", "plexus", "mneme", "canon")
VERSION_MISMATCHES = {"gather", "index", "forum", "mneme", "canon"}
ASYNC_BLOCKED = {"forum"}
MANIFEST = Path("packaging/python-lane-payloads.jsonl")
SOURCE_ALGORITHM = "sha256-canonical-source-manifest/v1"


class ManifestError(RuntimeError):
    pass


def load_manifest(path: Path = MANIFEST) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ManifestError(f"line {number}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ManifestError(f"line {number}: row is not an object")
        rows.append(row)
    return rows


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ManifestError(message)


def _digest(value: dict[str, Any] | list[Any]) -> str:
    return "sha256:" + canonical_sha256(value)


def validate_manifest(rows: list[dict[str, Any]]) -> dict[str, Any]:
    lanes = [str(row.get("lane")) for row in rows]
    _require(tuple(lanes) == EXPECTED_LANES, f"unexpected lane order/set: {lanes!r}")
    seen_mismatches: set[str] = set()
    seen_async: set[str] = set()
    descriptor_digests: dict[str, str] = {}
    source_digests: dict[str, str] = {}
    for row in rows:
        lane = str(row["lane"])
        descriptor = row.get("component_descriptor")
        _require(isinstance(descriptor, dict), f"{lane}: component_descriptor missing")
        source = descriptor.get("source")
        _require(isinstance(source, dict), f"{lane}: source missing")
        files = source.get("files")
        _require(isinstance(files, list) and files, f"{lane}: source files missing")
        _require(source.get("algorithm") == SOURCE_ALGORITHM, f"{lane}: source algorithm mismatch")
        _require(source.get("file_count") == len(files), f"{lane}: file_count mismatch")
        _require(source.get("bytes") == sum(int(item["bytes"]) for item in files), f"{lane}: bytes mismatch")
        _require(source.get("manifest_sha256") == _digest(files), f"{lane}: source manifest digest mismatch")
        _require(row.get("component_descriptor_sha256") == _digest(descriptor), f"{lane}: descriptor digest mismatch")
        _require(descriptor.get("schema") == "flywheel.bundled-lane-component/v1", f"{lane}: descriptor schema mismatch")
        _require(descriptor.get("name") == lane, f"{lane}: descriptor name mismatch")
        _require(descriptor.get("version") == row["owner_project"]["version"], f"{lane}: descriptor version mismatch")
        entrypoint = descriptor.get("entrypoint")
        _require(isinstance(entrypoint, dict), f"{lane}: entrypoint missing")
        _require(entrypoint.get("argv") == ["--bundled-lane-mcp", lane], f"{lane}: public argv mismatch")
        mcp = row.get("mcp")
        _require(isinstance(mcp, dict), f"{lane}: mcp block missing")
        _require(entrypoint.get("module") == mcp.get("module"), f"{lane}: module mismatch")
        _require(entrypoint.get("callable") == mcp.get("callable"), f"{lane}: callable mismatch")
        _require(entrypoint.get("health_tool") == mcp.get("health_tool"), f"{lane}: health tool mismatch")
        allowed = [mcp.get("health_tool"), mcp.get("doctor_tool")]
        _require(descriptor.get("allowed_tools") == allowed, f"{lane}: allowed tools mismatch")
        tools = set(mcp.get("static_tool_names") or [])
        _require(set(allowed) <= tools, f"{lane}: allowed tool not in static tool list")
        _require(mcp.get("callable_style") in {"sync", "async"}, f"{lane}: callable style invalid")
        if mcp.get("callable_style") == "async":
            seen_async.add(lane)
            _require(mcp.get("contract_status") == "needs_async_dispatch_or_wrapper", f"{lane}: async blocker not recorded")
        else:
            _require(mcp.get("contract_status") == "compatible_with_sync_dispatcher", f"{lane}: sync status mismatch")
        project = row.get("owner_project")
        _require(isinstance(project, dict), f"{lane}: project block missing")
        _require(project.get("runtime_dependencies") == [], f"{lane}: runtime dependencies must be explicit and empty")
        _require(bool(project.get("license_files")), f"{lane}: license file evidence missing")
        _require(mcp.get("module") in set(row.get("hidden_imports") or []), f"{lane}: mcp module absent from hidden imports")
        if row.get("owner_project", {}).get("version") != row.get("flywheel_registry_expected_version"):
            seen_mismatches.add(lane)
        descriptor_digests[lane] = str(row["component_descriptor_sha256"])
        source_digests[lane] = str(source["manifest_sha256"])
    _require(seen_mismatches == VERSION_MISMATCHES, f"version mismatch set changed: {sorted(seen_mismatches)!r}")
    _require(seen_async == ASYNC_BLOCKED, f"async blocker set changed: {sorted(seen_async)!r}")
    return {
        "schema": "flywheel.python-lane-payload-manifest-check/v1",
        "verdict": "PASS",
        "lanes": lanes,
        "version_mismatches": sorted(seen_mismatches),
        "async_blockers": sorted(seen_async),
        "descriptor_sha256": descriptor_digests,
        "source_manifest_sha256": source_digests,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", nargs="?", default=str(MANIFEST))
    args = parser.parse_args(argv)
    try:
        report = validate_manifest(load_manifest(Path(args.manifest)))
    except ManifestError as exc:
        print(json.dumps({"verdict": "FAIL", "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
