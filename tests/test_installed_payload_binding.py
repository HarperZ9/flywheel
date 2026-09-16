import json
import os
from pathlib import Path

import pytest

from desktop.tool import installed_launch_acceptance as ila
from desktop.tool import installed_payload_binding as ipb
from tests.installed_launch_acceptance_fixtures import COMMIT, make_install, row, run_harness


def _manifest_with_payload(path: Path, install: Path) -> Path:
    files = []
    for relative in ("flywheel_desktop.exe", "data/app.so", "engine/flywheel-gateway.exe"):
        target = install / Path(relative)
        files.append({
            "path": relative,
            "origin": "build",
            "sha256": ila.sha256_file(target),
            "size": target.stat().st_size,
        })
    path.write_text(json.dumps({
        "schema": "flywheel.installed-build-manifest/v1",
        "source_commit": COMMIT,
        "version": "0.6.1",
        "artifacts": {
            "app_sha256": ila.sha256_file(install / "flywheel_desktop.exe"),
            "engine_sha256": ila.sha256_file(install / "engine" / "flywheel-gateway.exe"),
        },
        "payload": {"schema": "flywheel.installed-payload/v1", "files": files},
        "trust_boundary": "operator_supplied_integrity_binding",
    }), encoding="utf-8")
    return path


def _add_flutter_payload(install: Path) -> Path:
    (install / "data").mkdir(exist_ok=True)
    app_so = install / "data" / "app.so"
    app_so.write_bytes(b"compiled flutter payload v1")
    return app_so


def test_payload_manifest_rejects_changed_app_so_when_exe_hashes_match(tmp_path):
    install, app_sha, engine_sha = make_install(tmp_path)
    app_so = _add_flutter_payload(install)
    manifest = _manifest_with_payload(tmp_path / "build-manifest.json", install)

    app_so.write_bytes(b"compiled flutter payload v2")
    receipt = run_harness(tmp_path, install, build_manifest=manifest,
                          expected_app_sha256=app_sha, expected_engine_sha256=engine_sha)

    h20 = row(receipt, "H20_receipt_fresh_complete_and_source_bound")
    assert receipt["complete"] is False
    assert h20["state"] == "FAIL"
    assert "payload_file_hash_mismatch:data/app.so" in h20["observed_redacted"]["binding_failures"]


def test_matching_payload_manifest_allows_installer_generated_files_without_hashing_them(tmp_path):
    install, app_sha, engine_sha = make_install(tmp_path)
    _add_flutter_payload(install)
    manifest_body = ipb.build_manifest(
        [(install, "")], source_commit=COMMIT, version="0.6.1",
        installer_generated_files=["unins000.exe", "unins000.dat"])
    manifest_body["artifacts"]["app_sha256"] = app_sha
    manifest_body["artifacts"]["engine_sha256"] = engine_sha
    manifest = tmp_path / "build-manifest.json"
    manifest.write_text(json.dumps(manifest_body), encoding="utf-8")
    (install / "unins000.exe").write_bytes(b"inno uninstaller")
    (install / "unins000.dat").write_bytes(b"inno uninstall metadata")

    receipt = run_harness(tmp_path, install, build_manifest=manifest,
                          expected_app_sha256=app_sha, expected_engine_sha256=engine_sha)

    h20 = row(receipt, "H20_receipt_fresh_complete_and_source_bound")
    assert receipt["complete"] is True
    assert h20["state"] == "PASS"
    payload = h20["observed_redacted"]["payload_binding"]
    assert payload["build_file_count"] == 3
    assert payload["installer_generated_file_count"] == 2


def test_generated_origin_cannot_hide_build_payload_drift(tmp_path):
    install, _, _ = make_install(tmp_path)
    app_so = _add_flutter_payload(install)
    manifest = json.loads(_manifest_with_payload(tmp_path / "build-manifest.json", install).read_text())
    for item in manifest["payload"]["files"]:
        if item["path"] == "data/app.so":
            item.pop("sha256")
            item.pop("size")
            item["origin"] = "installer_generated"
    app_so.write_bytes(b"compiled flutter payload v2")

    report = ipb.verify_installed_payload(install, manifest)

    assert report["match"] is False
    assert "installer_generated_file_not_allowed:data/app.so" in report["failures"]


def test_producer_rejects_generated_paths_outside_inno_uninstaller_files(tmp_path):
    install, _, _ = make_install(tmp_path)
    _add_flutter_payload(install)

    with pytest.raises(ValueError, match="installer_generated_file_not_allowed:data/fake_generated.bin"):
        ipb.build_manifest([(install, "")], source_commit=COMMIT, version="0.6.1",
                           installer_generated_files=["data/fake_generated.bin"])


def test_legacy_launcher_engine_manifest_is_not_treated_as_full_payload_evidence(tmp_path):
    install, app_sha, engine_sha = make_install(tmp_path)
    manifest = tmp_path / "legacy-build-manifest.json"
    manifest.write_text(json.dumps({
        "schema": "flywheel.installed-build-manifest/v1",
        "source_commit": COMMIT,
        "version": "0.6.1",
        "artifacts": {"app_sha256": app_sha, "engine_sha256": engine_sha},
    }), encoding="utf-8")

    receipt = run_harness(tmp_path, install, build_manifest=manifest,
                          expected_app_sha256=app_sha, expected_engine_sha256=engine_sha)

    h20 = row(receipt, "H20_receipt_fresh_complete_and_source_bound")
    assert receipt["complete"] is False
    assert h20["state"] == "FAIL"
    assert "payload_manifest_missing" in h20["observed_redacted"]["binding_failures"]


def test_payload_manifest_requires_exact_payload_schema(tmp_path):
    install, _, _ = make_install(tmp_path)
    _add_flutter_payload(install)
    manifest = json.loads(_manifest_with_payload(tmp_path / "build-manifest.json", install).read_text())
    manifest["payload"].pop("schema")

    report = ipb.verify_installed_payload(install, manifest)

    assert report["match"] is False
    assert "payload_manifest_schema_mismatch" in report["failures"]


def test_payload_manifest_rejects_extra_installed_files(tmp_path):
    install, app_sha, engine_sha = make_install(tmp_path)
    _add_flutter_payload(install)
    manifest = _manifest_with_payload(tmp_path / "build-manifest.json", install)
    (install / "data" / "extra.bin").write_bytes(b"unexpected")

    receipt = run_harness(tmp_path, install, build_manifest=manifest,
                          expected_app_sha256=app_sha, expected_engine_sha256=engine_sha)

    h20 = row(receipt, "H20_receipt_fresh_complete_and_source_bound")
    assert receipt["complete"] is False
    assert "payload_extra_file:data/extra.bin" in h20["observed_redacted"]["binding_failures"]


def test_payload_manifest_rejects_traversal_and_case_colliding_paths(tmp_path):
    install, _, _ = make_install(tmp_path)
    _add_flutter_payload(install)
    manifest = json.loads(_manifest_with_payload(tmp_path / "build-manifest.json", install).read_text())
    manifest["payload"]["files"].append({
        "path": "../app.so", "origin": "build", "sha256": "0" * 64, "size": 1})
    manifest["payload"]["files"].append({
        "path": "DATA/app.so", "origin": "build", "sha256": "0" * 64, "size": 1})

    report = ipb.verify_installed_payload(install, manifest)

    assert report["match"] is False
    assert any(item.startswith("payload_file_path_") for item in report["failures"])
    assert "payload_path_case_collision:data/app.so" in report["failures"]


def test_manifest_paths_are_raw_identifiers_not_repaired(tmp_path):
    install, _, _ = make_install(tmp_path)
    _add_flutter_payload(install)
    manifest = json.loads(_manifest_with_payload(tmp_path / "build-manifest.json", install).read_text())
    for item in manifest["payload"]["files"]:
        if item["path"] == "data/app.so":
            item["path"] = "data/app.so\n"

    report = ipb.verify_installed_payload(install, manifest)

    assert report["match"] is False
    assert "payload_file_path_control_character" in report["failures"]


def test_installed_payload_rejects_links(tmp_path):
    install, _, _ = make_install(tmp_path)
    _add_flutter_payload(install)
    manifest = json.loads(_manifest_with_payload(tmp_path / "build-manifest.json", install).read_text())
    target = install / "data" / "linked-target.bin"
    target.write_bytes(b"target")
    link = install / "data" / "linked.bin"
    try:
        os.symlink(target, link)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    report = ipb.verify_installed_payload(install, manifest)

    assert report["match"] is False
    assert "installed_payload_link:data/linked.bin" in report["failures"]


def test_installed_payload_rejects_linked_install_root(tmp_path):
    install, _, _ = make_install(tmp_path / "real")
    _add_flutter_payload(install)
    manifest = json.loads(_manifest_with_payload(tmp_path / "build-manifest.json", install).read_text())
    link = tmp_path / "linked-root"
    try:
        os.symlink(install, link, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation is unavailable")

    report = ipb.verify_installed_payload(link, manifest)

    assert report["match"] is False
    assert "install_root_link:." in report["failures"]


def test_installed_payload_rejects_linked_install_root_ancestor(tmp_path):
    real_parent = tmp_path / "real-parent"
    install, _, _ = make_install(real_parent)
    _add_flutter_payload(install)
    manifest = json.loads(_manifest_with_payload(tmp_path / "build-manifest.json", install).read_text())
    link_parent = tmp_path / "linked-parent"
    try:
        os.symlink(real_parent, link_parent, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation is unavailable")

    report = ipb.verify_installed_payload(link_parent / "Flywheel", manifest)

    assert report["match"] is False
    assert any(item.startswith("install_root_ancestor_link:") for item in report["failures"])


def test_payload_hash_rejects_static_file_swap_during_read(tmp_path, monkeypatch):
    install, _, _ = make_install(tmp_path)
    app_so = _add_flutter_payload(install)
    manifest = json.loads(_manifest_with_payload(tmp_path / "build-manifest.json", install).read_text())
    original_open = Path.open
    replacement = b"swapped during verification with stat-visible extra bytes"
    assert len(replacement) != app_so.stat().st_size

    def swapping_open(path, *args, **kwargs):
        handle = original_open(path, *args, **kwargs)
        if Path(path).name == "app.so":
            with original_open(path, "wb") as replacement_file:
                replacement_file.write(replacement)
        return handle

    monkeypatch.setattr(Path, "open", swapping_open)

    report = ipb.verify_installed_payload(install, manifest)

    assert report["match"] is False
    assert "payload_file_changed_during_hash:data/app.so" in report["failures"]


def test_producer_requires_launcher_and_engine_build_hashes(tmp_path):
    payload = tmp_path / "payload"
    (payload / "data").mkdir(parents=True)
    (payload / "data" / "app.so").write_bytes(b"app so only")

    with pytest.raises(ValueError, match="required_build_payload_missing:flywheel_desktop.exe"):
        ipb.build_manifest([(payload, "")], source_commit=COMMIT, version="0.6.1")


def test_manifest_build_command_supports_prefixed_roots_and_generated_files(tmp_path, capsys):
    app_root = tmp_path / "app"
    engine_root = tmp_path / "engine-root"
    crt_root = tmp_path / "crt"
    for root in (app_root / "data", engine_root, crt_root):
        root.mkdir(parents=True)
    (app_root / "flywheel_desktop.exe").write_bytes(b"app")
    (app_root / "data" / "app.so").write_bytes(b"app so")
    (engine_root / "flywheel-gateway.exe").write_bytes(b"engine")
    (crt_root / "msvcp140.dll").write_bytes(b"crt")
    out = tmp_path / "manifest.json"

    code = ipb.main([
        "build", "--payload-root", str(app_root),
        "--payload-root", f"{engine_root}=engine", "--payload-root", str(crt_root),
        "--installer-generated", "unins000.exe", "--source-commit", COMMIT,
        "--version", "0.6.1", "--out", str(out)])

    assert code == 0
    summary = json.loads(capsys.readouterr().out)
    manifest = json.loads(out.read_text(encoding="utf-8"))
    paths = [item["path"] for item in manifest["payload"]["files"]]
    assert summary["file_count"] == 5
    assert "engine/flywheel-gateway.exe" in paths
    assert "unins000.exe" in paths
    assert manifest["payload"]["installer_generated_file_count"] == 1
