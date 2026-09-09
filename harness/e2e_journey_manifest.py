"""Versioned product E2E journey manifests.

The manifest layer describes a product workflow and the operator-owned fixture
files it may read. Execution stays in :mod:`harness.e2e_runner`; this module is
only schema, validation, and path containment.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any

from harness.cross_harness_artifacts import validate_path_component

MANIFEST_SCHEMA = "flywheel.product-e2e-journey/v1"
RUN_SCHEMA = "flywheel.product-e2e-run/v1"

IMPLEMENTED_RUNTIME_KINDS = frozenset({"cli_process", "mcp_stdio"})
FUTURE_RUNTIME_KINDS = frozenset({
    "mcp_http", "authenticated_http", "browser", "native", "device"
})
KNOWN_RUNTIME_KINDS = IMPLEMENTED_RUNTIME_KINDS | FUTURE_RUNTIME_KINDS

_DEVICES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
            *(f"lpt{i}" for i in range(1, 10))}


@dataclass(frozen=True)
class RuntimeSpec:
    kind: str
    executable_env: str
    expected_distribution: str
    expected_version_prefix: str
    expected_wheel_sha256: str = ""
    expected_executable_sha256: str = ""
    forbid_pythonpath: bool = True
    forbid_editable: bool = True


@dataclass(frozen=True)
class JourneyManifest:
    schema: str
    journey_id: str
    product: str
    product_version: str
    platforms: tuple[str, ...]
    runtime: RuntimeSpec
    allowed_resource_paths: tuple[str, ...]
    fixtures: dict[str, str]
    oracle: dict[str, Any]
    controls: tuple[str, ...]
    path: Path
    repo_root: Path
    _fixture_paths: dict[str, Path]

    def fixture_path(self, name: str) -> Path:
        try:
            return self._fixture_paths[name]
        except KeyError as exc:
            raise KeyError(f"unknown fixture: {name}") from exc

    def fixture_relative(self, name: str) -> str:
        try:
            return self.fixtures[name]
        except KeyError as exc:
            raise KeyError(f"unknown fixture: {name}") from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "journey_id": self.journey_id,
            "product": self.product,
            "product_version": self.product_version,
            "platforms": list(self.platforms),
            "runtime": {
                "kind": self.runtime.kind,
                "executable_env": self.runtime.executable_env,
                "expected_distribution": self.runtime.expected_distribution,
                "expected_version_prefix": self.runtime.expected_version_prefix,
                "expected_wheel_sha256": self.runtime.expected_wheel_sha256,
                "expected_executable_sha256": self.runtime.expected_executable_sha256,
                "forbid_pythonpath": self.runtime.forbid_pythonpath,
                "forbid_editable": self.runtime.forbid_editable,
            },
            "allowed_resource_paths": list(self.allowed_resource_paths),
            "fixtures": dict(self.fixtures),
            "oracle": self.oracle,
            "controls": list(self.controls),
        }


@dataclass(frozen=True)
class ValidationIssue:
    field: str
    message: str


def _inside(root: Path, candidate: Path) -> bool:
    try:
        root_key = os.path.normcase(os.path.normpath(str(root.resolve(strict=True))))
        candidate_key = os.path.normcase(os.path.normpath(str(candidate.resolve(strict=True))))
        return os.path.commonpath((root_key, candidate_key)) == root_key
    except (OSError, ValueError):
        return False


def _safe_relative(value: str, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty relative path")
    if "\\" in value or ":" in value:
        raise ValueError(f"{label} invalid: {value}")
    path = Path(value)
    parts = path.parts
    if path.is_absolute() or path.drive or ".." in parts or value.startswith(("/", "\\")):
        raise ValueError(f"{label} invalid: {value}")
    for part in parts:
        stem = part.split(".", 1)[0].casefold()
        if not part or part.endswith((".", " ")) or stem in _DEVICES:
            raise ValueError(f"{label} invalid: {value}")
    return path


def _resolve_existing(repo_root: Path, relative: str, label: str) -> Path:
    rel = _safe_relative(relative, label)
    resolved = (repo_root / rel).resolve(strict=True)
    if not _inside(repo_root, resolved):
        raise ValueError(f"{label} outside source root: {relative}")
    return resolved


def _resolve_allowed_roots(repo_root: Path, paths: list[Any]) -> list[Path]:
    if not paths:
        raise ValueError("allowed_resource_paths must not be empty")
    out = []
    for index, item in enumerate(paths):
        if not isinstance(item, str):
            raise ValueError(f"allowed_resource_paths[{index}] must be a string")
        out.append(_resolve_existing(repo_root, item, "allowed resource path"))
    return out


def _runtime_from(raw: Any) -> RuntimeSpec:
    if not isinstance(raw, dict):
        raise ValueError("runtime must be an object")
    kind = raw.get("kind")
    if kind not in KNOWN_RUNTIME_KINDS:
        raise ValueError(f"unsupported runtime kind: {kind!r}")
    executable_env = raw.get("executable_env", "")
    expected_distribution = raw.get("expected_distribution", "")
    expected_version_prefix = raw.get("expected_version_prefix", "")
    if not all(isinstance(value, str) and value for value in (
        executable_env, expected_distribution, expected_version_prefix,
    )):
        raise ValueError("runtime executable_env, expected_distribution, and expected_version_prefix are required")
    return RuntimeSpec(
        kind=kind,
        executable_env=executable_env,
        expected_distribution=expected_distribution,
        expected_version_prefix=expected_version_prefix,
        expected_wheel_sha256=str(raw.get("expected_wheel_sha256", "") or ""),
        expected_executable_sha256=str(raw.get("expected_executable_sha256", "") or ""),
        forbid_pythonpath=bool(raw.get("forbid_pythonpath", True)),
        forbid_editable=bool(raw.get("forbid_editable", True)),
    )


def validate_journey_manifest(manifest: JourneyManifest) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if manifest.runtime.kind in FUTURE_RUNTIME_KINDS:
        issues.append(ValidationIssue("runtime.kind", "runtime vocabulary is known but no adapter is implemented"))
    return issues


def load_journey_manifest(path: str | Path, *, repo_root: str | Path | None = None) -> JourneyManifest:
    manifest_path = Path(path).resolve(strict=True)
    root = Path(repo_root).resolve(strict=True) if repo_root is not None else Path.cwd().resolve(strict=True)
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifest json malformed: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("manifest must be a JSON object")
    if raw.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"unsupported journey schema: {raw.get('schema')!r}")

    journey_id = raw.get("journey_id")
    if not isinstance(journey_id, str) or not journey_id:
        raise ValueError("journey_id must be a non-empty string")
    validate_path_component(journey_id, "journey_id")

    product = raw.get("product")
    if product != "gather":
        raise ValueError(f"unsupported product: {product!r}")
    product_version = raw.get("product_version")
    if not isinstance(product_version, str) or not product_version:
        raise ValueError("product_version must be a non-empty string")

    platforms = raw.get("platforms", [])
    if platforms is None:
        platforms = []
    if not isinstance(platforms, list) or not all(isinstance(item, str) for item in platforms):
        raise ValueError("platforms must be a list of strings")

    allowed = raw.get("allowed_resource_paths", [])
    allowed_roots = _resolve_allowed_roots(root, allowed)

    fixtures = raw.get("fixtures")
    if not isinstance(fixtures, dict) or "source_text" not in fixtures:
        raise ValueError("fixtures.source_text is required")
    fixture_strings: dict[str, str] = {}
    fixture_paths: dict[str, Path] = {}
    for name, relative in fixtures.items():
        if not isinstance(name, str) or not isinstance(relative, str):
            raise ValueError("fixture names and paths must be strings")
        resolved = _resolve_existing(root, relative, f"fixture {name}")
        if not any(_inside(allowed_root, resolved) for allowed_root in allowed_roots):
            raise ValueError(f"fixture {name} outside allowed_resource_paths: {relative}")
        fixture_strings[name] = relative
        fixture_paths[name] = resolved

    oracle = raw.get("oracle")
    if not isinstance(oracle, dict) or oracle.get("kind") != "gather_context_selection/v1":
        raise ValueError("oracle.kind must be gather_context_selection/v1")
    for field in ("include_text", "exclude_text", "start_marker", "end_marker"):
        if not isinstance(oracle.get(field), str) or not oracle[field]:
            raise ValueError(f"oracle.{field} must be a non-empty string")

    controls = raw.get("controls", [])
    if controls is None:
        controls = []
    if not isinstance(controls, list) or not all(isinstance(item, str) for item in controls):
        raise ValueError("controls must be a list of strings")

    return JourneyManifest(
        schema=MANIFEST_SCHEMA,
        journey_id=journey_id,
        product=product,
        product_version=product_version,
        platforms=tuple(platforms),
        runtime=_runtime_from(raw.get("runtime")),
        allowed_resource_paths=tuple(str(item) for item in allowed),
        fixtures=fixture_strings,
        oracle=dict(oracle),
        controls=tuple(controls),
        path=manifest_path,
        repo_root=root,
        _fixture_paths=fixture_paths,
    )
