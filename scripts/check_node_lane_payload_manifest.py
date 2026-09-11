"""Validate build-only Node lane payload source pins and descriptor candidates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from node_lane_payload_lib import PayloadError, canonical_sha256, load_jsonl, require

EXPECTED_LANES = ("learn", "telos")
MANIFEST = Path("packaging/node-lane-payloads.jsonl")
RUNTIME_SHA = "sha256:158f7685b44de51f6c0df1d153526cbcd3e1bc739a8dfc607721cef75de9e541"


def _digest(value: dict[str, Any] | list[Any]) -> str:
    return "sha256:" + canonical_sha256(value)


def validate_manifest(rows: list[dict[str, Any]]) -> dict[str, Any]:
    lanes = [str(row.get("lane")) for row in rows]
    require(tuple(lanes) == EXPECTED_LANES, f"unexpected lane order/set: {lanes!r}")
    descriptors: dict[str, str] = {}
    server_info: dict[str, dict[str, str]] = {}
    source_receipts: dict[str, str] = {}
    for row in rows:
        lane = str(row["lane"])
        require(row.get("schema") == "flywheel.node-lane-payload/v1", f"{lane}: schema mismatch")
        runtime = row.get("runtime")
        require(isinstance(runtime, dict), f"{lane}: runtime missing")
        require(runtime.get("version") == "24.21.0", f"{lane}: runtime version mismatch")
        require(runtime.get("archive_sha256") == RUNTIME_SHA, f"{lane}: runtime hash mismatch")
        source = row.get("source")
        require(isinstance(source, dict), f"{lane}: source missing")
        require(source.get("engine") == "node>=20", f"{lane}: engine range missing")
        entrypoint = row.get("entrypoint")
        require(isinstance(entrypoint, dict), f"{lane}: entrypoint missing")
        tools = row.get("tools")
        require(isinstance(tools, list) and tools, f"{lane}: tools missing")
        allowed = entrypoint.get("allowed_tools")
        require(allowed == [entrypoint.get("status_tool"), entrypoint.get("doctor_tool")], f"{lane}: allowed tools mismatch")
        require(set(allowed) <= set(tools), f"{lane}: allowed tool absent from tools")
        descriptor = row.get("component_descriptor")
        require(isinstance(descriptor, dict), f"{lane}: descriptor missing")
        require(descriptor.get("schema") == "flywheel.node-lane-component-candidate/v1", f"{lane}: descriptor schema mismatch")
        require(descriptor.get("name") == lane, f"{lane}: descriptor name mismatch")
        require(descriptor.get("runtime") == runtime, f"{lane}: descriptor runtime drift")
        require(descriptor.get("entrypoint") == entrypoint, f"{lane}: descriptor entrypoint drift")
        require(descriptor.get("tools") == tools, f"{lane}: descriptor tool drift")
        require(row.get("component_descriptor_sha256") == _digest(descriptor), f"{lane}: descriptor digest mismatch")
        if lane == "learn":
            release = source.get("parent_release") or {}
            delta = source.get("source_delta") or {}
            require(release.get("git_head") == delta.get("parent_commit"), "learn: parent release/delta mismatch")
            require(delta.get("commit") != delta.get("parent_commit"), "learn: missing source delta commit")
            require(entrypoint.get("server_info") == {"name": "learn", "version": "1.6.0"}, "learn: serverInfo mismatch")
            source_receipts[lane] = str(delta.get("commit"))
        if lane == "telos":
            require(source.get("commit") == "344e6fd9c5a010b8e7375cb359920b1517faeb20", "telos: source commit mismatch")
            require(source.get("registry_status") == "unpublished-owned-source-bundle", "telos: registry status mismatch")
            require(entrypoint.get("server_info") == {"name": "project-telos-telos", "version": "0.3.0"}, "telos: serverInfo mismatch")
            source_receipts[lane] = str(source.get("commit"))
        descriptors[lane] = str(row["component_descriptor_sha256"])
        server_info[lane] = entrypoint["server_info"]
    return {
        "schema": "flywheel.node-lane-payload-manifest-check/v1",
        "verdict": "PASS",
        "lanes": lanes,
        "runtime": {"version": "24.21.0", "archive_sha256": RUNTIME_SHA},
        "server_info": server_info,
        "component_descriptor_sha256": descriptors,
        "source_receipts": source_receipts,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", nargs="?", default=str(MANIFEST))
    args = parser.parse_args(argv)
    try:
        report = validate_manifest(load_jsonl(Path(args.manifest)))
    except PayloadError as exc:
        print(json.dumps({"verdict": "FAIL", "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
