"""Build and verify installed payload file bindings."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA = "flywheel.installed-build-manifest/v1"
PAYLOAD_SCHEMA = "flywheel.installed-payload/v1"
BUILD_ORIGIN = "build"
INSTALLER_GENERATED_ORIGIN = "installer_generated"
TRUST_BOUNDARY = "operator-supplied integrity binding; not external attestation"
ALLOWED_INSTALLER_GENERATED_FILES = frozenset({"unins000.exe", "unins000.dat"})
REQUIRED_BUILD_PAYLOADS = ("flywheel_desktop.exe", "engine/flywheel-gateway.exe")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    payload_roots: Iterable[tuple[Path, str]],
    *,
    source_commit: str,
    version: str,
    installer_generated_files: Iterable[str] = (),
) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root, prefix in payload_roots:
        root = Path(root)
        normalized_prefix = _normalize_prefix(prefix)
        for relative, path in _scan_files(root):
            manifest_path = _join_manifest_path(normalized_prefix, relative)
            lowered = manifest_path.casefold()
            if lowered in seen:
                raise ValueError(f"payload path case collision: {manifest_path}")
            seen.add(lowered)
            files.append({"path": manifest_path, "origin": BUILD_ORIGIN,
                          "sha256": sha256_file(path), "size": path.stat().st_size})
    for value in installer_generated_files:
        manifest_path = _normalize_relative_path(value, "installer_generated")
        _require_installer_generated_path(manifest_path)
        lowered = manifest_path.casefold()
        if lowered in seen:
            raise ValueError(f"payload path case collision: {manifest_path}")
        seen.add(lowered)
        files.append({"path": manifest_path, "origin": INSTALLER_GENERATED_ORIGIN})
    files.sort(key=lambda row: row["path"])
    by_path = {row["path"]: row for row in files if row.get("origin") == BUILD_ORIGIN}
    for required in REQUIRED_BUILD_PAYLOADS:
        if not by_path.get(required, {}).get("sha256"):
            raise ValueError(f"required_build_payload_missing:{required}")
    payload_digest = _payload_digest(files)
    return {
        "schema": MANIFEST_SCHEMA,
        "source_commit": source_commit,
        "version": version,
        "artifacts": {
            "app_sha256": by_path.get("flywheel_desktop.exe", {}).get("sha256", ""),
            "engine_sha256": by_path.get("engine/flywheel-gateway.exe", {}).get("sha256", ""),
        },
        "payload": {
            "schema": PAYLOAD_SCHEMA,
            "files": files,
            "file_count": len(files),
            "build_file_count": sum(1 for row in files if row.get("origin") == BUILD_ORIGIN),
            "installer_generated_file_count": sum(
                1 for row in files if row.get("origin") == INSTALLER_GENERATED_ORIGIN
            ),
            "payload_sha256": payload_digest,
        },
        "trust_boundary": TRUST_BOUNDARY,
    }


def verify_installed_payload(install_root: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    expected = _expected_files(manifest, failures)
    actual = _scan_installed_payload(Path(install_root), failures)
    expected_paths = set(expected)
    actual_paths = set(actual)
    for path in sorted(expected_paths - actual_paths):
        origin = expected[path].get("origin")
        code = "installer_generated_file_missing" if origin == INSTALLER_GENERATED_ORIGIN else "payload_file_missing"
        failures.append(f"{code}:{path}")
    for path in sorted(actual_paths - expected_paths):
        failures.append(f"payload_extra_file:{path}")
    for path in sorted(expected_paths & actual_paths):
        row = expected[path]
        if row.get("origin") == INSTALLER_GENERATED_ORIGIN:
            continue
        target = actual[path]
        want_size = row.get("size")
        if not isinstance(want_size, int) or want_size < 0:
            failures.append(f"payload_file_size_invalid:{path}")
        elif target.stat(follow_symlinks=False).st_size != want_size:
            failures.append(f"payload_file_size_mismatch:{path}")
        want_hash = _hash(row.get("sha256"))
        if not want_hash:
            failures.append(f"payload_file_hash_missing:{path}")
        elif _sha256_file_stable(target, failures, path) != want_hash:
            failures.append(f"payload_file_hash_mismatch:{path}")
    return {
        "schema": "flywheel.installed-payload-binding/v1",
        "match": not failures,
        "failures": failures,
        "expected_file_count": len(expected),
        "observed_file_count": len(actual),
        "build_file_count": sum(1 for row in expected.values()
                                if row.get("origin") == BUILD_ORIGIN),
        "installer_generated_file_count": sum(1 for row in expected.values()
                                              if row.get("origin") == INSTALLER_GENERATED_ORIGIN),
        "payload_sha256": _payload_digest(expected.values()) if expected else None,
    }


def _expected_files(manifest: Mapping[str, Any], failures: list[str]) -> dict[str, dict[str, Any]]:
    if manifest.get("schema") != MANIFEST_SCHEMA:
        failures.append("build_manifest_schema_mismatch")
    payload = manifest.get("payload")
    if not isinstance(payload, Mapping):
        failures.append("payload_manifest_missing")
        return {}
    if payload.get("schema") != PAYLOAD_SCHEMA:
        failures.append("payload_manifest_schema_mismatch")
    rows = payload.get("files")
    if not isinstance(rows, list) or not rows:
        failures.append("payload_files_missing")
        return {}
    expected: dict[str, dict[str, Any]] = {}
    lowered: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            failures.append(f"payload_file_row_malformed:{index}")
            continue
        try:
            path = _normalize_relative_path(row.get("path"), "payload_file")
        except ValueError as exc:
            failures.append(str(exc))
            continue
        lowered.append(path.casefold())
        origin = row.get("origin", BUILD_ORIGIN)
        if origin not in (BUILD_ORIGIN, INSTALLER_GENERATED_ORIGIN):
            failures.append(f"payload_file_origin_unknown:{path}")
            continue
        if origin == INSTALLER_GENERATED_ORIGIN and path not in ALLOWED_INSTALLER_GENERATED_FILES:
            failures.append(f"installer_generated_file_not_allowed:{path}")
            continue
        if origin == INSTALLER_GENERATED_ORIGIN and ("sha256" in row or "size" in row):
            failures.append(f"installer_generated_file_has_build_hash:{path}")
            continue
        expected[path] = dict(row) | {"path": path, "origin": origin}
    for path, count in Counter(lowered).items():
        if count > 1:
            failures.append(f"payload_path_case_collision:{path}")
    return expected


def _scan_installed_payload(root: Path, failures: list[str]) -> dict[str, Path]:
    files: dict[str, Path] = {}
    lowered: list[str] = []
    root = _absolute_without_resolving(root)
    _reject_linked_root_or_ancestors(root, failures)
    if not root.exists():
        failures.append("install_root_missing")
        return files
    if not root.is_dir():
        failures.append("install_root_not_directory")
        return files
    if failures:
        return files
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if _is_link(path):
            failures.append(f"installed_payload_link:{relative}")
            continue
        if path.is_file():
            try:
                normalized = _normalize_relative_path(relative, "installed_file")
            except ValueError as exc:
                failures.append(str(exc))
                continue
            files[normalized] = path
            lowered.append(normalized.casefold())
    for path, count in Counter(lowered).items():
        if count > 1:
            failures.append(f"installed_payload_case_collision:{path}")
    return files


def _scan_files(root: Path) -> list[tuple[str, Path]]:
    failures: list[str] = []
    files = _scan_installed_payload(root, failures)
    if failures:
        raise ValueError("; ".join(failures))
    return sorted(files.items())


def _normalize_relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or value == "":
        raise ValueError(f"{label}_path_missing")
    text = value
    if text != text.strip():
        if any(ord(char) < 32 for char in text):
            raise ValueError(f"{label}_path_control_character")
        raise ValueError(f"{label}_path_not_normalized:{text}")
    if "\\" in text or text.startswith(("/", ".")) or ":" in text:
        raise ValueError(f"{label}_path_not_normalized:{text}")
    parts = text.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"{label}_path_traversal:{text}")
    if any(ord(char) < 32 for char in text):
        raise ValueError(f"{label}_path_control_character")
    return "/".join(parts)


def _normalize_prefix(value: str) -> str:
    return _normalize_relative_path(value, "payload_prefix") if value else ""


def _join_manifest_path(prefix: str, relative: str) -> str:
    return _normalize_relative_path(f"{prefix}/{relative}" if prefix else relative, "payload_file")


def _hash(value: Any) -> str:
    text = str(value).strip().lower() if value is not None else ""
    return text if len(text) == 64 and all(c in "0123456789abcdef" for c in text) else ""


def _payload_digest(rows: Iterable[Mapping[str, Any]]) -> str:
    normalized = [
        {key: row[key] for key in ("path", "origin", "sha256", "size") if key in row}
        for row in rows
    ]
    payload = json.dumps(sorted(normalized, key=lambda row: row["path"]),
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _is_link(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", lambda: False)
    return path.is_symlink() or bool(is_junction())


def _require_installer_generated_path(path: str) -> None:
    if path not in ALLOWED_INSTALLER_GENERATED_FILES:
        raise ValueError(f"installer_generated_file_not_allowed:{path}")


def _absolute_without_resolving(path: Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else Path.cwd() / path


def _reject_linked_root_or_ancestors(root: Path, failures: list[str]) -> None:
    if _is_link(root):
        failures.append("install_root_link:.")
    for ancestor in root.parents:
        if _is_link(ancestor):
            failures.append(f"install_root_ancestor_link:{ancestor.name or ancestor.as_posix()}")


def _file_fingerprint(path: Path) -> tuple[int, int, int, int, int]:
    stat = path.stat(follow_symlinks=False)
    return (int(getattr(stat, "st_dev", 0)), int(getattr(stat, "st_ino", 0)),
            int(stat.st_size), int(stat.st_mtime_ns), int(stat.st_ctime_ns))


def _sha256_file_stable(path: Path, failures: list[str], manifest_path: str) -> str:
    if _is_link(path):
        failures.append(f"installed_payload_link:{manifest_path}")
        return ""
    try:
        before = _file_fingerprint(path)
        digest = sha256_file(path)
        if _is_link(path):
            failures.append(f"installed_payload_link:{manifest_path}")
            return digest
        after = _file_fingerprint(path)
    except FileNotFoundError:
        failures.append(f"payload_file_missing:{manifest_path}")
        return ""
    if before != after:
        failures.append(f"payload_file_changed_during_hash:{manifest_path}")
    return digest


def _parse_payload_root(value: str) -> tuple[Path, str]:
    if "=" not in value:
        return Path(value), ""
    root, prefix = value.rsplit("=", 1)
    return Path(root), prefix


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--payload-root", action="append", required=True,
                       help="source root, optionally ROOT=install/prefix")
    build.add_argument("--installer-generated", action="append", default=[])
    build.add_argument("--source-commit", required=True)
    build.add_argument("--version", required=True)
    build.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        manifest = build_manifest(
            [_parse_payload_root(value) for value in args.payload_root],
            source_commit=args.source_commit,
            version=args.version,
            installer_generated_files=args.installer_generated,
        )
        Path(args.out).write_text(json.dumps(manifest, indent=2, sort_keys=True),
                                  encoding="utf-8")
        print(json.dumps({"schema": "flywheel.installed-payload-binding-build/v1",
                          "out": str(args.out),
                          "file_count": manifest["payload"]["file_count"],
                          "payload_sha256": manifest["payload"]["payload_sha256"]},
                         sort_keys=True))
        return 0
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
