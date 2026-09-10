"""Admission gate for components carried inside the frozen gateway payload."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tomllib
from typing import Callable, Mapping

from .bundled_lane_expectations import expected_bundled_lane
from .evidence_json import canonical_sha256, strict_load_json
from .mcp_client import LaunchSpec

SCHEMA = "flywheel.bundled-lane-component/v1"
SOURCE_ALGORITHM = "sha256-canonical-source-manifest/v1"
ADMITTED_BUNDLED_RELAY_TOOLS = ("relay.status",)
DOES_NOT_PROVE = (
    "NOT_PROVES_REPLACEMENT_OF_TRUSTED_EXECUTABLE: the descriptor binds the "
    "reviewed Relay source included in this build, not a later replacement of "
    "the whole gateway executable.",
    "NOT_PROVES_AGENTIC_TASK_SUCCESS: relay.status is an identity and "
    "transport check, not proof that Relay can complete model-backed work.",
    "NOT_PROVES_PROVIDER_OR_NETWORK_READINESS: the status check is "
    "network-free and carries no provider credential custody.",
)


@dataclass(frozen=True)
class BundledLaneAdmission:
    launch: LaunchSpec | None
    component: dict | None
    blocking_codes: tuple[str, ...]


def bundled_child_environment(
        environ: Mapping[str, str], *, platform: str = os.name) -> dict[str, str]:
    """Return the small environment passed to a bundled lane child."""
    if platform == "nt":
        retained = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "SYSTEMDRIVE",
                    "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA"}
        env = {key: str(value) for key, value in environ.items()
               if key.upper() in retained}
        root = env.get("SYSTEMROOT") or env.get("WINDIR") or "C:/Windows"
        env["PATH"] = str(Path(root) / "System32").replace("\\", "/")
        return env
    retained = {"LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TEMP", "TMP"}
    env = {key: str(value) for key, value in environ.items() if key in retained}
    env["PATH"] = os.defpath
    return env


def default_descriptor_path() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / "packaging" / "bundled-lanes" / "relay.json"


def admit_bundled_lane(
    name: str,
    *,
    executable: str,
    environ: Mapping[str, str],
    descriptor_path: str | Path | None = None,
    importable_fn: Callable[[str], bool] | None = None,
    expected: Mapping[str, object] | None = None,
) -> BundledLaneAdmission:
    """Admit one frozen bundled lane only when descriptor and module agree."""
    if name != "relay":
        return BundledLaneAdmission(None, None, ("bundled_lane_not_supported",))
    expected_row = {**expected_bundled_lane(name), **dict(expected or {})}
    path = Path(descriptor_path) if descriptor_path is not None else default_descriptor_path()
    descriptor, load_codes = _load_descriptor(path)
    if descriptor is None:
        return BundledLaneAdmission(None, None, load_codes)
    codes = list(load_codes)
    codes.extend(_validate_descriptor(descriptor, expected_row))
    module_name = str(expected_row.get("module", ""))
    if not module_name:
        codes.append("bundled_entrypoint_invalid")
    elif not (importable_fn or _module_importable)(module_name):
        codes.append("bundled_module_missing")
    codes = list(dict.fromkeys(codes))
    if codes:
        return BundledLaneAdmission(None, None, tuple(codes))
    component = _component_summary(descriptor, expected_row)
    launch = LaunchSpec(
        (executable, "--bundled-lane-mcp", name),
        env_overrides=tuple(sorted(bundled_child_environment(environ).items())),
        inherit_env=False,
        hide_window=True,
        allowed_tools=tuple(expected_row["allowed_tools"]),
    )
    return BundledLaneAdmission(launch, component, ())


def dispatch_bundled_lane_mcp(
    argv: list[str] | tuple[str, ...] | None = None,
    *,
    import_module_fn: Callable[[str], object] = importlib.import_module,
    executable: str | None = None,
    environ: Mapping[str, str] | None = None,
    descriptor_path: str | Path | None = None,
    expected: Mapping[str, object] | None = None,
) -> int | None:
    """Serve an exact bundled lane child mode, or return None for normal gateway."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] != "--bundled-lane-mcp":
        return None
    if args != ["--bundled-lane-mcp", "relay"]:
        return 2
    expected_row = {**expected_bundled_lane("relay"), **dict(expected or {})}
    admission = admit_bundled_lane(
        "relay",
        executable=executable or sys.executable,
        environ=environ or os.environ,
        descriptor_path=descriptor_path,
        expected=expected_row,
    )
    if admission.blocking_codes:
        return 2
    module = import_module_fn(str(expected_row["module"]))
    serve = getattr(module, str(expected_row["callable"]), None)
    if not callable(serve):
        return 2
    result = serve()
    return int(result or 0)


def build_relay_descriptor(source_root: Path, *, commit: str) -> dict:
    """Build the canonical descriptor for the Relay source tree at ``source_root``."""
    source_root = source_root.resolve()
    version = _pyproject_version(source_root / "pyproject.toml")
    files = source_manifest(source_root / "src" / "relay", relative_to=source_root)
    source = {
        "repo": "https://github.com/HarperZ9/relay",
        "commit": commit,
        "path": "src/relay",
        "algorithm": SOURCE_ALGORITHM,
        "file_count": len(files),
        "bytes": sum(int(row["bytes"]) for row in files),
        "files": files,
        "manifest_sha256": "sha256:" + canonical_sha256(files),
    }
    return {
        "schema": SCHEMA,
        "name": "relay",
        "version": version,
        "source": source,
        "entrypoint": {
            "argv": ["--bundled-lane-mcp", "relay"],
            "module": "relay.local_mcp",
            "callable": "serve",
            "health_tool": "relay.status",
        },
        "allowed_tools": list(ADMITTED_BUNDLED_RELAY_TOOLS),
        "does_not_prove": list(DOES_NOT_PROVE),
    }


def source_manifest(root: Path, *, relative_to: Path) -> list[dict[str, object]]:
    root = root.resolve()
    base = relative_to.resolve()
    rows: list[dict[str, object]] = []
    for path in sorted(root.rglob("*.py")):
        if not path.is_file():
            continue
        data = path.read_bytes()
        rows.append({
            "path": path.relative_to(base).as_posix(),
            "bytes": len(data),
            "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
        })
    return rows


def descriptor_digest(descriptor: Mapping[str, object]) -> str:
    return "sha256:" + canonical_sha256(dict(descriptor))


def canonical_descriptor_text(descriptor: Mapping[str, object]) -> str:
    return json.dumps(
        dict(descriptor), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _load_descriptor(path: Path) -> tuple[dict | None, tuple[str, ...]]:
    try:
        return strict_load_json(path.read_bytes(), max_bytes=4_000_000,
                                max_depth=48), ()
    except FileNotFoundError:
        return None, ("bundled_descriptor_missing",)
    except (OSError, TypeError, ValueError):
        return None, ("bundled_descriptor_invalid",)


def _validate_descriptor(
        descriptor: Mapping[str, object], expected: Mapping[str, object]) -> tuple[str, ...]:
    codes: list[str] = []
    source = descriptor.get("source")
    entrypoint = descriptor.get("entrypoint")
    if (descriptor.get("schema") != SCHEMA
            or descriptor.get("name") != expected.get("name", "relay")
            or not isinstance(source, dict)
            or not isinstance(entrypoint, dict)):
        return ("bundled_descriptor_shape_invalid",)
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
    files = source.get("files")
    if (not isinstance(files, list)
            or any(not _manifest_file_row(row) for row in files)
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
    if entrypoint.get("argv") != ["--bundled-lane-mcp", "relay"]:
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


def _component_summary(
        descriptor: Mapping[str, object], expected: Mapping[str, object]) -> dict:
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


def _manifest_file_row(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        set(value) == {"path", "bytes", "sha256"}
        and isinstance(value.get("path"), str)
        and value["path"].startswith("src/relay/")
        and value["path"].endswith(".py")
        and isinstance(value.get("bytes"), int)
        and value["bytes"] >= 0
        and isinstance(value.get("sha256"), str)
        and len(value["sha256"]) == 71
        and value["sha256"].startswith("sha256:")
    )


def _module_importable(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False

def _pyproject_version(path: Path) -> str:
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError("Relay pyproject version is unreadable") from exc
    version = value.get("project", {}).get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("Relay pyproject version is missing")
    return version
