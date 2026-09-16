"""Studio body runtime manifest validation helpers."""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

MANIFEST_SCHEMA = "flywheel.studio-body-runtime-manifest/v1"
PAYLOAD_SCHEMA = "flywheel.studio-runtime-payload/v1"
STUDIO_RUNTIME_MANIFEST_ENV = "FLYWHEEL_STUDIO_BODY_RUNTIME_MANIFEST"
STUDIO_RUNTIME_PAYLOAD_ENV = "FLYWHEEL_STUDIO_BODY_RUNTIME_PAYLOAD"
ENGINE_DESTINATION = Path("harness/studio_engine_bundle")
PYTHON_RUNTIME_DIR = Path("studio_runtime_python")
PAYLOAD_MANIFEST_DESTINATION = Path(
    "packaging/studio-body/STUDIO-BODY-RUNTIME-MANIFEST.json")
LICENSE_DESTINATION = Path("licenses/studio-runtime")

PACKAGE_SECTIONS = (
    "accountable_surface",
    "coherence_membrane",
    "proof_surface",
)
BODY_HIDDENIMPORTS = (
    "harness.live_screen_cleanup",
    "harness.live_screen_delivery",
    "harness.live_screen_delivery_records",
    "harness.live_screen_feed",
    "harness.live_screen_gateway_contract",
    "harness.live_screen_gateway_mount",
    "harness.live_screen_gateway_sessions",
    "harness.live_screen_provider_delivery",
    "harness.live_screen_route",
    "harness.live_screen_scheduler",
    "harness.live_screen_sources",
    "harness.live_screen_startup",
    "harness.live_screen_types",
    "harness.studio_body_capture",
    "harness.studio_body_contract",
    "harness.studio_body_engine",
    "harness.studio_body_engine_contract",
    "harness.studio_body_engine_effector",
    "harness.studio_body_engine_render",
    "harness.studio_body_engine_resolution",
    "harness.studio_body_live_screen",
    "harness.studio_body_route",
    "harness.studio_body_route_status",
    "harness.studio_body_sound",
)
RAW_SHA256 = re.compile(r"^[0-9a-f]{64}$")
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
TOP_LEVEL_KEYS = {
    "schema",
    "created_at",
    "studio_engine",
    "accountable_surface",
    "coherence_membrane",
    "proof_surface",
    "packaging_actions",
    "release_boundary",
}
ENGINE_KEYS = {
    "status",
    "root",
    "source_root",
    "required_files",
    "required_file_hashes",
    "schema",
    "basis",
    "distribution_name",
    "package_version",
    "expected_head",
}
PACKAGE_KEYS = {"status", "source_root", "entry_modules", "files", "file_hashes"}


def load_runtime_manifest(path: Path | str) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise RuntimeError(f"runtime manifest is missing: {source}")
    try:
        doc = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("runtime manifest is not valid JSON") from exc
    if not isinstance(doc, dict) or doc.get("schema") != MANIFEST_SCHEMA:
        raise RuntimeError("runtime manifest schema mismatch")
    validate_manifest_shape(doc)
    return doc


def validate_manifest_shape(doc: Mapping[str, Any]) -> None:
    _reject_extra_keys(doc, TOP_LEVEL_KEYS, "manifest")
    _reject_extra_keys(doc.get("studio_engine"), ENGINE_KEYS, "studio_engine")
    for section in PACKAGE_SECTIONS:
        _reject_extra_keys(doc.get(section), PACKAGE_KEYS, section)


def _reject_extra_keys(value: Any, allowed: set[str], label: str) -> None:
    if not isinstance(value, Mapping):
        raise RuntimeError(f"{label} must be an object")
    extra = sorted(set(value) - allowed)
    if extra:
        raise RuntimeError(f"unsupported manifest field in {label}: {extra[0]}")


def validate_manifest_sources(doc: Mapping[str, Any]) -> list[tuple[str, Path, Path]]:
    validate_manifest_shape(doc)
    files = section_rows(doc, "studio_engine")
    for section in PACKAGE_SECTIONS:
        rows = section_rows(doc, section)
        validate_entry_modules(doc[section], {rel.as_posix() for _, _, rel in rows})
        files.extend(rows)
    return files


def section_rows(
    doc: Mapping[str, Any],
    section: str,
    *,
    require_source: bool = True,
) -> list[tuple[str, Path, Path]]:
    data = doc.get(section)
    if not isinstance(data, dict) or data.get("status") != "ready":
        raise RuntimeError(f"{section} runtime is not ready")
    file_key = "required_files" if section == "studio_engine" else "files"
    hash_key = "required_file_hashes" if section == "studio_engine" else "file_hashes"
    rels = relative_files(data.get(file_key), f"{section}.{file_key}")
    hashes = data.get(hash_key)
    if not isinstance(hashes, dict):
        raise RuntimeError(f"{section}.{hash_key} is missing")
    source_root = Path(data.get("root") or data.get("source_root") or ".")
    if require_source:
        if "root" not in data and "source_root" not in data:
            raise RuntimeError(f"{section} source root is missing")
        source_root = source_root.expanduser().resolve()
        if not source_root.is_dir():
            raise RuntimeError(f"{section} source root is absent")
        if section == "studio_engine":
            validate_studio_engine_identity(source_root / "pyproject.toml")
    rows = []
    for rel in rels:
        expected = hashes.get(rel.as_posix())
        if not isinstance(expected, str) or RAW_SHA256.fullmatch(expected) is None:
            raise RuntimeError(f"{section} hash is invalid for {rel.as_posix()}")
        if require_source:
            path = (source_root / rel).resolve()
            try:
                path.relative_to(source_root)
            except ValueError as exc:
                raise RuntimeError(
                    f"{section} source file escaped root: {rel.as_posix()}") from exc
            if not path.is_file():
                raise RuntimeError(f"{section} source file is missing: {rel.as_posix()}")
            assert_hash(path, expected)
        rows.append((section, source_root, rel))
    return rows


def relative_files(value: Any, name: str) -> list[Path]:
    if not isinstance(value, list) or not value:
        raise RuntimeError(f"{name} is missing")
    seen, out = set(), []
    for item in value:
        if not isinstance(item, str):
            raise RuntimeError(f"{name} must contain strings")
        if not item or item == "." or item.startswith("./"):
            raise RuntimeError(f"{name} must stay relative: {item!r}")
        if "/./" in item or item.endswith("/.") or ":" in item:
            raise RuntimeError(f"{name} must stay relative: {item!r}")
        if CONTROL_CHARS.search(item):
            raise RuntimeError(f"{name} must stay relative: {item!r}")
        rel = PurePosixPath(item)
        if rel.is_absolute() or ".." in rel.parts or "\\" in item or item.endswith("/"):
            raise RuntimeError(f"{name} must stay relative: {item!r}")
        if Path(rel.as_posix()).is_absolute():
            raise RuntimeError(f"{name} must stay relative: {item!r}")
        key = rel.as_posix().lower()
        if key in seen:
            raise RuntimeError(f"{name} contains a case collision: {item}")
        seen.add(key)
        out.append(Path(rel.as_posix()))
    return out


def validate_entry_modules(section: Mapping[str, Any], files: set[str]) -> None:
    entries = section.get("entry_modules")
    if not isinstance(entries, list) or not entries:
        raise RuntimeError("runtime section lacks entry modules")
    for module in entries:
        if not isinstance(module, str) or module.startswith("studio_engine"):
            raise RuntimeError("runtime entry module is invalid")
        if not (module_file(module) & files):
            raise RuntimeError(f"entry module absent from closure: {module}")


def module_file(module: str) -> set[str]:
    base = module.replace(".", "/")
    return {base + ".py", base + "/__init__.py"}


def module_name(relative: str) -> str | None:
    if not relative.endswith(".py"):
        return None
    stem = relative[:-3]
    if stem.endswith("/__init__"):
        return stem[:-9].replace("/", ".")
    return stem.replace("/", ".")


def hiddenimports_from_manifest(doc: Mapping[str, Any]) -> set[str]:
    modules = set()
    for section in PACKAGE_SECTIONS:
        data = doc[section]
        modules.update(data["entry_modules"])
        modules.update(
            name for rel in data["files"] if (name := module_name(rel)) is not None)
    return modules


def expected_hash(doc: Mapping[str, Any], payload_relative: str) -> str:
    engine_prefix = ENGINE_DESTINATION.as_posix() + "/"
    if payload_relative.startswith(engine_prefix):
        rel = payload_relative[len(engine_prefix):]
        return doc["studio_engine"]["required_file_hashes"][rel]
    rel = payload_relative[len(PYTHON_RUNTIME_DIR.as_posix()) + 1:]
    for section in PACKAGE_SECTIONS:
        if rel in doc[section]["file_hashes"]:
            return doc[section]["file_hashes"][rel]
    raise RuntimeError(f"payload hash source is unknown: {payload_relative}")


def packaged_manifest(doc: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": MANIFEST_SCHEMA,
        "payload_schema": PAYLOAD_SCHEMA,
        "created_at": deepcopy(doc.get("created_at")),
        "studio_engine": _public_section(doc["studio_engine"], (
            "status",
            "required_files",
            "required_file_hashes",
            "schema",
            "basis",
            "distribution_name",
            "package_version",
            "expected_head",
        )),
        "accountable_surface": _public_section(doc["accountable_surface"], (
            "status", "entry_modules", "files", "file_hashes")),
        "coherence_membrane": _public_section(doc["coherence_membrane"], (
            "status", "entry_modules", "files", "file_hashes")),
        "proof_surface": _public_section(doc["proof_surface"], (
            "status", "entry_modules", "files", "file_hashes")),
        "payload_layout": {
        "studio_engine": ENGINE_DESTINATION.as_posix(),
        "python_packages": PYTHON_RUNTIME_DIR.as_posix(),
        "license_notices": LICENSE_DESTINATION.as_posix(),
        },
    }


def _public_section(section: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: deepcopy(section[key]) for key in keys if key in section}


def contains_source_root(value: Any) -> bool:
    if isinstance(value, dict):
        return any(k in {"root", "source_root"} or contains_source_root(v)
                   for k, v in value.items())
    if isinstance(value, list):
        return any(contains_source_root(item) for item in value)
    return False


def validate_studio_engine_identity(pyproject: Path) -> None:
    if not pyproject.is_file():
        raise RuntimeError("Studio Engine pyproject.toml is missing")
    try:
        project = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {})
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeError("Studio Engine pyproject.toml is invalid") from exc
    name = project.get("name")
    normalized = re.sub(r"[-_.]+", "-", name).lower() if isinstance(name, str) else ""
    if normalized != "studio-engine":
        raise RuntimeError("Studio Engine project.name must be studio-engine")


def assert_hash(path: Path, expected: str) -> None:
    actual = sha256(path)
    if actual != expected:
        raise RuntimeError(f"hash mismatch for {path.name}: {actual} != {expected}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
