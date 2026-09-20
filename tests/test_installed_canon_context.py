import json
import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import check_installed_canon_context as installed

PIN = "8c6a8228ce2117112c5dad74ddb0450ba80aa8ff"
COMMIT = "a" * 40
VERSION = "1.0.0"


def make_install(tmp_path: Path, data: bytes = b"engine"):
    root = tmp_path / "Programs" / "Flywheel"
    engine = root / "engine" / "flywheel-gateway.exe"
    engine.parent.mkdir(parents=True)
    engine.write_bytes(data)
    return root, engine, sha256(data).hexdigest()


def make_install_at(root: Path, data: bytes = b"engine"):
    engine = root / "engine" / "flywheel-gateway.exe"
    engine.parent.mkdir(parents=True)
    engine.write_bytes(data)
    return engine, sha256(data).hexdigest()


def run_checker(tmp_path: Path, monkeypatch, checker, *, root=None, sha=None):
    if root is None:
        root, _engine, real_sha = make_install(tmp_path)
    else:
        real_sha = sha or "0" * 64
    receipt = tmp_path / "receipt.json"
    monkeypatch.setattr(installed.check_frozen_gateway, "check", checker)
    code = installed.main([
        "--install-root", str(root),
        "--expected-version", VERSION,
        "--expected-engine-sha256", sha or real_sha,
        "--source-commit", COMMIT,
        "--receipt", str(receipt),
    ])
    return code, json.loads(receipt.read_text(encoding="utf-8")), receipt


def symlink_dir(target: Path, link: Path):
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink unavailable: {exc}")


def fill_success(receipt: dict, *, version: str = VERSION):
    receipt.update({
        "schema": "flywheel.frozen-gateway-smoke/v1",
        "version": version,
        "owned_process_terminal": True,
        "isolated_runtime_removed": True,
        "canon_context_payload": {
            "schema": "flywheel.frozen-canon-context-payload/v1",
            "owner_commit": PIN,
            "source_manifest_sha256": "sha256:" + "1" * 64,
            "license_sha256": "sha256:" + "2" * 64,
            "license_present": True,
            "license_path": "python-lane-payloads/canon/licenses/LICENSE",
        },
        "context_memory_acceptance": {
            "schema": "flywheel.frozen-context-memory-smoke/v1",
            "capture_status": "stored",
            "preflight_status": "found_in_searched_sources",
            "hit_count": 1,
            "denied_project_code": "CONTEXT_SCOPE_NOT_BOUND",
            "denied_owner_code": "CONTEXT_OWNER_NOT_BOUND",
            "tampered_evidence_code": "CANON_CONTEXT_TOOL_ERROR",
            "destination_binding_checked": True,
            "canon_store_id_bound": "ctxstore_" + "6" * 32,
            "event_record_id": "context-event-" + "3" * 64,
            "source_hash": "4" * 64,
            "owner_ref_bound": "owner_" + "5" * 32,
        },
    })


def test_direct_script_help_imports_from_outside_checkout_without_pythonpath(tmp_path):
    env = {
        key: value for key, value in os.environ.items()
        if key.upper() not in {"PYTHONPATH", "PYTHONHOME"}
    }

    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_installed_canon_context.py"), "--help"],
        cwd=tmp_path, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )

    assert completed.returncode == 0, completed.stderr
    assert "usage:" in completed.stdout


def test_wrong_expected_engine_hash_fails_before_smoke_and_does_not_call_checker(tmp_path, monkeypatch):
    root, _engine, _real_sha = make_install(tmp_path)

    def checker(*_args):
        raise AssertionError("checker should not run")

    code, receipt, _path = run_checker(tmp_path, monkeypatch, checker, root=root, sha="0" * 64)

    assert code == 1
    assert receipt["verdict"] == "HOLD"
    assert receipt["failure"]["code"] == "ENGINE_SHA256_MISMATCH_BEFORE"


def test_engine_symlink_escape_is_rejected_before_smoke(tmp_path, monkeypatch):
    root = tmp_path / "Programs" / "Flywheel"
    engine = root / "engine" / "flywheel-gateway.exe"
    outside = tmp_path / "outside.exe"
    engine.parent.mkdir(parents=True)
    outside.write_bytes(b"outside")
    try:
        os.symlink(outside, engine)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    def checker(*_args):
        raise AssertionError("checker should not run")

    code, receipt, _path = run_checker(
        tmp_path, monkeypatch, checker, root=root, sha=sha256(outside.read_bytes()).hexdigest())

    assert code == 1
    assert receipt["failure"]["code"] in {"ENGINE_REPARSE_POINT", "ENGINE_PATH_ESCAPE"}


def test_install_root_symlink_redirect_is_rejected_before_smoke(tmp_path, monkeypatch):
    real_root = tmp_path / "actual" / "Flywheel"
    _engine, real_sha = make_install_at(real_root)
    link_root = tmp_path / "FlywheelLink"
    symlink_dir(real_root, link_root)

    def checker(*_args):
        raise AssertionError("checker should not run")

    code, receipt, _path = run_checker(tmp_path, monkeypatch, checker, root=link_root, sha=real_sha)

    assert code == 1
    assert receipt["failure"]["code"] == "INSTALL_ROOT_REPARSE_POINT"


def test_install_root_ancestor_symlink_redirect_is_rejected_before_smoke(tmp_path, monkeypatch):
    real_parent = tmp_path / "actual-programs"
    real_root = real_parent / "Flywheel"
    _engine, real_sha = make_install_at(real_root)
    link_parent = tmp_path / "ProgramsLink"
    symlink_dir(real_parent, link_parent)

    def checker(*_args):
        raise AssertionError("checker should not run")

    code, receipt, _path = run_checker(
        tmp_path, monkeypatch, checker, root=link_parent / "Flywheel", sha=real_sha)

    assert code == 1
    assert receipt["failure"]["code"] == "INSTALL_ROOT_REPARSE_POINT"


def test_omitted_context_result_fails(tmp_path, monkeypatch):
    def checker(_engine, _version, receipt):
        fill_success(receipt)
        receipt.pop("context_memory_acceptance")

    code, receipt, _path = run_checker(tmp_path, monkeypatch, checker)

    assert code == 1
    assert receipt["failure"]["code"] == "CONTEXT_RESULT_MISSING"


def test_malformed_context_result_fails(tmp_path, monkeypatch):
    def checker(_engine, _version, receipt):
        fill_success(receipt)
        receipt["context_memory_acceptance"]["tampered_evidence_code"] = "OK"

    code, receipt, _path = run_checker(tmp_path, monkeypatch, checker)

    assert code == 1
    assert receipt["failure"]["code"] == "CONTEXT_TAMPER_RESULT_MISSING"


def test_cleanup_failure_fails_receipt(tmp_path, monkeypatch):
    def checker(_engine, _version, receipt):
        fill_success(receipt)
        receipt["isolated_runtime_removed"] = False

    code, receipt, _path = run_checker(tmp_path, monkeypatch, checker)

    assert code == 1
    assert receipt["failure"]["code"] == "ISOLATED_RUNTIME_NOT_REMOVED"


def test_binary_changed_during_smoke_fails_after_smoke(tmp_path, monkeypatch):
    root, engine, real_sha = make_install(tmp_path)

    def checker(_engine, _version, receipt):
        fill_success(receipt)
        engine.write_bytes(b"changed")

    code, receipt, _path = run_checker(tmp_path, monkeypatch, checker, root=root, sha=real_sha)

    assert code == 1
    assert receipt["failure"]["code"] == "ENGINE_SHA256_CHANGED_DURING_SMOKE"


def test_arbitrary_exception_text_is_sanitized_from_outputs_and_receipt(tmp_path, monkeypatch, capsys):
    secret = "secret-token-from-exception"

    def checker(_engine, _version, _receipt):
        raise ValueError(f"boom {secret}")

    code, receipt, receipt_path = run_checker(tmp_path, monkeypatch, checker)
    captured = capsys.readouterr()
    combined = receipt_path.read_text(encoding="utf-8") + captured.out + captured.err

    assert code == 1
    assert receipt["failure"]["code"] == "ValueError"
    assert secret not in combined


@pytest.mark.parametrize("message", ["API_SECRET_ABC123", "HTTP_FAILURE:/private/token"])
def test_runtime_error_message_is_not_a_failure_code_or_output(tmp_path, monkeypatch, capsys, message):
    def checker(_engine, _version, _receipt):
        raise RuntimeError(message)

    code, receipt, receipt_path = run_checker(tmp_path, monkeypatch, checker)
    captured = capsys.readouterr()
    combined = receipt_path.read_text(encoding="utf-8") + captured.out + captured.err

    assert code == 1
    assert receipt["failure"]["code"] == "FROZEN_SMOKE_FAILED"
    assert message not in combined


def test_success_calls_checker_with_installed_engine_and_writes_bounded_receipt(tmp_path, monkeypatch):
    root, engine, real_sha = make_install(tmp_path)
    called = {}

    def checker(observed_engine, observed_version, receipt):
        called["engine"] = observed_engine
        called["version"] = observed_version
        fill_success(receipt)

    code, receipt, receipt_path = run_checker(tmp_path, monkeypatch, checker, root=root, sha=real_sha)
    text = receipt_path.read_text(encoding="utf-8")

    assert code == 0
    assert called == {"engine": engine.resolve(), "version": VERSION}
    assert receipt["schema"] == "flywheel.installed-canon-context-smoke/v1"
    assert receipt["verdict"] == "PASS"
    assert receipt["source"]["commit"] == COMMIT
    assert receipt["source"]["attestation"] == "caller-supplied"
    assert receipt["engine"]["sha256"] == real_sha
    assert receipt["engine"]["hash_verified_before_after"] is True
    assert receipt["canon"]["owner_commit"] == PIN
    assert receipt["context_memory"]["denied_owner_code"] == "CONTEXT_OWNER_NOT_BOUND"
    assert receipt["context_memory"]["owner_ref_bound_present"] is True
    assert receipt["context_memory"]["destination_binding_checked"] is True
    assert receipt["context_memory"]["canon_store_id_bound_present"] is True
    assert receipt["limits"]
    assert str(tmp_path) not in text
    assert not Path(receipt["canon"]["license_path"]).is_absolute()
