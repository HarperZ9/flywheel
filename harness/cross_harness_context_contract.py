"""Bounded artifact contract checks for the context-recovery task."""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Any

from harness.cross_harness_oracle_support import _Malformed, _digest, _read, _rows, _sha, _strings


_ENTRY_TYPES = {"directory", "file"}
_FILE_ATTRIBUTE_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
CONTEXT_RECOVERY_FIXTURE_SCHEMA = "harness.cross_harness_fixture.context_recovery_state.v1"
_OBJECT_KEYS = {
    "recovered_context": {"preview_ref", "preview_sha256", "source_state_sha256", "event_head_sha256", "selected_files"},
    "next_action": {"action_id", "kind", "selected_files", "basis_refs", "description"},
}
_ROW_KEYS = {
    "workspace_state": {"path", "role", "sha256"},
    "source_drift_decisions": {"case_id", "decision", "error_code", "effect_count"},
    "duplicate_resolutions": {"case_id", "decision", "new_effect_count", "journey_count"},
}


def validate_fixture_schema(fixture: dict[str, Any]) -> None:
    if fixture.get("schema") != CONTEXT_RECOVERY_FIXTURE_SCHEMA:
        raise _Malformed("fixture_schema_invalid")


def _relative(value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise _Malformed(f"{field}_invalid")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise _Malformed(f"{field}_invalid")
    return path


def _inside_dir(root: Path, value: Any, field: str) -> Path:
    relative = _relative(value, field)
    if _has_reparse(root, relative):
        raise _Malformed(f"{field}_invalid")
    try:
        path = (root / relative).resolve()
    except (OSError, RuntimeError) as exc:
        raise _Malformed(f"{field}_invalid") from exc
    if not path.is_relative_to(root.resolve()) or not path.is_dir():
        raise _Malformed(f"{field}_invalid")
    return path


def _is_reparse(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        attrs = getattr(path.lstat(), "st_file_attributes", 0)
        return bool(attrs & _FILE_ATTRIBUTE_REPARSE_POINT)
    except OSError:
        return True


def _has_reparse(root: Path, relative: Path) -> bool:
    current = root.resolve()
    for part in relative.parts:
        current = current / part
        if _is_reparse(current):
            return True
    return False


def _actual_inventory(root: Path, directory: Path) -> tuple[dict[str, str], bool]:
    actual: dict[str, str] = {}
    safe = True
    stack = [directory]
    while stack:
        current = stack.pop()
        try:
            children = sorted(current.iterdir(), key=lambda item: item.name)
        except OSError:
            return actual, False
        for child in children:
            rel = child.relative_to(root).as_posix()
            if _is_reparse(child):
                actual[rel] = "reparse"
                safe = False
            elif child.is_dir():
                actual[rel] = "directory"
                stack.append(child)
            elif child.is_file():
                actual[rel] = "file"
            else:
                actual[rel] = "other"
                safe = False
    return actual, safe


def _inventory_config(fixture: dict[str, Any]) -> tuple[Path, dict[str, dict[str, Any]], set[str]]:
    config = fixture.get("workspace_inventory")
    if not isinstance(config, dict):
        raise _Malformed("fixture_workspace_inventory_invalid")
    inventory_root = _relative(config.get("root"), "fixture_workspace_inventory_root")
    entries = _rows(config.get("entries"), "fixture_workspace_inventory_entries")
    allowed = set(_strings(config.get("allowed_write_paths", []), "fixture_workspace_inventory_allowed_writes"))
    expected: dict[str, dict[str, Any]] = {}
    for rel in allowed:
        _relative(rel, "fixture_workspace_inventory_allowed_write")
    for row in entries:
        rel = row.get("path")
        entry_type = row.get("type")
        if entry_type not in _ENTRY_TYPES:
            raise _Malformed("fixture_workspace_inventory_type_invalid")
        relative = _relative(rel, "fixture_workspace_inventory_path").as_posix()
        if relative in expected or relative in allowed:
            raise _Malformed("fixture_workspace_inventory_path_invalid")
        if not Path(relative).is_relative_to(inventory_root):
            raise _Malformed("fixture_workspace_inventory_path_invalid")
        if entry_type == "file":
            _digest(row.get("sha256"), f"fixture_workspace_inventory_sha256:{relative}")
        expected[relative] = row
    if not expected:
        raise _Malformed("fixture_workspace_inventory_empty")
    return inventory_root, expected, allowed


def workspace_inventory_codes(root: Path, fixture: dict[str, Any], checked: dict[str, Any]) -> tuple[list[str], bool]:
    inventory_root, expected, allowed = _inventory_config(fixture)
    directory = _inside_dir(root, inventory_root.as_posix(), "fixture_workspace_inventory_root")
    codes: list[str] = []
    for rel in _strings(fixture.get("forbidden_workspace_paths", []), "fixture_forbidden_workspace_paths"):
        relative = _relative(rel, "fixture_forbidden_workspace_path")
        try:
            forbidden = (root / relative).resolve()
        except (OSError, RuntimeError):
            continue
        if forbidden.is_relative_to(root) and forbidden.exists():
            codes.append("unexpected_workspace_effect")
    actual, safe = _actual_inventory(root, directory)
    actual = {rel: entry_type for rel, entry_type in actual.items() if rel not in allowed}
    expected_types = {path: str(row.get("type")) for path, row in expected.items()}
    if actual != expected_types:
        codes.append("unexpected_workspace_effect")
        codes.append("workspace_inventory_mismatch")
        journey = fixture.get("journey_state")
        journey_path = journey.get("path") if isinstance(journey, dict) else None
        if isinstance(journey_path, str) and actual.get(journey_path) != "file":
            codes.append("journey_state_mismatch")
    if not safe:
        return codes, False
    for rel, row in expected.items():
        if row.get("type") != "file":
            continue
        path = root / rel
        try:
            resolved = path.resolve()
        except (OSError, RuntimeError):
            codes.append("workspace_inventory_mismatch")
            return codes, False
        if _has_reparse(root, Path(rel)) or not resolved.is_relative_to(root.resolve()) or not path.is_file():
            codes.append("workspace_inventory_mismatch")
            return codes, False
        try:
            data = _read(checked, f"workspace_inventory:{rel}", resolved)
        except OSError:
            codes.append("workspace_inventory_mismatch")
            continue
        if _sha(data) != row.get("sha256"):
            codes.append("workspace_inventory_mismatch")
    return codes, True


def _project_markdown(report: dict[str, Any]) -> str | None:
    task_id = report.get("task_id")
    recovered = report.get("recovered_context")
    if not isinstance(task_id, str) or not isinstance(recovered, dict):
        return None
    if not isinstance(recovered.get("preview_ref"), str):
        return None
    return f"# {task_id}\nSource context selected.\n"


def _schema_codes(report: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    for field, keys in _OBJECT_KEYS.items():
        value = report.get(field)
        if not isinstance(value, dict) or set(value) != keys:
            codes.append("report_schema_mismatch")
    for field, keys in _ROW_KEYS.items():
        rows = report.get(field)
        if not isinstance(rows, list):
            codes.append("report_schema_mismatch")
            continue
        for row in rows:
            if not isinstance(row, dict) or set(row) != keys:
                codes.append("report_schema_mismatch")
    for field in ("preserved_files", "forbidden_effects"):
        value = report.get(field)
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            codes.append("report_schema_mismatch")
    if not isinstance(report.get("native_provenance_state"), str):
        codes.append("report_schema_mismatch")
    return codes


def report_contract_codes(report: dict[str, Any], texts: dict[str, str], fixture: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    accepted_fields = set(_strings(fixture.get("accepted_report_fields"), "fixture_accepted_report_fields"))
    if set(report) != accepted_fields:
        codes.append("report_schema_mismatch")
    codes.extend(_schema_codes(report))
    if "recovery_contract" in report and report.get("recovery_contract") != fixture.get("recovery_contract"):
        codes.append("recovery_contract_mismatch")
    canonical = _project_markdown(report)
    if canonical is None:
        codes.append("canonical_markdown_mismatch")
        return codes
    markdown = next((text for name, text in texts.items() if name.endswith(".md")), None)
    if markdown != canonical:
        codes.append("canonical_markdown_mismatch")
    return codes
