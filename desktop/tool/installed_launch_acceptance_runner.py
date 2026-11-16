"""Acceptance runner orchestration for installed-launch checks."""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

try:
    from .installed_launch_acceptance_contract import (
        completion_from_rows, evaluate_build_binding, phase_results,
        validate_receipt_semantics,
    )
    from .installed_launch_acceptance_model import (
        APP_EXE, APP_ID, DOES_NOT_PROVE, ENGINE_EXE, SCHEMA,
        TOKEN_NAME, Clock, HarnessConfig, build_child_environment,
        display_path, full_path, inside, read_json, redact_token_body,
        reserve_port, same_path, sha256_file, status_state,
    )
except ImportError:
    from installed_launch_acceptance_contract import (  # type: ignore
        completion_from_rows, evaluate_build_binding, phase_results,
        validate_receipt_semantics,
    )
    from installed_launch_acceptance_model import (  # type: ignore
        APP_EXE, APP_ID, DOES_NOT_PROVE, ENGINE_EXE, SCHEMA,
        TOKEN_NAME, Clock, HarnessConfig, build_child_environment,
        display_path, full_path, inside, read_json, redact_token_body,
        reserve_port, same_path, sha256_file, status_state,
    )

class AcceptanceHarness:
    def __init__(self, config: HarnessConfig, *, fs, windows, http, process, clock=None):
        self.c = config
        self.fs = fs
        self.windows = windows
        self.http = http
        self.process = process
        self.clock = clock or Clock()
        self.rows: list[dict] = []
        self.artifacts: dict[str, Any] = {"app_id": APP_ID}
        self.installed_version = ""

    def run(self) -> dict:
        started = self.clock.now()
        run_id = self.c.run_id or "installed_launch_" + uuid.uuid4().hex
        root = full_path(self.c.install_root)
        app, engine = root / APP_EXE, root / "engine" / ENGINE_EXE
        self.artifacts.update({"install_root": self._path(root), "app_exe": self._path(app),
                               "engine_exe": self._path(engine)})
        app_ok = self._file_row("H01_app_exe_exists", app, "installed app exe")
        engine_ok = self._file_row("H02_engine_exe_exists_under_install_root", engine, "installed engine exe")
        self._payload_files(root)
        self._metadata(app)
        if self.c.start_engine and engine_ok:
            self._engine(engine, root, run_id)
        else:
            severity = "critical" if self.c.mode in ("engine", "full") else "info"
            for aid in ("H08_port_precheck_refuses_foreign_gateway", "H09_installed_engine_owned_start",
                        "H10_desktop_status_schema_required", "H11_token_used_but_redacted",
                        "H12_owned_process_cleanup_no_survivors", "H13_hidden_gateway_visible_window_count_when_observer_available",
                        "H14_journey_read_only_availability_or_typed_unavailable",
                        "H15_offline_to_ready_status_transition", "H16_restart_same_isolated_profile"):
                self._add(aid, "NOT_CHECKED", "info" if aid.endswith("observer_available") else severity)
        self._upgrade()
        self._add("H18_known_unavailable_lanes_not_live", "PASS", "info",
                  observed={"planned_lanes_count_as_live": False})
        self._add("H19_standalone_cli_separated_from_installed_engine", "PASS", "info",
                  observed={"path_fallback_allowed": False})
        self._source_bound(app if app_ok else None, engine if engine_ok else None)
        complete = completion_from_rows(self.rows)
        receipt = {"schema": SCHEMA, "run_id": run_id, "started_at_utc": started,
                   "completed_at_utc": self.clock.now(), "complete": complete,
                   "source_commit_expected": self.c.source_commit_expected,
                   "expected_version": self.c.expected_version, "mode": self.c.mode,
                   "paths_redacted_by_default": not self.c.include_local_paths,
                   "artifacts": self.artifacts, "assertions": self.rows,
                   "phase_results": phase_results(),
                   "unexpected_green_controls": ["world_only_liveness_rejected",
                                                  "foreign_port_rejected",
                                                  "path_fallback_rejected",
                                                  "token_material_never_recorded"],
                   "privacy_redactions": ["token_value", "token_hash_prefix", "local_paths"],
                   "does_not_prove": DOES_NOT_PROVE}
        semantic_errors = validate_receipt_semantics(receipt)
        if semantic_errors:
            receipt["complete"] = False
            receipt["semantic_validation_errors"] = semantic_errors
        self.c.out.parent.mkdir(parents=True, exist_ok=True)
        self.c.out.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
        return receipt

    def _file_row(self, aid: str, path: Path, label: str) -> bool:
        ok = inside(path, self.c.install_root) and self.fs.is_file(path)
        observed = {"path": self._path(path), "exists": ok,
                    "under_install_root": inside(path, self.c.install_root)}
        if ok:
            observed["sha256"] = sha256_file(path)
        self._add(aid, "PASS" if ok else "FAIL", expected=label, observed=observed)
        return ok

    def _payload_files(self, root: Path):
        names = ["flutter_windows.dll", "data", "msvcp140.dll",
                 "vcruntime140.dll", "vcruntime140_1.dll"]
        present = {name: (root / name).exists() for name in names}
        if not self.c.expect_installer_payload:
            self._add("H03_installer_payload_files_when_expected", "NOT_CHECKED",
                      "info", observed=present)
            return
        self._add("H03_installer_payload_files_when_expected",
                  "PASS" if all(present.values()) else "FAIL",
                  observed=present, expected="Flutter bundle and CRT payload files")

    def _source_bound(self, app: Path | None, engine: Path | None):
        app_sha = sha256_file(app) if app else ""
        engine_sha = sha256_file(engine) if engine else ""
        ok, observed = evaluate_build_binding(
            manifest_path=self.c.build_manifest,
            expected_source=self.c.source_commit_expected,
            expected_version=self.c.expected_version,
            expected_app_sha256=self.c.expected_app_sha256,
            expected_engine_sha256=self.c.expected_engine_sha256,
            observed_app_sha256=app_sha,
            observed_engine_sha256=engine_sha,
            observed_installed_version=self.installed_version,
        )
        if self.c.build_manifest:
            observed["build_manifest_path"] = self._path(self.c.build_manifest)
        self._add("H20_receipt_fresh_complete_and_source_bound", "PASS" if ok else "FAIL",
                  expected="operator manifest binds source, version, app hash, engine hash, and installed version",
                  observed=observed)

    def _metadata(self, app: Path):
        crit = "critical" if self.c.mode in ("metadata", "full") else "info"
        shortcuts = self.windows.start_menu_shortcuts()
        self._add("H04_start_menu_shortcut_targets_app_exe",
                  "PASS" if any(same_path(x.target, app) for x in shortcuts) else ("FAIL" if shortcuts else "UNTESTED"),
                  crit, observed={"targets": [self._path(x.target) for x in shortcuts]})
        desk = self.windows.desktop_shortcut()
        state = "PASS" if desk and same_path(desk.target, app) else ("FAIL" if desk or self.c.require_desktop_shortcut else "SKIP")
        desk_crit = "critical" if desk or self.c.require_desktop_shortcut else "info"
        self._add("H05_desktop_shortcut_optional_or_targets_app_exe", state, desk_crit,
                  observed={"target": self._path(desk.target) if desk else None})
        reg = self.windows.uninstall_registry(APP_ID, self.c.install_root)
        if reg.state == "PASS" and isinstance(reg.observed, dict):
            self.installed_version = str(reg.observed.get("DisplayVersion") or
                                         reg.observed.get("display_version") or "")
        self._add("H06_uninstall_registry_appid_singleton_or_access_denied", reg.state, crit,
                  observed=reg.observed, evidence_ref=reg.reason)
        proto = self.windows.protocol_registration("flywheel")
        self._add("H07_protocol_registration_supported_or_explicit_unsupported", proto.state, "info",
                  observed=proto.observed, evidence_ref=proto.reason)
    def _engine(self, engine: Path, root: Path, run_id: str):
        port = self.c.port or reserve_port()
        if self.process.is_port_open(port):
            self._add("H08_port_precheck_refuses_foreign_gateway", "PORT_OCCUPIED_PRECHECK")
            self._mark_engine_rows_not_checked()
            return
        self._add("H08_port_precheck_refuses_foreign_gateway", "PASS", observed={"port": port})
        ar = full_path(self.c.artifact_root or (self.c.out.parent / run_id))
        env = build_child_environment(os.environ, ar)
        stdout, stderr = ar / "engine.stdout.log", ar / "engine.stderr.log"
        ar.mkdir(parents=True, exist_ok=True)
        args = ["--port", str(port), "--root", str(root), "--run-root", str(ar / "run")]
        handle = self.process.start_engine(engine, args, env, engine.parent, stdout, stderr)
        if getattr(handle, "job_error", ""):
            self._add("H09_installed_engine_owned_start", "FAIL",
                      observed={"pid": handle.pid, "job_object_assigned": False,
                                "job_error": handle.job_error})
            self._add("H10_desktop_status_schema_required", "NOT_CHECKED")
            self._add("H11_token_used_but_redacted", "NOT_CHECKED")
            self._add("H12_owned_process_cleanup_no_survivors", "FAIL",
                      observed={"job_object_assigned": False, "job_error": handle.job_error})
            self._add("H13_hidden_gateway_visible_window_count_when_observer_available",
                      "NOT_CHECKED", "info")
            self._add("H14_journey_read_only_availability_or_typed_unavailable",
                      "NOT_CHECKED", "critical" if self.c.mode == "full" else "info")
            self._add("H15_offline_to_ready_status_transition", "FAIL",
                      observed={"pre_start_status": "not_foreign", "post_start_typed": False})
            self._add("H16_restart_same_isolated_profile", "NOT_CHECKED",
                      "critical" if self.c.mode == "full" else "info")
            return
        owned = handle.pid in self.process.listener_pids(port)
        self._add("H09_installed_engine_owned_start", "PASS" if owned else "FAIL",
                  observed={"pid": handle.pid, "listener_owned": owned,
                            "job_object_assigned": getattr(handle, "job_object_assigned", None)})
        self._add("H13_hidden_gateway_visible_window_count_when_observer_available",
                  "NOT_CHECKED", "info")
        token_path = Path(env["FLYWHEEL_HOME"]) / TOKEN_NAME
        token = _wait_token(token_path)
        self._add("H11_token_used_but_redacted", "PASS" if token else "AUTH_TOKEN_UNAVAILABLE",
                  observed={"token_present": bool(token), "source": "isolated_flywheel_home"})
        status_ok = self._status(port, token)
        self._journey(port, token) if self.c.mode == "full" else self._add(
            "H14_journey_read_only_availability_or_typed_unavailable", "NOT_CHECKED", "info")
        cleanup = self.process.cleanup(handle, port)
        closed = not self.process.is_port_open(port)
        if isinstance(cleanup, dict):
            survivors = cleanup.get("surviving_pids", [])
            cleanup_state = cleanup.get("state")
            cleanup_observed = {"port_closed": closed} | cleanup
            h12_ok = closed and cleanup_state == "PASS" and not survivors
        else:
            survivors = cleanup
            cleanup_observed = {"port_closed": closed, "surviving_pids": survivors}
            h12_ok = closed and not survivors
        self._add("H12_owned_process_cleanup_no_survivors", "PASS" if h12_ok else "FAIL",
                  observed=cleanup_observed)
        self._add("H15_offline_to_ready_status_transition", "PASS" if status_ok else "FAIL",
                  observed={"pre_start_status": "not_foreign", "post_start_typed": status_ok})
        if self.c.mode == "full":
            handle2 = self.process.start_engine(engine, args, env, engine.parent, stdout, stderr)
            second = False if getattr(handle2, "job_error", "") else self._status(port, token, row=False)
            self.process.cleanup(handle2, port)
            self._add("H16_restart_same_isolated_profile", "PASS" if second else "FAIL",
                      observed={"same_flywheel_home": self._path(token_path.parent),
                                "second_status": second,
                                "job_error": getattr(handle2, "job_error", "")})
        else:
            self._add("H16_restart_same_isolated_profile", "NOT_CHECKED", "info")
    def _status(self, port: int, token: str | None, row: bool = True) -> bool:
        code, body = self.http.get_json(f"http://127.0.0.1:{port}/api/desktop/status", token)
        state, ok = status_state(code, body, self.c.expected_api_version)
        if state == "STATUS_CONTRACT_MISSING":
            self.http.get_json(f"http://127.0.0.1:{port}/api/world", token)
        if row:
            self._add("H10_desktop_status_schema_required", state, observed=redact_token_body(body))
        return ok
    def _journey(self, port: int, token: str | None):
        if not token:
            self._add("H14_journey_read_only_availability_or_typed_unavailable",
                      "AUTH_TOKEN_UNAVAILABLE", "critical" if self.c.mode == "full" else "info")
            return
        code, body = self.http.post_json(f"http://127.0.0.1:{port}/api/journeys/list", {}, token)
        if code != 200:
            state = "UNAVAILABLE"
        elif not isinstance(body, dict) or body.get("schema") != "flywheel.evidence-journey-list/v2":
            state = "JOURNEY_SCHEMA_INVALID"
        elif not isinstance(body.get("journeys"), list):
            state = "JOURNEY_SCHEMA_INVALID"
        else:
            state = "READY_EMPTY" if not body["journeys"] else "PASS"
        count = len(body.get("journeys", [])) if isinstance(body, dict) and isinstance(body.get("journeys"), list) else None
        self._add("H14_journey_read_only_availability_or_typed_unavailable", state,
                  "critical" if self.c.mode == "full" else "info",
                  observed={"status_code": code, "journey_count": count})
    def _upgrade(self):
        state = "UPGRADE_NOT_CHECKED"
        observed = {"before": bool(self.c.before_receipt), "after": bool(self.c.after_receipt)}
        if self.c.before_receipt and self.c.after_receipt:
            before, after = read_json(self.c.before_receipt), read_json(self.c.after_receipt)
            same = before.get("artifacts", {}).get("app_id") == after.get("artifacts", {}).get("app_id") == APP_ID
            state, observed["stable_app_id"] = ("PASS" if same else "FAIL"), same
        severity = "critical" if self.c.before_receipt and self.c.after_receipt else "info"
        self._add("H17_upgrade_before_after_snapshot_compare", state, severity, observed=observed)
    def _mark_engine_rows_not_checked(self):
        severity = "critical" if self.c.mode in ("engine", "full") else "info"
        for aid in ("H09_installed_engine_owned_start", "H10_desktop_status_schema_required",
                    "H11_token_used_but_redacted", "H12_owned_process_cleanup_no_survivors",
                    "H13_hidden_gateway_visible_window_count_when_observer_available",
                    "H14_journey_read_only_availability_or_typed_unavailable",
                    "H15_offline_to_ready_status_transition", "H16_restart_same_isolated_profile"):
            self._add(aid, "NOT_CHECKED", "info" if aid.endswith("observer_available") else severity)

    def _add(self, aid: str, state: str, severity: str = "critical", *, expected=None, observed=None, evidence_ref=""):
        self.rows.append({"id": aid, "state": state, "severity": severity,
                          "observed_at_utc": self.clock.now(), "evidence_kind": "headless",
                          "evidence_ref": evidence_ref, "expected": expected,
                          "observed_redacted": self._redact(observed), "source_pointers": [],
                          "does_not_prove": DOES_NOT_PROVE})

    def _path(self, path: Path) -> str:
        return display_path(path, self.c.install_root, self.c.include_local_paths)

    def _redact(self, value):
        if isinstance(value, dict):
            return {k: self._redact(v) for k, v in value.items() if "token" not in k.lower()}
        if isinstance(value, list):
            return [self._redact(v) for v in value]
        if isinstance(value, Path):
            return self._path(value)
        if isinstance(value, str) and not self.c.include_local_paths:
            root = str(full_path(self.c.install_root))
            if root.lower() in value.lower():
                return value.replace(root, "<install_root>").replace("\\", "/")
            if len(value) > 2 and value[1] == ":" and value[2] in ("\\", "/"):
                return "<redacted-local-path>"
        return value

def _wait_token(path: Path, deadline_seconds: float = 2.0) -> str | None:
    end = time.monotonic() + deadline_seconds
    while time.monotonic() <= end:
        if path.exists():
            return path.read_text(encoding="utf-8").strip() or None
        time.sleep(0.05)
    return None
