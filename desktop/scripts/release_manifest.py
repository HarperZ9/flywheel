"""release_manifest.py -- default-reject staging manifests.

build: hash every staged byte and emit flywheel.windows-payload-manifest/v1.
Only files the policy explicitly allows (normalized relative paths, no
globs) may appear; anything else is a refusal, and the allowlist is never
derived from what happens to be in the staging tree.
verify: re-hash the tree against a manifest; any extra, missing,
symlinked, or case-colliding file fails.

CLI:
  python release_manifest.py build  --staging-root DIR --policy JSON
  python release_manifest.py verify --staging-root DIR --policy JSON --manifest JSON
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

MANIFEST_SCHEMA = "flywheel.windows-payload-manifest/v1"
_POLICY_KEYS = ("allow", "reject_globs", "reject_symlinks",
                "reject_alternate_data_streams", "reject_case_collisions",
                "reject_reserved_names")
_RESERVED = {"con", "prn", "aux", "nul"} | {
    f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}
_STREAM_SEP = ":"
_RESERVED_CHARS = '<>:"|?*'


def _refuse(msg: str) -> None:
    raise ValueError(msg)


def _load_policy(path: Path) -> dict:
    policy = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(policy, dict):
        _refuse("the payload policy is not an object")
    for key in _POLICY_KEYS:
        if key not in policy:
            _refuse(f"the payload policy lacks {key}")
    if policy.get("reject_globs") is not True:
        _refuse("the payload policy must reject globs")
    allow = policy.get("allow")
    if not isinstance(allow, list):
        _refuse("the payload allowlist is missing")
    for row in allow:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            _refuse("every allow row names a normalized relative path")
        candidate = row["path"]
        if any(sep in candidate for sep in ("*", "?", "[")):
            _refuse(f"the allowlist must not contain globs: {candidate!r}")
        if candidate.startswith("/") or ":" in candidate.split("/")[0] \
                or ".." in candidate.split("/"):
            _refuse(f"the allowlist must stay relative: {candidate!r}")
        stem = candidate.split("/")[-1].split(".")[0].lower()
        if stem in _RESERVED or any(c in _RESERVED_CHARS for c in candidate):
            _refuse(f"the allowlist names a reserved name: {candidate!r}")
    return policy


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _staged_relative_files(staging_root: Path) -> list[Path]:
    files = []
    for path in staging_root.rglob("*"):
        if path.is_symlink() or path.is_junction():
            _refuse(f"a symlink or reparse point is staged: {path.name}")
        if path.is_file():
            if ":" in path.name:
                _refuse("an alternate data stream is staged")
            files.append(path.relative_to(staging_root))
    lowered = [str(f).lower() for f in files]
    if len(lowered) != len(set(lowered)):
        _refuse("case-colliding files are staged")
    return sorted(files)


def build_manifest(staging_root: Path, *, policy_path: Path) -> dict:
    staging_root = Path(staging_root)
    policy = _load_policy(Path(policy_path))
    allowed_paths = {row["path"]: row for row in policy["allow"]}
    rows = []
    for relative in _staged_relative_files(staging_root):
        key = relative.as_posix()
        row = allowed_paths.get(key)
        if row is None:
            _refuse(f"staged file is not in the policy allowlist: {key}")
        rows.append({
            "path": key,
            "sha256": _sha256(staging_root / relative),
            "size": (staging_root / relative).stat().st_size,
            "purpose": str(row.get("purpose", "")),
            "component": str(row.get("component", "")),
            "license": str(row.get("license", "")),
        })
    for allowed in allowed_paths:
        if allowed not in {r["path"] for r in rows}:
            _refuse(f"an allowlisted file is missing from staging: {allowed}")
    return {
        "schema": MANIFEST_SCHEMA,
        "file_count": len(rows),
        "files": sorted(rows, key=lambda r: r["path"]),
        "total_sha256": hashlib.sha256(
            "\n".join(r["sha256"] for r in
                      sorted(rows, key=lambda r: r["path"])).encode()
        ).hexdigest(),
    }


def verify_manifest(staging_root: Path, manifest: dict,
                    *, policy_path: Path) -> dict:
    staging_root = Path(staging_root)
    rebuilt = build_manifest(staging_root, policy_path=policy_path)
    if rebuilt != manifest:
        _refuse("the staged tree does not match the manifest")
    return {"schema": "flywheel.windows-payload-verification/v1",
            "match": True, "file_count": manifest["file_count"],
            "total_sha256": manifest["total_sha256"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "verify"):
        child = sub.add_parser(name)
        child.add_argument("--staging-root", required=True)
        child.add_argument("--policy", required=True)
        if name == "verify":
            child.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            manifest = build_manifest(Path(args.staging_root),
                                      policy_path=Path(args.policy))
            print(json.dumps(manifest, indent=2, sort_keys=True))
            return 0
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        result = verify_manifest(Path(args.staging_root), manifest,
                                 policy_path=Path(args.policy))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
