"""Filesystem isolation and receipt helpers for cross-harness execution."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
from typing import Any, Iterable


def _sha_bytes(data: bytes) -> str: return hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def canonical_sha256(value: Any) -> str: return _sha_bytes(_canonical(value))


def _resolved_key(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path.resolve(strict=True))))


def _inside(root: Path, candidate: Path) -> bool:
    try:
        return os.path.commonpath((_resolved_key(root), _resolved_key(candidate))) == _resolved_key(root)
    except ValueError:
        return False


def _resolve_from_existing_parent(path: Path) -> Path:
    cursor, tail = path.absolute(), []
    while not cursor.exists():
        parent = cursor.parent
        if parent == cursor:
            raise ValueError("artifact_root_parent_missing")
        tail.append(cursor.name)
        cursor = parent
    resolved = cursor.resolve(strict=True)
    for name in reversed(tail):
        resolved /= name
    return resolved


def preflight_artifact_root(source_root: Path, artifact_root: Path) -> Path:
    source = Path(source_root).resolve(strict=True)
    if not source.is_dir():
        raise ValueError("source_root_not_directory")
    requested = Path(artifact_root).absolute()
    proposed = _resolve_from_existing_parent(requested)
    try:
        source_key = _resolved_key(source)
        requested_key = os.path.normcase(os.path.normpath(str(requested)))
        proposed_key = os.path.normcase(os.path.normpath(str(proposed)))
        contained = (os.path.commonpath((source_key, requested_key)) == source_key
                     or os.path.commonpath((source_key, proposed_key)) == source_key)
    except ValueError:
        contained = False
    if contained:
        raise ValueError("artifact_root_inside_source")
    return proposed


def _readonly_attributes(info: os.stat_result) -> int:
    attributes = int(getattr(info, "st_file_attributes", 0))
    return attributes & int(getattr(stat, "FILE_ATTRIBUTE_READONLY", 1))


def snapshot_source_tree(root: Path) -> dict[str, Any]:
    base = Path(root).resolve(strict=True)
    files = []
    for current, directories, names in os.walk(base, followlinks=False):
        current_path = Path(current)
        directories[:] = sorted(name for name in directories if name != ".git")
        for name in list(directories):
            path = current_path / name
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                directories.remove(name); names.append(name)
        for name in sorted(names):
            path, info = current_path / name, (current_path / name).lstat()
            if stat.S_ISLNK(info.st_mode): data = os.readlink(path).encode("utf-8")
            elif stat.S_ISREG(info.st_mode): data = path.read_bytes()
            else: raise ValueError(f"source_tree_special_file: {path.relative_to(base).as_posix()}")
            files.append({"path": path.relative_to(base).as_posix(), "sha256": _sha_bytes(data),
                          "size": info.st_size, "mode": stat.S_IMODE(info.st_mode),
                          "read_only_attributes": _readonly_attributes(info)})
    files.sort(key=lambda row: row["path"])
    return {"schema": "harness.cross-harness-source-snapshot/v1", "files": files,
            "sha256": _sha_bytes(_canonical(files))}


def _safe_relative(value: str, label: str) -> Path:
    path = Path(value)
    if (not value or path.is_absolute() or path.drive or ".." in path.parts
            or value.startswith(("/", "\\")) or "\\" in value or ":" in value
            or any(part.endswith((".", " ")) or part.split(".", 1)[0].casefold() in _DEVICES
                   for part in path.parts)):
        raise ValueError(f"{label} invalid: {value}")
    return path


_STANDARD_NAMES = {"prompt.txt", "output.txt", "tool_trace.json", "receipt.json", "metrics.json",
                   "limitations.md", "enforcement.json", "availability.json", "provider-receipt.json",
                   "oracle.json", "resource.json"}
_DEVICES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
            *(f"lpt{i}" for i in range(1, 10))}


def _safe_artifact_name(value: str, label: str) -> str:
    validate_path_component(value, label)
    return value


def validate_path_component(value: str, label: str = "path component") -> str:
    path = _safe_relative(value, label)
    if len(path.parts) != 1 or "/" in value or "\\" in value:
        raise ValueError(f"{label} invalid: {value}")
    return value


def create_attempt_workspace(
    source_root: Path, required_inputs: list[str], expected_sha256s: dict[str, str], attempt_dir: Path,
) -> tuple[Path, dict[str, str]]:
    source, workspace = Path(source_root).resolve(strict=True), Path(attempt_dir) / "workspace"
    if workspace.exists():
        raise ValueError("attempt workspace already exists")
    workspace.mkdir(parents=True)
    workspace = workspace.resolve(strict=True)
    observed: dict[str, str] = {}
    for reference in required_inputs:
        relative = _safe_relative(reference, "required input")
        origin = (source / relative).resolve(strict=True)
        if not origin.is_file() or not _inside(source, origin):
            raise ValueError(f"required input outside source: {reference}")
        digest = _sha_file(origin)
        if expected_sha256s.get(reference) != digest:
            raise ValueError(f"required input hash mismatch: {reference}")
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin, target)
        if os.path.samefile(origin, target) or target.stat().st_nlink != 1:
            raise ValueError(f"required input copy is not independent: {reference}")
        target.chmod(stat.S_IREAD)
        observed[reference] = digest
    return workspace, observed


def _pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in rows:
        if key in result:
            raise ValueError(f"duplicate artifact name: {key}")
        result[key] = value
    return result


def _declared_names(names: list[str]) -> list[str]:
    if len(names) != len({name.casefold() for name in names}):
        raise ValueError("declared artifact names contain duplicates")
    for name in names:
        _safe_artifact_name(name, "declared artifact")
        if name.casefold() in _STANDARD_NAMES:
            raise ValueError("declared artifact conflicts with standard attempt filename")
    return names


def materialize_response_envelope(
    output_text: str, declared_names: list[str], attempt_dir: Path,
) -> tuple[Path, dict[str, Path]]:
    requested_root = Path(attempt_dir)
    if requested_root.is_symlink() or getattr(requested_root, "is_junction", lambda: False)():
        raise ValueError("artifact attempt root is a link")
    requested_root.mkdir(parents=True, exist_ok=True)
    root = requested_root.resolve(strict=True)
    raw = root / "output.txt"
    raw.write_text(output_text, encoding="utf-8", newline="")
    names = _declared_names(declared_names)
    try:
        envelope = json.loads(output_text, object_pairs_hook=_pairs)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"artifact envelope malformed: {exc}") from exc
    if not isinstance(envelope, dict) or set(envelope) != {"artifacts"} or not isinstance(envelope["artifacts"], dict):
        raise ValueError("artifact envelope must contain only an artifacts object")
    artifacts = envelope["artifacts"]
    for name in artifacts:
        _safe_artifact_name(name, "artifact name")
    if set(artifacts) != set(names):
        raise ValueError("artifact set does not match declared artifacts")
    paths: dict[str, Path] = {}
    for name in names:
        value, path = artifacts[name], root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if name.endswith(".md"):
            if not isinstance(value, str):
                raise ValueError(f"artifact value must be markdown string: {name}")
            path.write_text(value, encoding="utf-8", newline="")
        else:
            if not isinstance(value, dict):
                raise ValueError(f"artifact value must be JSON object: {name}")
            path.write_bytes(_canonical(value) + b"\n")
        paths[name] = path
    return raw, paths


_SUBJECT_FIELDS = ("attempt_key", "run_id", "phase", "provider_role", "harness_id", "adapter_id",
                   "model_id", "task_set_id", "task_id", "repetition", "execution_state",
                   "raw_prompt_sha256", "raw_output_sha256", "tool_policy_sha256", "enforcement_sha256",
                   "source_snapshot_sha256", "workspace_snapshot_sha256", "cache_state", "input_sha256s",
                   "comparison_key", "randomness_control", "model_observed", "enforcement_description",
                   "enforcement_verification_state", "policy_equivalence", "availability_evidence",
                   "observed_capabilities", "policy_violations", "source_commit")


def _receipt_subject(row: dict[str, Any], artifacts: list[dict[str, str]]) -> dict[str, Any]:
    return {"schema": "harness.cross-harness-receipt-subject/v1",
            "executor_facts": {field: row.get(field) for field in _SUBJECT_FIELDS}, "artifacts": artifacts}


def bind_attempt_receipt(row: dict[str, Any], artifact_paths: dict[str, Path], receipt_path: Path) -> dict[str, Any]:
    receipt_path = Path(receipt_path)
    root = receipt_path.parent.resolve()
    artifacts = []
    for name, path in sorted(artifact_paths.items()):
        resolved = Path(path).resolve(strict=True)
        if not _inside(root, resolved):
            raise ValueError(f"receipt artifact outside attempt: {name}")
        artifacts.append({"name": name, "path": resolved.relative_to(root).as_posix(), "sha256": _sha_file(resolved)})
    subject = _receipt_subject(row, artifacts)
    receipt = {"schema": "harness.cross-harness-attempt-receipt/v1", "receipt_subject": subject,
               "receipt_subject_sha256": canonical_sha256(subject),
               "does_not_bind": ["oracle_result", "receipt_recheck_state", "primary_outcome", "final_status"]}
    receipt_path.write_bytes(_canonical(receipt) + b"\n")
    return receipt


def recheck_attempt_receipt(receipt_path: Path, row: dict[str, Any]) -> str:
    try:
        receipt_path = Path(receipt_path).resolve(strict=True)
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"), object_pairs_hook=_pairs)
        if receipt.get("schema") != "harness.cross-harness-attempt-receipt/v1": return "drift"
        subject = receipt.get("receipt_subject")
        if not isinstance(subject, dict) or receipt.get("receipt_subject_sha256") != canonical_sha256(subject): return "drift"
        artifacts = subject.get("artifacts", [])
        current = []
        for item in artifacts:
            path = (receipt_path.parent / _safe_relative(str(item["path"]), "receipt artifact")).resolve(strict=True)
            if not _inside(receipt_path.parent, path): return "drift"
            current.append({"name": item["name"], "path": item["path"], "sha256": _sha_file(path)})
        if _receipt_subject(row, current) != subject: return "drift"
        return "verified"
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return "drift"


def write_artifact_index(run_root: Path, referenced_paths: Iterable[Path]) -> Path:
    root = Path(run_root).resolve(strict=True)
    index_path = root / "artifact-index.json"
    unique: dict[str, Path] = {}
    for path in referenced_paths:
        if Path(path).is_symlink() or getattr(Path(path), "is_junction", lambda: False)():
            raise ValueError("indexed artifact is a link")
        resolved = Path(path).resolve(strict=True)
        if resolved == index_path.resolve(strict=False): continue
        if not _inside(root, resolved) or not resolved.is_file(): raise ValueError("indexed artifact outside run root")
        unique[resolved.relative_to(root).as_posix()] = resolved
    payload = {"schema": "harness.cross-harness-artifact-index/v1",
               "artifacts": [{"path": name, "sha256": _sha_file(path)} for name, path in sorted(unique.items())],
               "self_hash": None, "self_hash_reason": "artifact index cannot contain its own hash"}
    index_path.write_bytes(_canonical(payload) + b"\n")
    return index_path
