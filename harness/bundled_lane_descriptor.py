"""Descriptor validation and manifest-derived expectations for bundled lanes.

A bundled lane carries its reviewed source inside the frozen gateway payload.
Before that source runs as a child, its descriptor must agree with an
expectation the build already trusts. Relay's expectation is compiled in
(``bundled_lane_expectations``); every other lane's expectation is derived from
its pinned ``python-lane-payloads`` manifest row and re-checked for internal
consistency (the recorded ``component_descriptor_sha256`` must match the
descriptor, and the recorded source ``manifest_sha256`` must match a recompute
of its own file list). Nothing here launches anything: it decides only whether a
descriptor may be admitted, so the relay-specific pieces (descriptor lookup,
allowed tools, source path prefix, entrypoint argv) are parameterized by lane.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Mapping

from .bundled_lane_expectations import EXPECTED_BUNDLED_LANES, expected_bundled_lane
from .evidence_json import canonical_sha256, strict_load_json

SCHEMA = "flywheel.bundled-lane-component/v1"
SOURCE_ALGORITHM = "sha256-canonical-source-manifest/v1"
_MANIFEST_RELATIVE = ("packaging", "python-lane-payloads.jsonl")


def base_dir() -> Path:
    """The payload root: the PyInstaller extraction dir when frozen, else repo."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def default_descriptor_path(name: str = "relay") -> Path:
    return base_dir() / "packaging" / "bundled-lanes" / f"{name}.json"


def descriptor_digest(descriptor: Mapping[str, object]) -> str:
    return "sha256:" + canonical_sha256(dict(descriptor))


def canonical_descriptor_text(descriptor: Mapping[str, object]) -> str:
    return json.dumps(
        dict(descriptor), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def load_manifest_rows(path: str | Path | None = None) -> dict[str, dict]:
    """Every python-lane-payload row keyed by lane name."""
    manifest = (Path(path) if path is not None
                else base_dir() / Path(*_MANIFEST_RELATIVE))
    rows: dict[str, dict] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[str(row["lane"])] = row
    return rows


def expected_from_manifest_row(row: Mapping[str, object]) -> dict[str, object]:
    """The admission expectation for one manifest lane, from its pinned row.

    ``descriptor_sha256`` is the row's separately recorded
    ``component_descriptor_sha256``, so validating a descriptor against this
    expectation still catches a row whose recorded digest was tampered apart from
    its ``component_descriptor``."""
    descriptor = dict(row["component_descriptor"])  # type: ignore[arg-type]
    source = descriptor["source"]
    entry = descriptor["entrypoint"]
    return {
        "schema": descriptor["schema"],
        "name": descriptor["name"],
        "version": descriptor["version"],
        "source_repo": source["repo"],
        "source_commit": source["commit"],
        "source_path": source["path"],
        "source_manifest_sha256": source["manifest_sha256"],
        "descriptor_sha256": row["component_descriptor_sha256"],
        "module": entry["module"],
        "callable": entry["callable"],
        "health_tool": entry["health_tool"],
        "allowed_tools": tuple(descriptor["allowed_tools"]),
    }


def resolve_expected(
    name: str, *, expected: Mapping[str, object] | None = None,
    manifest_rows: Mapping[str, dict] | None = None,
) -> dict | None:
    """The expectation for any bundled lane, or None when the lane is unknown.

    Relay (and anything in ``EXPECTED_BUNDLED_LANES``) uses its compiled anchor;
    every other lane derives its expectation from the pinned manifest row."""
    override = dict(expected or {})
    if name in EXPECTED_BUNDLED_LANES:
        return {**expected_bundled_lane(name), **override}
    row = _manifest_row(name, manifest_rows)
    if row is None:
        return None
    return {**expected_from_manifest_row(row), **override}


def resolve_descriptor(
    name: str, *, descriptor_path: str | Path | None = None,
    manifest_rows: Mapping[str, dict] | None = None,
) -> tuple[dict | None, tuple[str, ...]]:
    """Load the descriptor to validate: an explicit path, else the per-lane
    ``bundled-lanes/<name>.json`` on disk when present, else the descriptor
    carried in the pinned manifest row."""
    if descriptor_path is not None:
        return load_descriptor(Path(descriptor_path))
    if name in EXPECTED_BUNDLED_LANES:
        return load_descriptor(default_descriptor_path(name))
    disk = default_descriptor_path(name)
    if disk.exists():
        return load_descriptor(disk)
    row = _manifest_row(name, manifest_rows)
    if row is None:
        return None, ("bundled_lane_not_supported",)
    return dict(row["component_descriptor"]), ()


def resolve_bundled_lane(
    name: str, *, descriptor_path: str | Path | None = None,
    expected: Mapping[str, object] | None = None,
    manifest_rows: Mapping[str, dict] | None = None,
) -> tuple[dict | None, dict | None, tuple[str, ...]]:
    """Return (descriptor, expected_row, blocking_codes) for one bundled lane."""
    expected_row = resolve_expected(
        name, expected=expected, manifest_rows=manifest_rows)
    if expected_row is None:
        return None, None, ("bundled_lane_not_supported",)
    descriptor, codes = resolve_descriptor(
        name, descriptor_path=descriptor_path, manifest_rows=manifest_rows)
    return descriptor, expected_row, codes


def _manifest_row(
        name: str, manifest_rows: Mapping[str, dict] | None) -> dict | None:
    if manifest_rows is not None:
        return dict(manifest_rows[name]) if name in manifest_rows else None
    try:
        rows = load_manifest_rows()
    except (OSError, ValueError):
        return None
    return rows.get(name)


def load_descriptor(path: Path) -> tuple[dict | None, tuple[str, ...]]:
    try:
        return strict_load_json(path.read_bytes(), max_bytes=4_000_000,
                                max_depth=48), ()
    except FileNotFoundError:
        return None, ("bundled_descriptor_missing",)
    except (OSError, TypeError, ValueError):
        return None, ("bundled_descriptor_invalid",)


def validate_descriptor(
        name: str, descriptor: Mapping[str, object],
        expected: Mapping[str, object]) -> tuple[str, ...]:
    """Every way the descriptor can disagree with what the build expects, as a
    de-duplicated code tuple. The source path prefix and the public argv are
    bound to ``name``, so no lane can smuggle another lane's files or child mode."""
    source = descriptor.get("source")
    entrypoint = descriptor.get("entrypoint")
    if (descriptor.get("schema") != SCHEMA
            or descriptor.get("name") != name
            or not isinstance(source, dict)
            or not isinstance(entrypoint, dict)):
        return ("bundled_descriptor_shape_invalid",)
    codes: list[str] = []
    if descriptor_digest(descriptor) != expected.get("descriptor_sha256"):
        codes.append("bundled_descriptor_digest_mismatch")
    if descriptor.get("version") != expected.get("version"):
        codes.append("bundled_component_version_mismatch")
    if source.get("repo") != expected.get("source_repo"):
        codes.append("bundled_source_repo_mismatch")
    if source.get("commit") != expected.get("source_commit"):
        codes.append("bundled_source_commit_mismatch")
    if source.get("path") != expected.get("source_path"):
        codes.append("bundled_source_path_mismatch")
    if source.get("algorithm") != SOURCE_ALGORITHM:
        codes.append("bundled_source_algorithm_mismatch")
    prefix = str(source.get("path", "")) + "/"
    files = source.get("files")
    if (not isinstance(files, list)
            or any(not manifest_file_row(row, path_prefix=prefix) for row in files)
            or sorted(row["path"] for row in files) != [row["path"] for row in files]):
        codes.append("bundled_source_manifest_invalid")
    else:
        if source.get("file_count") != len(files):
            codes.append("bundled_source_file_count_mismatch")
        if source.get("bytes") != sum(int(row["bytes"]) for row in files):
            codes.append("bundled_source_bytes_mismatch")
        manifest_digest = "sha256:" + canonical_sha256(files)
        if source.get("manifest_sha256") != manifest_digest:
            codes.append("bundled_source_manifest_digest_invalid")
        if source.get("manifest_sha256") != expected.get("source_manifest_sha256"):
            codes.append("bundled_source_digest_mismatch")
    if entrypoint.get("argv") != ["--bundled-lane-mcp", name]:
        codes.append("bundled_entrypoint_invalid")
    if entrypoint.get("module") != expected.get("module"):
        codes.append("bundled_entrypoint_invalid")
    if entrypoint.get("callable") != expected.get("callable"):
        codes.append("bundled_entrypoint_invalid")
    if entrypoint.get("health_tool") != expected.get("health_tool"):
        codes.append("bundled_entrypoint_invalid")
    allowed = descriptor.get("allowed_tools", list(expected.get("allowed_tools", ())))
    if list(allowed) != list(expected.get("allowed_tools", ())):
        codes.append("bundled_allowed_tools_mismatch")
    return tuple(dict.fromkeys(codes))


def component_summary(
        descriptor: Mapping[str, object],
        expected: Mapping[str, object]) -> dict:
    source = descriptor["source"]
    return {
        "schema": "flywheel.bundled-lane-component-summary/v1",
        "name": descriptor["name"],
        "version": descriptor["version"],
        "descriptor_sha256": descriptor_digest(descriptor),
        "source_repo": source["repo"],
        "source_commit": source["commit"],
        "source_manifest_sha256": source["manifest_sha256"],
        "file_count": source["file_count"],
        "bytes": source["bytes"],
        "module": expected["module"],
        "health_tool": expected["health_tool"],
        "allowed_tools": list(expected["allowed_tools"]),
        "does_not_prove": list(descriptor.get("does_not_prove", ())),
    }


def manifest_file_row(value: object, *, path_prefix: str) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        set(value) == {"path", "bytes", "sha256"}
        and isinstance(value.get("path"), str)
        and value["path"].startswith(path_prefix)
        and value["path"].endswith(".py")
        and isinstance(value.get("bytes"), int)
        and value["bytes"] >= 0
        and isinstance(value.get("sha256"), str)
        and len(value["sha256"]) == 71
        and value["sha256"].startswith("sha256:")
    )


def module_importable(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False
