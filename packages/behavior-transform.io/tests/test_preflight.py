import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import pytest


def test_preflight_imports():
    from preflight import (
        Capsule, Manifest, build_seal, verify_seal,
        write_receipt, read_latest_receipt,
        write_activation_state, project_root,
    )
    assert callable(build_seal)
    assert callable(verify_seal)
    assert callable(write_receipt)
    assert callable(write_activation_state)


def test_paths_project_root():
    from preflight.paths import project_root
    root = project_root()
    assert isinstance(root, Path)


def test_paths_seal_root():
    from preflight.paths import seal_root
    root = seal_root()
    assert isinstance(root, Path)


def test_paths_receipt_root():
    from preflight.paths import receipt_root
    root = receipt_root()
    assert isinstance(root, Path)


def test_seals_build_seal_callable():
    from preflight.seals import build_seal
    assert callable(build_seal)


def test_seals_verify_seal_callable():
    from preflight.seals import verify_seal
    assert callable(verify_seal)


def test_seals_build_and_verify(tmp_path):
    from preflight.seals import build_seal
    f1 = tmp_path / "src" / "warden_prefire" / "cli.py"
    f1.parent.mkdir(parents=True, exist_ok=True)
    f1.write_text("# placeholder")
    seal = build_seal(root=tmp_path)
    assert isinstance(seal, dict)
    assert "status" in seal
    assert "artifacts" in seal


def test_receipts_write_receipt(tmp_path):
    from preflight.receipts import write_receipt
    receipt_path = write_receipt(
        receipt_root=tmp_path,
        payload={"surface": "test", "status": "PASS"},
    )
    assert isinstance(receipt_path, Path)
    assert receipt_path.exists()


def test_receipts_read_latest(tmp_path):
    from preflight.receipts import write_receipt, read_latest_receipt
    write_receipt(
        receipt_root=tmp_path,
        payload={"surface": "test", "status": "PASS"},
    )
    latest = read_latest_receipt(receipt_root=tmp_path, surface="test")
    assert latest is not None
    assert latest["status"] == "PASS"


def test_activation_state_root(tmp_path):
    from preflight.activation import state_root
    result = state_root(tmp_path)
    assert isinstance(result, Path)


def test_manifest_class():
    from preflight.manifest import Manifest
    assert Manifest is not None


def test_capsule_class():
    from preflight.capsule import Capsule
    assert Capsule is not None


def test_audit_module():
    from preflight.audit import run_audit
    assert callable(run_audit)


def test_doctor_module():
    from preflight.doctor import run_doctor
    assert callable(run_doctor)


def test_bundle_module():
    from preflight.bundle import export_bundle
    assert callable(export_bundle)


def test_native_module():
    from preflight.native import resolve_native_command
    assert callable(resolve_native_command)


def test_meta_module():
    from preflight.meta import MetaContract
    assert MetaContract is not None


def test_runner_module():
    from preflight.runner import run_child, build_io_command
    assert callable(run_child)
    assert callable(build_io_command)


def test_launcher_module():
    from preflight.launcher import launch
    assert callable(launch)
