from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.studio_runtime_packaging import (
    LICENSE_DESTINATION,
    PAYLOAD_MANIFEST_DESTINATION,
    PYTHON_RUNTIME_DIR,
    STUDIO_RUNTIME_MANIFEST_ENV,
    STUDIO_RUNTIME_PAYLOAD_ENV,
    build_studio_runtime_payload,
    check_studio_runtime_payload,
    pyinstaller_studio_runtime_inputs,
)


def _write(path: Path, text: str = "# fixture\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_manifest(tmp_path: Path) -> tuple[Path, dict]:
    engine = tmp_path / "engine"
    engine_files = [
        "pyproject.toml",
        "studio_engine/__init__.py",
        "studio_engine/engine.py",
    ]
    _write(engine / "pyproject.toml", "[project]\nname = 'studio-engine'\n")
    _write(engine / "studio_engine" / "__init__.py")
    _write(engine / "studio_engine" / "engine.py")
    _write(engine / "studio_engine" / "private_extra.py")

    account = tmp_path / "accountable" / "src"
    account_files = [
        "accountable_surface/remote_actuation.py",
        "accountable_surface/remote_durable.py",
        "accountable_surface/effector.py",
    ]
    for rel in account_files:
        _write(account / rel)
    _write(account / "accountable_surface" / "unlisted.py")

    membrane = tmp_path / "membrane" / "src"
    membrane_files = [
        "coherence_membrane/membrane.py",
        "coherence_membrane/observation.py",
        "coherence_membrane/organs/web.py",
    ]
    for rel in membrane_files:
        _write(membrane / rel)

    proof = tmp_path / "proof" / "src"
    proof_files = [
        "proof_surface/__init__.py",
        "proof_surface/_validate.py",
        "proof_surface/authorization_receipt.py",
    ]
    for rel in proof_files:
        _write(proof / rel)

    def section(root: Path, files: list[str], entries: list[str]) -> dict:
        return {
            "status": "ready",
            "source_root": str(root),
            "entry_modules": entries,
            "files": files,
            "file_hashes": {rel: _sha(root / rel) for rel in files},
        }

    doc = {
        "schema": "flywheel.studio-body-runtime-manifest/v1",
        "created_at": "2026-09-15T14:00:00Z",
        "studio_engine": {
            "status": "ready",
            "root": str(engine),
            "required_files": engine_files,
            "required_file_hashes": {rel: _sha(engine / rel) for rel in engine_files},
        },
        "accountable_surface": section(
            account, account_files, ["accountable_surface.remote_actuation"]
        ),
        "coherence_membrane": section(
            membrane, membrane_files, ["coherence_membrane.organs.web"]
        ),
        "proof_surface": section(proof, proof_files, ["proof_surface"]),
    }
    manifest = tmp_path / "studio-manifest.json"
    manifest.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return manifest, doc


def _license(tmp_path: Path) -> Path:
    path = tmp_path / "THIRD-PARTY-NOTICES.txt"
    _write(path, "Fixture Studio runtime notices\n")
    return path


def test_payload_checker_rejects_manifest_drift_without_source_file_changes(tmp_path):
    manifest, _doc = _source_manifest(tmp_path)
    payload = tmp_path / "payload"
    build_studio_runtime_payload(manifest, payload, license_notice_paths=[_license(tmp_path)])
    packaged = payload / PAYLOAD_MANIFEST_DESTINATION
    altered = json.loads(packaged.read_text(encoding="utf-8"))
    altered["studio_engine"]["expected_head"] = "0" * 40
    packaged.write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(RuntimeError, match="packaged Studio runtime manifest differs"):
        check_studio_runtime_payload(manifest, payload)


def test_payload_builder_copies_only_manifest_files_and_strips_source_roots(tmp_path):
    manifest, doc = _source_manifest(tmp_path)
    payload = tmp_path / "payload"

    result = build_studio_runtime_payload(
        manifest, payload, license_notice_paths=[_license(tmp_path)]
    )

    assert result["file_count"] == 3 + 3 + 3 + 3
    assert (payload / "harness/studio_engine_bundle/studio_engine/engine.py").is_file()
    assert not (payload / "harness/studio_engine_bundle/studio_engine/private_extra.py").exists()
    assert (payload / PYTHON_RUNTIME_DIR / "accountable_surface/remote_durable.py").is_file()
    assert not (payload / PYTHON_RUNTIME_DIR / "accountable_surface/unlisted.py").exists()
    packaged = json.loads((payload / PAYLOAD_MANIFEST_DESTINATION).read_text())
    assert str(tmp_path) not in json.dumps(packaged)
    assert packaged["studio_engine"]["required_file_hashes"] == doc[
        "studio_engine"
    ]["required_file_hashes"]
    assert (payload / LICENSE_DESTINATION / "THIRD-PARTY-NOTICES.txt").is_file()


def test_payload_builder_keeps_duplicate_license_basenames_without_private_names(tmp_path):
    manifest, _doc = _source_manifest(tmp_path)
    first = tmp_path / "first" / "LICENSE"
    second = tmp_path / "second" / "LICENSE"
    _write(first, "License A\n")
    _write(second, "License B\n")

    build_studio_runtime_payload(
        manifest, tmp_path / "payload", license_notice_paths=[first, second]
    )

    notice_names = sorted(
        path.name for path in (tmp_path / "payload" / LICENSE_DESTINATION).iterdir()
    )
    assert notice_names == ["02-LICENSE", "LICENSE"]
    assert "first" not in json.dumps(notice_names)
    assert "second" not in json.dumps(notice_names)


def test_payload_builder_rejects_hash_drift_and_wrong_engine_identity(tmp_path):
    manifest, doc = _source_manifest(tmp_path)
    doc["accountable_surface"]["file_hashes"]["accountable_surface/effector.py"] = "0" * 64
    manifest.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(RuntimeError, match="hash mismatch"):
        build_studio_runtime_payload(
            manifest, tmp_path / "bad-hash", license_notice_paths=[_license(tmp_path)]
        )

    manifest, doc = _source_manifest(tmp_path / "identity")
    engine_root = Path(doc["studio_engine"]["root"])
    _write(
        engine_root / "pyproject.toml",
        "[project]\nname = 'wrong-engine'\ndependencies = ['studio-engine']\n",
    )
    doc["studio_engine"]["required_file_hashes"]["pyproject.toml"] = _sha(
        engine_root / "pyproject.toml"
    )
    manifest.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(RuntimeError, match="project.name"):
        build_studio_runtime_payload(
            manifest,
            tmp_path / "wrong-identity",
            license_notice_paths=[_license(tmp_path)],
        )


def test_payload_builder_rejects_unknown_manifest_fields_before_packaging(tmp_path):
    manifest, doc = _source_manifest(tmp_path)
    doc["private_debug_path"] = "C:/dev/private"
    doc["studio_engine"]["debug_path"] = "C:/dev/private"
    manifest.write_text(json.dumps(doc), encoding="utf-8")

    with pytest.raises(RuntimeError, match="unsupported manifest field"):
        build_studio_runtime_payload(
            manifest, tmp_path / "payload", license_notice_paths=[_license(tmp_path)]
        )


@pytest.mark.parametrize(
    "bad_path",
    [
        "C:/dev/outside.py",
        "/outside.py",
        "studio_engine/./engine.py",
        "studio_engine/\nengine.py",
        ".",
    ],
)
def test_payload_builder_rejects_drive_control_dot_and_absolute_paths(tmp_path, bad_path):
    manifest, doc = _source_manifest(tmp_path)
    doc["studio_engine"]["required_files"][1] = bad_path
    doc["studio_engine"]["required_file_hashes"][bad_path] = "0" * 64
    manifest.write_text(json.dumps(doc), encoding="utf-8")

    with pytest.raises(RuntimeError, match="must stay relative"):
        build_studio_runtime_payload(
            manifest, tmp_path / "payload", license_notice_paths=[_license(tmp_path)]
        )


def test_payload_and_pyinstaller_inputs_fail_for_missing_required_payloads(tmp_path):
    manifest, _doc = _source_manifest(tmp_path)
    with pytest.raises(RuntimeError, match="license notice"):
        build_studio_runtime_payload(manifest, tmp_path / "payload", license_notice_paths=[])

    with pytest.raises(RuntimeError, match=STUDIO_RUNTIME_PAYLOAD_ENV):
        pyinstaller_studio_runtime_inputs(
            Path.cwd(), env={STUDIO_RUNTIME_MANIFEST_ENV: str(manifest)}
        )

    payload = tmp_path / "payload"
    build_studio_runtime_payload(
        manifest, payload, license_notice_paths=[_license(tmp_path)]
    )
    (payload / "harness/studio_engine_bundle/studio_engine/engine.py").unlink()
    with pytest.raises(RuntimeError, match="payload missing"):
        pyinstaller_studio_runtime_inputs(
            Path.cwd(),
            env={
                STUDIO_RUNTIME_MANIFEST_ENV: str(manifest),
                STUDIO_RUNTIME_PAYLOAD_ENV: str(payload),
            },
        )


def test_pyinstaller_inputs_match_runtime_layout_and_hidden_import_closure(tmp_path):
    manifest, _doc = _source_manifest(tmp_path)
    payload = tmp_path / "payload"
    build_studio_runtime_payload(
        manifest, payload, license_notice_paths=[_license(tmp_path)]
    )

    inputs = pyinstaller_studio_runtime_inputs(
        Path.cwd(),
        env={
            STUDIO_RUNTIME_MANIFEST_ENV: str(manifest),
            STUDIO_RUNTIME_PAYLOAD_ENV: str(payload),
        },
    )

    assert str(payload / PYTHON_RUNTIME_DIR) in inputs.pathex
    assert (
        str(payload / "harness/studio_engine_bundle/studio_engine/engine.py"),
        "harness/studio_engine_bundle/studio_engine",
    ) in inputs.datas
    assert (
        str(payload / PAYLOAD_MANIFEST_DESTINATION),
        "packaging/studio-body",
    ) in inputs.datas
    assert (
        str(payload / LICENSE_DESTINATION / "THIRD-PARTY-NOTICES.txt"),
        "licenses/studio-runtime",
    ) in inputs.datas
    assert "harness.studio_body_route" in inputs.hiddenimports
    assert "accountable_surface.remote_durable" in inputs.hiddenimports
    assert "coherence_membrane.organs.web" in inputs.hiddenimports
    assert "proof_surface.authorization_receipt" in inputs.hiddenimports
    assert not any(name.startswith("studio_engine") for name in inputs.hiddenimports)


def test_gateway_spec_is_wired_to_the_studio_runtime_payload_contract():
    spec = Path("packaging/flywheel-gateway.spec").read_text(encoding="utf-8")
    assert "pyinstaller_studio_runtime_inputs(repo)" in spec
    assert "*studio_runtime.datas" in spec
    assert "*studio_runtime.pathex" in spec
    assert "*studio_runtime.hiddenimports" in spec
