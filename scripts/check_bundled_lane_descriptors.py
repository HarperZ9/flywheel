"""Validate source-bound descriptors for bundled frozen gateway lanes.

The relay descriptor hashes the bytes a reproducible checkout of the pinned
commit writes, read with ``git cat-file --filters`` under ``core.autocrlf=false``
and ``core.eol=lf``, the way ``generate_python_lane_payload_row.py`` reads every
payload row. Hashing the working tree instead pinned the CRLF form a Windows
checkout with ``core.autocrlf=true`` writes, so the pin depended on the build
host's git setting and differed from the tag's bytes and the relay payload row.
A clean status still ties the working tree the freeze compiles to that commit.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
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
        commit = head or str(expected["source_commit"])
        computed = build_relay_descriptor(relay_root, commit=commit,
                                          files=committed_source_files(relay_root, commit))
    except (OSError, ValueError, subprocess.SubprocessError):
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


def committed_source_files(relay_root: Path, commit: str,
                           subdir: str = "src/relay") -> list[dict[str, object]] | None:
    """The ``*.py`` manifest of ``subdir`` at ``commit``, as LF checkout bytes.

    None when ``relay_root`` is no git checkout (a source tree without its
    ``.git``), so the caller hashes the working tree; a real build always has
    one, and a checkout that cannot be read raises ValueError."""
    if not (Path(relay_root) / ".git").exists():
        return None
    root = str(relay_root)
    listing = subprocess.run(
        ["git", "-C", root, "ls-tree", "-r", "-z", commit, "--", subdir],
        capture_output=True, timeout=60, check=False)
    if listing.returncode != 0:
        raise ValueError("relay source listing unavailable")
    pairs = []
    for entry in listing.stdout.decode("utf-8").split("\0"):
        if not entry:
            continue
        meta, path = entry.split("\t", 1)
        if meta.split()[1] == "blob" and path.endswith(".py"):
            pairs.append((path, meta.split()[2]))
    pairs.sort()
    stdin = "".join(f"{sha} {path}\n" for path, sha in pairs).encode("utf-8")
    batch = subprocess.run(
        ["git", "-C", root, "-c", "core.autocrlf=false", "-c", "core.eol=lf",
         "cat-file", "--batch", "--filters"],
        input=stdin, capture_output=True, timeout=120, check=False)
    if batch.returncode != 0:
        raise ValueError("relay source bytes unavailable")
    out, pos, rows = batch.stdout, 0, []
    for path, sha in pairs:
        end = out.index(b"\n", pos)
        header = out[pos:end].split()
        if len(header) != 3 or header[0].decode() != sha:
            raise ValueError(f"unexpected cat-file header for {path}")
        data = out[end + 1:end + 1 + int(header[2])]
        pos = end + 1 + int(header[2]) + 1
        rows.append({"path": path, "bytes": len(data),
                     "sha256": "sha256:" + sha256(data).hexdigest()})
    return rows


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
