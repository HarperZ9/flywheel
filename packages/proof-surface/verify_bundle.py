#!/usr/bin/env python3
"""verify_bundle.py -- a zero-dependency, standalone verifier for a proof-surface
bundle. Pure Python stdlib, no proof_surface import. A reviewer holding only a
bundle directory re-derives its verdict offline:

    python verify_bundle.py path/to/bundle-dir

It re-reads every artifact named in ``bundle.json``, recomputes its sha256 from
the bytes on disk, and compares to the recorded digest. It then independently
recomputes ``bundle_hash`` over the recorded ``name:sha256`` pairs, so a manifest
edited after the fact is caught even when the files are untouched. One verdict
line is printed and the exit code carries it: 0 MATCH, 1 DRIFT (a digest or
bundle_hash mismatch), 2 UNVERIFIABLE (bundle.json missing or unreadable).

This is the standalone twin of the in-package verify_receipts, the way relay
ships both cert.py and verify_cert.py. It is not a schema check: it re-derives
the same hashes the producer sealed and reports what fails to reproduce.
"""
import hashlib
import json
import sys
from pathlib import Path


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_bundle(target):
    """Return (exit_code, verdict_line): 0 match, 1 drift, 2 unverifiable."""
    target = Path(target)
    bundle_path = target / "bundle.json" if target.is_dir() else target
    if not bundle_path.exists():
        return 2, f"UNVERIFIABLE  no bundle.json at {bundle_path}"
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return 2, f"UNVERIFIABLE  cannot read bundle.json: {exc}"
    if not isinstance(bundle, dict) or not isinstance(bundle.get("files"), list):
        return 2, "UNVERIFIABLE  bundle.json is not a manifest object with a files array"

    out = bundle_path.parent
    drift = []
    pairs = []
    for entry in bundle["files"]:
        name = entry.get("name") if isinstance(entry, dict) else None
        recorded = entry.get("sha256") if isinstance(entry, dict) else None
        if not isinstance(name, str) or not name:
            drift.append("a files[] entry has no name to re-check")
            continue
        pairs.append(f"{name}:{recorded}\n")
        artifact = out / name
        if not artifact.exists():
            drift.append(f"{name}: listed artifact is missing")
            continue
        if _digest(artifact) != recorded:
            drift.append(f"{name}: recomputed sha256 does not match the recorded digest")

    manifest_hash = hashlib.sha256("".join(pairs).encode("utf-8")).hexdigest()
    if manifest_hash != bundle.get("bundle_hash"):
        drift.append("bundle_hash does not re-derive from the recorded file digests")

    if drift:
        return 1, "DRIFT  " + "; ".join(drift)
    return 0, "MATCH  every artifact digest and bundle_hash re-derives from disk"


def main(argv):
    if not argv:
        print("usage: python verify_bundle.py <bundle-dir>", file=sys.stderr)
        return 2
    code, line = verify_bundle(argv[0])
    print(line)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
