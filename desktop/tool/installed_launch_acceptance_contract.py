"""Receipt contract and build-binding checks for installed-launch acceptance."""
from __future__ import annotations

import json
import re
from collections.abc import Mapping as MappingABC
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

BUILD_MANIFEST_SCHEMA = "flywheel.installed-build-manifest/v1"
BUILD_MANIFEST_TRUST_BOUNDARY = (
    "operator-supplied integrity binding; not external attestation"
)

ASSERTION_IDS = (
    "H01_app_exe_exists",
    "H02_engine_exe_exists_under_install_root",
    "H03_installer_payload_files_when_expected",
    "H04_start_menu_shortcut_targets_app_exe",
    "H05_desktop_shortcut_optional_or_targets_app_exe",
    "H06_uninstall_registry_appid_singleton_or_access_denied",
    "H07_protocol_registration_supported_or_explicit_unsupported",
    "H08_port_precheck_refuses_foreign_gateway",
    "H09_installed_engine_owned_start",
    "H10_desktop_status_schema_required",
    "H11_token_used_but_redacted",
    "H12_owned_process_cleanup_no_survivors",
    "H13_hidden_gateway_visible_window_count_when_observer_available",
    "H14_journey_read_only_availability_or_typed_unavailable",
    "H15_offline_to_ready_status_transition",
    "H16_restart_same_isolated_profile",
    "H17_upgrade_before_after_snapshot_compare",
    "H18_known_unavailable_lanes_not_live",
    "H19_standalone_cli_separated_from_installed_engine",
    "H20_receipt_fresh_complete_and_source_bound",
)

PHASE_ASSERTIONS = {
    "P0_payload_manifest_preflight": (
        "H01_app_exe_exists",
        "H02_engine_exe_exists_under_install_root",
        "H03_installer_payload_files_when_expected",
        "H20_receipt_fresh_complete_and_source_bound",
    ),
    "P1_shortcut_registry_targets": (
        "H04_start_menu_shortcut_targets_app_exe",
        "H05_desktop_shortcut_optional_or_targets_app_exe",
        "H06_uninstall_registry_appid_singleton_or_access_denied",
        "H07_protocol_registration_supported_or_explicit_unsupported",
    ),
    "P2_owned_gateway_start_status_cleanup": (
        "H08_port_precheck_refuses_foreign_gateway",
        "H09_installed_engine_owned_start",
        "H10_desktop_status_schema_required",
        "H11_token_used_but_redacted",
        "H12_owned_process_cleanup_no_survivors",
        "H13_hidden_gateway_visible_window_count_when_observer_available",
    ),
    "P3_journey_offline_to_ready_observable": (
        "H14_journey_read_only_availability_or_typed_unavailable",
        "H15_offline_to_ready_status_transition",
    ),
    "P4_restart_and_recovery_snapshot": ("H16_restart_same_isolated_profile",),
    "P5_upgrade_snapshot_compare": ("H17_upgrade_before_after_snapshot_compare",),
    "P6_explicit_unavailable_lanes": (
        "H18_known_unavailable_lanes_not_live",
        "H19_standalone_cli_separated_from_installed_engine",
    ),
}
PHASE_IDS = tuple(PHASE_ASSERTIONS)
VALID_MODES = {"preflight", "metadata", "engine", "full"}
MODE_REQUIRED_ASSERTIONS = {
    "preflight": {
        "H01_app_exe_exists", "H02_engine_exe_exists_under_install_root",
        "H20_receipt_fresh_complete_and_source_bound",
    },
    "metadata": {
        "H01_app_exe_exists", "H02_engine_exe_exists_under_install_root",
        "H04_start_menu_shortcut_targets_app_exe",
        "H06_uninstall_registry_appid_singleton_or_access_denied",
        "H20_receipt_fresh_complete_and_source_bound",
    },
    "engine": {
        "H01_app_exe_exists", "H02_engine_exe_exists_under_install_root",
        "H08_port_precheck_refuses_foreign_gateway",
        "H09_installed_engine_owned_start",
        "H10_desktop_status_schema_required", "H11_token_used_but_redacted",
        "H12_owned_process_cleanup_no_survivors",
        "H15_offline_to_ready_status_transition",
        "H20_receipt_fresh_complete_and_source_bound",
    },
    "full": {
        "H01_app_exe_exists", "H02_engine_exe_exists_under_install_root",
        "H04_start_menu_shortcut_targets_app_exe",
        "H06_uninstall_registry_appid_singleton_or_access_denied",
        "H08_port_precheck_refuses_foreign_gateway",
        "H09_installed_engine_owned_start",
        "H10_desktop_status_schema_required", "H11_token_used_but_redacted",
        "H12_owned_process_cleanup_no_survivors",
        "H14_journey_read_only_availability_or_typed_unavailable",
        "H15_offline_to_ready_status_transition",
        "H16_restart_same_isolated_profile",
        "H20_receipt_fresh_complete_and_source_bound",
    },
}
VALID_ASSERTION_STATES = {
    "PASS", "FAIL", "NOT_CHECKED", "UNTESTED", "UNSUPPORTED", "SKIP",
    "ACCESS_DENIED", "UNAVAILABLE", "READY_EMPTY", "UPGRADE_NOT_CHECKED",
    "PORT_OCCUPIED_PRECHECK", "AUTH_TOKEN_UNAVAILABLE",
    "STATUS_CONTRACT_MISSING", "STATUS_SCHEMA_INVALID",
    "STATUS_VERSION_MISMATCH", "JOURNEY_SCHEMA_INVALID",
}

def phase_results() -> list[dict[str, Any]]:
    return [{"id": pid, "state": "RECORDED", "assertion_ids": list(aids)}
            for pid, aids in PHASE_ASSERTIONS.items()]

def assertion_is_satisfied(assertion_id: str, state: str) -> bool:
    if assertion_id == "H14_journey_read_only_availability_or_typed_unavailable":
        return state in {"PASS", "READY_EMPTY"}
    return state == "PASS"

def completion_from_rows(rows: list[Mapping[str, Any]]) -> bool:
    return all(
        row.get("severity") != "critical" or
        assertion_is_satisfied(str(row.get("id", "")), str(row.get("state", "")))
        for row in rows
    )

def validate_receipt_semantics(receipt: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    mode = str(receipt.get("mode", "preflight"))
    if mode not in VALID_MODES:
        errors.append("receipt mode is unknown")
    assertions = receipt.get("assertions")
    phases = receipt.get("phase_results")
    if not isinstance(assertions, list) or not isinstance(phases, list):
        return ["receipt assertions or phases are not arrays"]
    _check_exact_ids(errors, assertions, ASSERTION_IDS, "assertion")
    _check_exact_ids(errors, phases, PHASE_IDS, "phase")
    by_id = {row.get("id"): row for row in assertions
             if isinstance(row, MappingABC) and isinstance(row.get("id"), str)}
    for index, row in enumerate(assertions):
        if not isinstance(row, MappingABC):
            errors.append(f"assertion row {index} is not an object")
            continue
        row_id = row.get("id")
        if not isinstance(row_id, str):
            errors.append(f"assertion row {index} id is not a string")
            continue
        state = row.get("state")
        if state not in VALID_ASSERTION_STATES:
            errors.append(f"assertion {row_id} has unknown state {state}")
        if row.get("severity") not in {"critical", "info"}:
            errors.append(f"assertion {row_id} has invalid severity")
        if receipt.get("complete") is True and row.get("severity") == "critical":
            if not assertion_is_satisfied(row_id, str(state)):
                errors.append(f"required assertion {row_id} is {state}")
    if receipt.get("complete") is True:
        for aid in sorted(MODE_REQUIRED_ASSERTIONS.get(mode, ())):
            row = by_id.get(aid, {})
            if row.get("severity") != "critical":
                errors.append(f"mode {mode} requires critical assertion {aid}")
            if not assertion_is_satisfied(aid, str(row.get("state", ""))):
                errors.append(f"mode {mode} required assertion {aid} is {row.get('state')}")
    for index, phase in enumerate(phases):
        if not isinstance(phase, MappingABC):
            errors.append(f"phase row {index} is not an object")
            continue
        phase_id = phase.get("id")
        if not isinstance(phase_id, str):
            errors.append(f"phase row {index} id is not a string")
            continue
        if phase.get("state") != "RECORDED":
            errors.append(f"phase {phase_id} has invalid state")
        expected = list(PHASE_ASSERTIONS.get(phase_id, ()))
        if phase.get("assertion_ids") != expected:
            errors.append(f"phase {phase_id} assertion mapping mismatch")
    return errors

def _check_exact_ids(errors: list[str], rows: list[Any], expected: tuple[str, ...],
                     label: str):
    seen = []
    for index, row in enumerate(rows):
        if not isinstance(row, MappingABC):
            errors.append(f"{label} row {index} is not an object")
            continue
        row_id = row.get("id")
        if not isinstance(row_id, str):
            errors.append(f"{label} row {index} id is not a string")
            continue
        seen.append(row_id)
    counts = Counter(seen)
    missing = [x for x in expected if counts[x] == 0]
    unknown = [str(x) for x in seen if x not in expected]
    duplicate = [str(x) for x, count in counts.items() if count > 1]
    if missing:
        errors.append(f"missing {label} row(s): {', '.join(missing)}")
    if unknown:
        errors.append(f"unknown {label} row(s): {', '.join(unknown)}")
    if duplicate:
        errors.append(f"duplicate {label} row(s): {', '.join(duplicate)}")

def evaluate_build_binding(
    *,
    manifest_path: Path | None,
    expected_source: str,
    expected_version: str,
    expected_app_sha256: str,
    expected_engine_sha256: str,
    observed_app_sha256: str,
    observed_engine_sha256: str,
    observed_installed_version: str,
) -> tuple[bool, dict[str, Any]]:
    observed: dict[str, Any] = {
        "build_manifest_present": bool(manifest_path),
        "manifest_trust_boundary": BUILD_MANIFEST_TRUST_BOUNDARY,
        "source_commit_expected_supplied": bool(expected_source),
        "expected_version_supplied": bool(expected_version),
        "observed_installed_version": observed_installed_version or None,
        "app_sha256": observed_app_sha256 or None,
        "engine_sha256": observed_engine_sha256 or None,
    }
    failures: list[str] = []
    manifest = _read_manifest(manifest_path, observed, failures)
    binding = _manifest_binding(manifest)
    observed["manifest_binding"] = {k: bool(v) for k, v in binding.items()}
    _expect_equal(failures, binding["source_commit"], expected_source, "source_commit")
    _expect_equal(failures, binding["version"], expected_version, "version")
    _expect_equal(failures, observed_installed_version, expected_version, "installed_version")
    _expect_hash(failures, binding["app_sha256"], observed_app_sha256, "app_sha256")
    _expect_hash(failures, binding["engine_sha256"], observed_engine_sha256, "engine_sha256")
    if expected_app_sha256:
        _expect_hash(failures, expected_app_sha256, observed_app_sha256, "expected_app_sha256")
    if expected_engine_sha256:
        _expect_hash(failures, expected_engine_sha256, observed_engine_sha256,
                     "expected_engine_sha256")
    observed["binding_failures"] = failures
    return not failures, observed

def _read_manifest(path: Path | None, observed: dict[str, Any], failures: list[str]) -> dict:
    if not path:
        failures.append("build_manifest_required")
        return {}
    try:
        manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        failures.append("build_manifest_missing")
        return {}
    except Exception as exc:
        failures.append("build_manifest_malformed:" + type(exc).__name__)
        return {}
    if not isinstance(manifest, MappingABC):
        observed["build_manifest_schema"] = None
        failures.append("build_manifest_malformed:non_object")
        return {}
    observed["build_manifest_schema"] = manifest.get("schema")
    if manifest.get("schema") != BUILD_MANIFEST_SCHEMA:
        failures.append("build_manifest_schema_mismatch")
    return manifest

def _manifest_binding(manifest: Mapping[str, Any]) -> dict[str, str]:
    artifacts = manifest.get("artifacts", {}) if isinstance(manifest.get("artifacts"), dict) else {}
    source = manifest.get("source", {}) if isinstance(manifest.get("source"), dict) else {}
    build = manifest.get("build", {}) if isinstance(manifest.get("build"), dict) else {}
    return {
        "source_commit": _text(manifest.get("source_commit") or source.get("commit") or
                               build.get("source_commit")),
        "version": _text(manifest.get("version") or build.get("version")),
        "app_sha256": _hash(manifest.get("app_sha256") or artifacts.get("app_sha256")),
        "engine_sha256": _hash(manifest.get("engine_sha256") or artifacts.get("engine_sha256")),
    }

def _expect_equal(failures: list[str], left: str, right: str, label: str):
    if not left or not right:
        failures.append(label + "_missing")
    elif left != right:
        failures.append(label + "_mismatch")

def _expect_hash(failures: list[str], left: str, right: str, label: str):
    if not left or not right:
        failures.append(label + "_missing")
    elif left.lower() != right.lower():
        failures.append(label + "_mismatch")

def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""

def _hash(value: Any) -> str:
    text = _text(value).lower()
    return text if re.fullmatch(r"[0-9a-f]{64}", text) else ""
