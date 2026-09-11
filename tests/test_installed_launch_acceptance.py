import json
import subprocess
import sys
from pathlib import Path

from desktop.tool import installed_launch_acceptance as ila
from desktop.tool import installed_launch_acceptance_platform as platform
from tests.installed_launch_acceptance_fixtures import (
    COMMIT, TOKEN, FakeHttp, FakeProcess, FakeWindows, build_manifest,
    make_install, powershell_for_selftest, row, run_harness, status_doc, valid_receipt, write_token,
)
def test_payload_preflight_requires_app_and_engine_under_same_install_root(tmp_path):
    install, app_sha, engine_sha = make_install(tmp_path)
    receipt = run_harness(
        tmp_path, install, expected_app_sha256=app_sha, expected_engine_sha256=engine_sha
    )
    assert receipt["complete"] is True
    assert ila.assertion_state(receipt, "H01_app_exe_exists") == "PASS"
    assert ila.assertion_state(receipt, "H02_engine_exe_exists_under_install_root") == "PASS"
    assert ila.assertion_state(receipt, "H20_receipt_fresh_complete_and_source_bound") == "PASS"
def test_installed_engine_assertion_refuses_path_fallback(tmp_path, monkeypatch):
    install, _, _ = make_install(tmp_path)
    (install / "engine" / "flywheel-gateway.exe").unlink()
    path_engine = tmp_path / "flywheel-gateway.exe"
    path_engine.write_bytes(b"path-engine")
    monkeypatch.setenv("PATH", str(tmp_path))

    receipt = run_harness(tmp_path, install)

    assert receipt["complete"] is False
    assert ila.assertion_state(receipt, "H02_engine_exe_exists_under_install_root") == "FAIL"
    assert str(path_engine) not in json.dumps(receipt)
def test_expected_installed_hash_mismatch_is_not_accepted(tmp_path):
    install, _, _ = make_install(tmp_path)
    receipt = run_harness(
        tmp_path,
        install,
        expected_app_sha256="0" * 64,
        expected_engine_sha256="1" * 64,
    )
    assert receipt["complete"] is False
    assert ila.assertion_state(receipt, "H20_receipt_fresh_complete_and_source_bound") == "FAIL"
def test_installer_payload_files_checked_when_expected(tmp_path):
    install, _, _ = make_install(tmp_path)
    receipt = run_harness(tmp_path, install, expect_installer_payload=True)
    assert receipt["complete"] is False
    assert ila.assertion_state(receipt, "H03_installer_payload_files_when_expected") == "FAIL"
def test_shortcuts_registry_and_protocol_are_typed_not_assumed(tmp_path):
    install, _, _ = make_install(tmp_path)
    app = install / "flywheel_desktop.exe"
    windows = FakeWindows(
        start=[ila.ShortcutRecord("Flywheel", app)],
        desktop=None,
        registry=ila.MetadataResult("ACCESS_DENIED", {"key": "uninstall"}),
        protocol=ila.MetadataResult("UNSUPPORTED"),
    )
    receipt = run_harness(tmp_path, install, mode="metadata", windows=windows)
    assert receipt["complete"] is False
    assert ila.assertion_state(receipt, "H04_start_menu_shortcut_targets_app_exe") == "PASS"
    assert ila.assertion_state(receipt, "H05_desktop_shortcut_optional_or_targets_app_exe") == "SKIP"
    assert ila.assertion_state(receipt, "H06_uninstall_registry_appid_singleton_or_access_denied") == "ACCESS_DENIED"
    assert ila.assertion_state(receipt, "H07_protocol_registration_supported_or_explicit_unsupported") == "UNSUPPORTED"
def test_start_menu_shortcut_must_target_installed_app(tmp_path):
    install, _, _ = make_install(tmp_path)
    other = tmp_path / "other.exe"
    other.write_bytes(b"other")
    windows = FakeWindows(start=[ila.ShortcutRecord("Flywheel", other)])
    receipt = run_harness(tmp_path, install, mode="metadata", windows=windows)
    assert receipt["complete"] is False
    assert ila.assertion_state(receipt, "H04_start_menu_shortcut_targets_app_exe") == "FAIL"
def test_local_paths_are_redacted_unless_included(tmp_path):
    install, _, _ = make_install(tmp_path)
    registry = ila.MetadataResult("PASS", {"InstallLocation": str(install)})
    windows = FakeWindows(registry=registry)
    redacted = run_harness(tmp_path, install, windows=windows)
    visible = run_harness(tmp_path, install, windows=windows, include_local_paths=True)
    assert row(redacted, "H06_uninstall_registry_appid_singleton_or_access_denied")["observed_redacted"]["InstallLocation"] != str(install)
    assert row(visible, "H06_uninstall_registry_appid_singleton_or_access_denied")["observed_redacted"]["InstallLocation"] == str(install)
def test_port_occupied_fails_before_starting_engine(tmp_path):
    install, _, _ = make_install(tmp_path)
    process = FakeProcess(port_open_before=True)
    receipt = run_harness(tmp_path, install, start_engine=True, process=process)
    assert ila.assertion_state(receipt, "H08_port_precheck_refuses_foreign_gateway") == "PORT_OCCUPIED_PRECHECK"
    assert process.started == []

def test_world_liveness_cannot_substitute_for_desktop_status_schema(tmp_path):
    install, _, _ = make_install(tmp_path)
    http = FakeHttp(status=[(404, {"error": "missing"})], world=[(200, {"ok": True})])
    process = FakeProcess()
    receipt = run_harness(tmp_path, install, start_engine=True, http=http, process=process)
    assert receipt["complete"] is False
    assert ila.assertion_state(receipt, "H10_desktop_status_schema_required") == "STATUS_CONTRACT_MISSING"

def test_owned_status_uses_token_without_recording_value_or_hash(tmp_path):
    install, _, _ = make_install(tmp_path)
    token_path = write_token(tmp_path)
    status = status_doc(live=2, total=2)
    http = FakeHttp(status=[(200, status)], world=[(200, {"world": True})])
    process = FakeProcess()

    receipt = run_harness(
        tmp_path, install, start_engine=True, artifact_root=token_path.parents[1],
        http=http, process=process,
    )

    text = json.dumps(receipt)
    assert receipt["complete"] is True
    assert TOKEN not in text
    assert ila.sha256_text(TOKEN)[:12] not in text
    assert ila.assertion_state(receipt, "H11_token_used_but_redacted") == "PASS"
    assert "PYTHONPATH" not in process.started[0][2]
    assert all("KEY" not in name and "TOKEN" not in name for name in process.started[0][2])

def test_listener_pid_and_cleanup_are_required(tmp_path):
    install, _, _ = make_install(tmp_path)
    status = status_doc()
    process = FakeProcess(listener_pid=99, survivors=[99])
    receipt = run_harness(tmp_path, install, start_engine=True, http=FakeHttp(status=[(200, status)]), process=process)
    assert receipt["complete"] is False
    assert ila.assertion_state(receipt, "H09_installed_engine_owned_start") == "FAIL"
    assert ila.assertion_state(receipt, "H12_owned_process_cleanup_no_survivors") == "FAIL"

def test_journey_restart_upgrade_and_lane_boundaries_are_explicit(tmp_path):
    install, _, _ = make_install(tmp_path)
    before = {"schema": ila.SCHEMA, "run_id": "before", "artifacts": {"app_id": ila.APP_ID}}
    before_path = tmp_path / "before.json"
    before_path.write_text(json.dumps(before), encoding="utf-8")
    token_path = write_token(tmp_path)
    status = status_doc("degraded", live=1, total=2)
    journey = {"schema": "flywheel.evidence-journey-list/v2", "journeys": []}
    http = FakeHttp(status=[(200, status), (200, status)], world=[(200, {})], journey=[(200, journey)])
    receipt = run_harness(tmp_path, install, start_engine=True, mode="full", http=http,
                          process=FakeProcess(), before_receipt=before_path,
                          artifact_root=token_path.parents[1])
    assert ila.assertion_state(receipt, "H14_journey_read_only_availability_or_typed_unavailable") == "READY_EMPTY"
    assert ila.assertion_state(receipt, "H16_restart_same_isolated_profile") == "PASS"
    assert ila.assertion_state(receipt, "H17_upgrade_before_after_snapshot_compare") == "UPGRADE_NOT_CHECKED"
    assert ila.assertion_state(receipt, "H18_known_unavailable_lanes_not_live") == "PASS"
    assert ila.assertion_state(receipt, "H19_standalone_cli_separated_from_installed_engine") == "PASS"

def test_metadata_mode_no_windows_adapter_cannot_complete(tmp_path):
    install, _, _ = make_install(tmp_path)
    receipt = run_harness(tmp_path, install, mode="metadata", windows=ila.NullWindowsMetadata())
    assert receipt["complete"] is False
    assert ila.assertion_state(receipt, "H04_start_menu_shortcut_targets_app_exe") == "UNTESTED"
    assert ila.assertion_state(receipt, "H06_uninstall_registry_appid_singleton_or_access_denied") == "UNTESTED"

def test_h20_requires_manifest_hashes_and_observed_installed_version(tmp_path):
    install, app_sha, engine_sha = make_install(tmp_path)
    no_manifest = run_harness(
        tmp_path, install, build_manifest=None,
        expected_app_sha256=app_sha, expected_engine_sha256=engine_sha,
    )
    no_version = run_harness(
        tmp_path, install, windows=FakeWindows(registry=ila.MetadataResult("PASS", {"AppId": ila.APP_ID})),
    )
    assert no_manifest["complete"] is False
    assert no_version["complete"] is False
    assert ila.assertion_state(no_manifest, "H20_receipt_fresh_complete_and_source_bound") == "FAIL"
    assert ila.assertion_state(no_version, "H20_receipt_fresh_complete_and_source_bound") == "FAIL"

def test_h20_rejects_bad_manifest_contract(tmp_path):
    install, app_sha, engine_sha = make_install(tmp_path)
    base = {"schema": "flywheel.installed-build-manifest/v1", "source_commit": COMMIT,
            "version": "0.6.1", "artifacts": {"app_sha256": app_sha, "engine_sha256": engine_sha}}
    cases = [
        ("unknown_schema", {"schema": "unknown"}),
        ("bad_hash_shape", {"artifacts": {"app_sha256": "abc", "engine_sha256": engine_sha}}),
        ("stale_source", {"source_commit": "old"}),
        ("stale_version", {"version": "0.6.0"}),
        ("missing_hashes", {"artifacts": {}}),
    ]
    for name, patch in cases:
        body = json.loads(json.dumps(base))
        body.update(patch)
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(body), encoding="utf-8")
        receipt = run_harness(tmp_path, install, build_manifest=path)
        assert receipt["complete"] is False, name
        assert ila.assertion_state(receipt, "H20_receipt_fresh_complete_and_source_bound") == "FAIL"

def test_registry_duplicate_flywheel_entries_fail_exact_appid_singleton():
    entries = [
        {"registry_key": ila.APP_ID + "_is1", "DisplayName": "Flywheel", "AppId": ila.APP_ID},
        {"registry_key": "stale_flywheel_is1", "DisplayName": "Flywheel"},
    ]
    result = ila.LocalWindowsMetadata().classify_uninstall_entries(ila.APP_ID, entries)
    assert result.state == "FAIL"
    assert result.reason == "duplicate_or_ambiguous_appid"
    mismatch = ila.LocalWindowsMetadata().classify_uninstall_entries(
        ila.APP_ID, [entries[0] | {"InstallLocation": "C:/Other/Flywheel"}], Path("C:/Expected/Flywheel"))
    assert mismatch.reason == "install_root_mismatch"

def test_journey_list_uses_post_route_and_schema(tmp_path):
    install, _, _ = make_install(tmp_path)
    token_path = write_token(tmp_path)
    status = status_doc()
    body = {"schema": "flywheel.evidence-journey-list/v2", "journeys": []}
    http = FakeHttp(status=[(200, status), (200, status)], journey=[(200, body)])
    receipt = run_harness(tmp_path, install, start_engine=True, mode="full", http=http,
                          process=FakeProcess(), artifact_root=token_path.parents[1])
    assert receipt["complete"] is True
    assert any(call[0] == "POST" and call[1].endswith("/api/journeys/list") for call in http.calls)
    assert ila.assertion_state(receipt, "H14_journey_read_only_availability_or_typed_unavailable") == "READY_EMPTY"

def test_journey_unavailable_does_not_complete_full_mode(tmp_path):
    install, _, _ = make_install(tmp_path)
    token_path = write_token(tmp_path)
    status = status_doc()
    http = FakeHttp(status=[(200, status), (200, status)], journey=[(404, {"error": "missing"})])
    receipt = run_harness(tmp_path, install, start_engine=True, mode="full", http=http,
                          process=FakeProcess(), artifact_root=token_path.parents[1])
    assert receipt["complete"] is False
    assert ila.assertion_state(receipt, "H14_journey_read_only_availability_or_typed_unavailable") == "UNAVAILABLE"

def test_cleanup_fails_for_nonlistening_descendant_survivor(tmp_path):
    install, _, _ = make_install(tmp_path)
    status = status_doc()
    receipt = run_harness(tmp_path, install, start_engine=True, http=FakeHttp(status=[(200, status)]),
                          process=FakeProcess(listener_pid=44, survivors=[55]))
    assert receipt["complete"] is False
    assert ila.assertion_state(receipt, "H09_installed_engine_owned_start") == "PASS"
    assert ila.assertion_state(receipt, "H12_owned_process_cleanup_no_survivors") == "FAIL"

def test_captured_descendant_survivor_uses_creation_time_to_avoid_pid_reuse():
    captured = [{"pid": 55, "creation_time": "created-a"}]
    assert platform._surviving_captured_pids(captured, {55: "created-a"}) == [55]
    assert platform._surviving_captured_pids(captured, {55: "created-b"}) == []
    assert platform._surviving_captured_pids(captured, {}) == [55]

def test_verify_receipt_rejects_missing_stale_incomplete_and_malformed(tmp_path):
    missing = tmp_path / "missing.json"
    for path, body in [
        (tmp_path / "stale.json", {"schema": ila.SCHEMA, "run_id": "old", "complete": True}),
        (tmp_path / "incomplete.json", {"schema": ila.SCHEMA, "run_id": "run-a", "complete": False}),
        (tmp_path / "malformed.json", "{"),
    ]:
        path.write_text(body if isinstance(body, str) else json.dumps(body), encoding="utf-8")
    for path in [missing, tmp_path / "stale.json", tmp_path / "incomplete.json", tmp_path / "malformed.json"]:
        try:
            ila.verify_receipt_file(path, "run-a")
        except ila.ReceiptError:
            pass
        else:
            raise AssertionError(f"accepted bad receipt {path}")

def test_verify_receipt_requires_exact_assertion_and_phase_rows(tmp_path):
    base = valid_receipt()

    def rejected(name, mutate):
        body = json.loads(json.dumps(base))
        mutate(body)
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(body), encoding="utf-8")
        try:
            ila.verify_receipt_file(path, "run-a")
        except ila.ReceiptError:
            return
        raise AssertionError(f"accepted bad semantic receipt {name}")

    rejected("missing-h01", lambda b: b["assertions"].pop(0))
    rejected("missing-h14", lambda b: b["assertions"].__setitem__(13, {"id": "H99_unknown", "state": "PASS"}))
    rejected("duplicate-h20", lambda b: b["assertions"].append({"id": b["assertions"][-1]["id"], "state": "PASS"}))
    rejected("phase-missing", lambda b: b["phase_results"].pop())
    rejected("required-untested", lambda b: b["assertions"][0].update({"state": "UNTESTED"}))
    rejected("metadata-required-info", lambda b: (b.update({"mode": "metadata"}), b["assertions"][3].update({"severity": "info"})))

def test_cli_synthetic_fixture_requires_installed_metadata_for_complete_receipt(tmp_path):
    install, app_sha, engine_sha = make_install(tmp_path)
    manifest = build_manifest(tmp_path, install, app_sha=app_sha, engine_sha=engine_sha)
    out = tmp_path / "cli-receipt.json"
    cmd = [
        sys.executable, "desktop/tool/installed_launch_acceptance.py",
        "--install-root", str(install), "--out", str(out), "--run-id", "cli-run",
        "--source-commit-expected", COMMIT, "--expected-version", "0.6.1",
        "--expected-app-sha256", app_sha, "--expected-engine-sha256", engine_sha,
        "--build-manifest", str(manifest),
    ]
    completed = subprocess.run(cmd, cwd=Path(__file__).parents[1], text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert completed.returncode == 1
    receipt = json.loads(out.read_text(encoding="utf-8"))
    assert receipt["run_id"] == "cli-run"
    assert receipt["complete"] is False
    assert ila.assertion_state(receipt, "H20_receipt_fresh_complete_and_source_bound") == "FAIL"
    assert str(out) not in completed.stdout

def test_powershell_wrapper_selftest_rejects_bad_receipts():
    repo = Path(__file__).parents[1]
    script = repo / "desktop" / "tool" / "run_installed_launch_acceptance.ps1"
    completed = subprocess.run(
        [powershell_for_selftest(), "-ExecutionPolicy", "Bypass", "-File", str(script), "-SelfTest"],
        cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0, completed.stderr
    assert "zero-exit-missing-receipt" in completed.stdout
    assert "fw-launch-paths-20260910" not in completed.stdout
    assert json.loads(completed.stdout)["root"] == "<redacted-local-path>"
