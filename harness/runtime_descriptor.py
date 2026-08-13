"""Public-safe, reproducible identity for the Python/pytest decision runtime."""
from __future__ import annotations

import hashlib
from importlib import metadata
from pathlib import Path, PurePosixPath
import sys

from .receipt_fields import canonical

SCHEMA = "flywheel.pytest-runtime/v1"
MAX_SOURCE_FILES = 1024
MAX_SOURCE_FILE_BYTES = 1_048_576
MAX_SOURCE_BYTES = 8_388_608
RUNTIME_LIMITS = (
    "NOT_PROVES_FULL_RUNTIME_DEPENDENCY_CLOSURE: the descriptor binds Python "
    "identity, pytest Python sources, and declared requirements, not stdlib, "
    "native code, or transitive dependency sources.",
    "NOT_PROVES_CROSS_ENVIRONMENT_REPRODUCTION: matching descriptors are "
    "required; execution under a different runtime is not proved equivalent.",
)


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical(value).encode()).hexdigest()


def _read(path: Path) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(MAX_SOURCE_FILE_BYTES + 1)
    if len(data) > MAX_SOURCE_FILE_BYTES:
        raise ValueError("pytest source file exceeds descriptor byte limit")
    return data


def _pytest_identity() -> dict:
    try:
        distribution = metadata.distribution("pytest")
    except metadata.PackageNotFoundError as exc:
        raise ValueError("pytest distribution metadata is unavailable") from exc
    files, total = [], 0
    for item in sorted(distribution.files or (), key=lambda value: value.as_posix()):
        rel = PurePosixPath(item.as_posix())
        if rel.suffix != ".py" or rel.parts[0] not in {"pytest", "_pytest"}:
            continue
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("pytest distribution contains an unsafe source path")
        data = _read(Path(distribution.locate_file(item)))
        total += len(data)
        if len(files) >= MAX_SOURCE_FILES or total > MAX_SOURCE_BYTES:
            raise ValueError("pytest source manifest exceeds descriptor limits")
        files.append({"path": rel.as_posix(), "bytes": len(data),
                      "sha256": "sha256:" + hashlib.sha256(data).hexdigest()})
    if not files:
        raise ValueError("pytest distribution has no reproducible Python sources")
    source = {"algorithm": "sha256-canonical-source-manifest/v1",
              "file_count": len(files), "bytes": total, "files": files,
              "manifest_sha256": _digest(files)}
    identity = {"distribution": "pytest", "version": distribution.version,
                "requires_dist": sorted(distribution.requires or []),
                "source": source}
    return {**identity, "identity_sha256": _digest(identity)}


def pytest_runtime_descriptor() -> dict:
    """Describe the deciding runtime without serializing host filesystem paths."""
    python = {"implementation": sys.implementation.name,
              "version": list(sys.version_info[:3]),
              "cache_tag": sys.implementation.cache_tag or "",
              "abi_flags": getattr(sys, "abiflags", ""),
              "byteorder": sys.byteorder, "platform": sys.platform}
    descriptor = {"schema": SCHEMA, "python": python,
                  "pytest": _pytest_identity(),
                  "does_not_prove": list(RUNTIME_LIMITS)}
    validate_runtime_descriptor(descriptor)
    return descriptor


def _sha(value: object) -> bool:
    return (type(value) is str and len(value) == 71 and value.startswith("sha256:")
            and all(char in "0123456789abcdef" for char in value[7:]))


def validate_runtime_descriptor(value: object) -> dict:
    """Strictly validate descriptor shape and its two independently rehashed IDs."""
    if type(value) is not dict or set(value) != {
            "schema", "python", "pytest", "does_not_prove"}:
        raise ValueError("runtime descriptor is not closed")
    if value["schema"] != SCHEMA or value["does_not_prove"] != list(RUNTIME_LIMITS):
        raise ValueError("runtime descriptor schema or limitations drift")
    python = value["python"]
    if type(python) is not dict or set(python) != {
            "implementation", "version", "cache_tag", "abi_flags",
            "byteorder", "platform"}:
        raise ValueError("Python runtime identity is not closed")
    if (any(type(python[name]) is not str for name in python if name != "version")
            or type(python["version"]) is not list
            or len(python["version"]) != 3
            or any(type(part) is not int or part < 0 for part in python["version"])):
        raise ValueError("Python runtime identity is malformed")
    pytest_id = value["pytest"]
    if type(pytest_id) is not dict or set(pytest_id) != {
            "distribution", "version", "requires_dist", "source",
            "identity_sha256"}:
        raise ValueError("pytest dependency identity is not closed")
    requires = pytest_id["requires_dist"]
    if (pytest_id["distribution"] != "pytest" or not pytest_id["version"]
            or type(requires) is not list or requires != sorted(requires)
            or any(type(item) is not str for item in requires)):
        raise ValueError("pytest dependency identity is malformed")
    source = pytest_id["source"]
    if type(source) is not dict or set(source) != {
            "algorithm", "file_count", "bytes", "files", "manifest_sha256"}:
        raise ValueError("pytest source identity is not closed")
    files = source["files"]
    if (source["algorithm"] != "sha256-canonical-source-manifest/v1"
            or type(files) is not list or not files or len(files) > MAX_SOURCE_FILES
            or files != sorted(files, key=lambda item: item.get("path", ""))):
        raise ValueError("pytest source manifest is malformed")
    total = 0
    for item in files:
        if (type(item) is not dict or set(item) != {"path", "bytes", "sha256"}
                or type(item["path"]) is not str or not item["path"]
                or PurePosixPath(item["path"]).is_absolute()
                or ".." in PurePosixPath(item["path"]).parts
                or type(item["bytes"]) is not int or item["bytes"] < 0
                or item["bytes"] > MAX_SOURCE_FILE_BYTES or not _sha(item["sha256"])):
            raise ValueError("pytest source entry is malformed")
        total += item["bytes"]
    if (source["file_count"] != len(files) or source["bytes"] != total
            or total > MAX_SOURCE_BYTES
            or source["manifest_sha256"] != _digest(files)):
        raise ValueError("pytest source manifest digest or denominator drift")
    identity = {key: pytest_id[key] for key in (
        "distribution", "version", "requires_dist", "source")}
    if not _sha(pytest_id["identity_sha256"]) or pytest_id["identity_sha256"] != _digest(identity):
        raise ValueError("pytest runtime dependency identity digest drift")
    return value
