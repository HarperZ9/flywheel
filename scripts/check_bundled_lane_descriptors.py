"""Validate source-bound descriptors for bundled frozen gateway lanes."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from harness.bundled_lane_admission import (  # noqa: E402
    build_relay_descriptor, canonical_descriptor_text, descriptor_digest)
from harness.bundled_lane_expectations import expected_bundled_lane  # noqa: E402
from harness.evidence_json import strict_load_json  # noqa: E402

SCHEMA = "flywheel.bundled-lane-descriptor-check/v1"


def check_lane_descriptor(
    repo_root: Path,
    lane: str = "relay",
    *,
    write: bool = False,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict:
    """Return a machine-readable descriptor/source/submodule verdict."""
    repo_root = Path(repo_root).resolve()
    if lane != "relay":
        return _receipt(lane, ["bundled_lane_not_supported"])
    expected = expected_bundled_lane("relay")
    relay_root = repo_root / "relay"
    descriptor_path = repo_root / "packaging" / "bundled-lanes" / "relay.json"
    codes: list[str] = []
    head = _git(relay_root, ["rev-parse", "HEAD"], runner)
    if head is None:
        codes.append("bundled_source_missing")
        head = ""
    elif head != expected["source_commit"]:
        codes.append("bundled_source_commit_mismatch")
    status = _git(relay_root, ["status", "--short", "--untracked-files=all"], runner)
    if status is None:
        codes.append("bundled_source_status_unavailable")
    elif status:
        codes.append("bundled_source_dirty")
    try:
        computed = build_relay_descriptor(relay_root, commit=head or str(
            expected["source_commit"]))
    except (OSError, ValueError) as exc:
        computed = None
        codes.append("bundled_source_manifest_unavailable")
    if write and computed is not None:
        descriptor_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor_path.write_text(canonical_descriptor_text(computed),
                                   encoding="utf-8")
    saved = None
    try:
        saved = strict_load_json(descriptor_path.read_bytes(), max_bytes=4_000_000,
                                max_depth=48)
    except FileNotFoundError:
        codes.append("bundled_descriptor_missing")
    except (OSError, TypeError, ValueError):
        codes.append("bundled_descriptor_invalid")
    if computed is not None:
        source = computed["source"]
        if source["manifest_sha256"] != expected["source_manifest_sha256"]:
            codes.append("bundled_source_digest_mismatch")
        if computed["version"] != expected["version"]:
            codes.append("bundled_component_version_mismatch")
        if descriptor_digest(computed) != expected["descriptor_sha256"]:
            codes.append("bundled_descriptor_digest_mismatch")
    if saved is not None and computed is not None and saved != computed:
        codes.append("bundled_descriptor_source_drift")
    if saved is not None and descriptor_digest(saved) != expected["descriptor_sha256"]:
        codes.append("bundled_descriptor_file_digest_mismatch")
    codes = list(dict.fromkeys(codes))
    receipt = _receipt(lane, codes)
    receipt.update({
        "repo_root": str(repo_root),
        "descriptor_path": str(descriptor_path),
        "source_commit": head,
        "expected_source_commit": expected["source_commit"],
        "expected_source_manifest_sha256": expected["source_manifest_sha256"],
        "expected_descriptor_sha256": expected["descriptor_sha256"],
        "descriptor_sha256": (
            descriptor_digest(saved) if saved is not None else None),
        "computed_descriptor_sha256": (
            descriptor_digest(computed) if computed is not None else None),
        "computed_source_manifest_sha256": (
            computed["source"]["manifest_sha256"] if computed is not None else None),
    })
    return receipt


def _receipt(lane: str, codes: list[str]) -> dict:
    return {
        "schema": SCHEMA,
        "lane": lane,
        "verdict": "HOLD" if codes else "PASS",
        "blocking_codes": codes,
    }


def _git(
    cwd: Path,
    args: list[str],
    runner: Callable[..., subprocess.CompletedProcess],
) -> str | None:
    if not cwd.is_dir():
        return None
    try:
        result = runner(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", default="relay")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    receipt = check_lane_descriptor(
        args.repo_root, args.lane, write=args.write)
    text = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.receipt:
        args.receipt.write_text(text, encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))
    return 1 if args.strict and receipt["verdict"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
