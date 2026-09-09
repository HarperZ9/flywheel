from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from tests.enterprise_envs.package_helpers import PACKAGE_ROOT, ROOT, add_product_src, product_pythonpath


def test_product_metadata_requires_engine_release_that_contains_api():
    """Catches production dependency claims against flywheel-verify 0.6.0."""
    pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["name"] == "flywheel-env-service-desk-incident"
    assert "flywheel-verify>=0.6.1,<0.7" in pyproject["project"]["dependencies"]
    assert "service-desk-incident-env" in pyproject["project"]["scripts"]
    assert "service_desk_incident_env" in pyproject["tool"]["setuptools"]["package-data"]


def test_shared_engine_imports_without_product_and_compat_fails_typed(tmp_path):
    """Catches circular engine imports that require installing this product."""
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    engine = subprocess.run(
        [sys.executable, "-c", "import harness.enterprise_envs; import harness.enterprise_envs.digest; print('engine-ok')"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    compat = subprocess.run(
        [sys.executable, "-m", "harness.enterprise_envs.cli", "e2e", "service-desk-incident/v1", "--out", str(tmp_path / "out")],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )

    assert engine.returncode == 0, engine.stderr
    assert engine.stdout.strip() == "engine-ok"
    assert compat.returncode == 2
    doc = json.loads(compat.stdout)
    assert doc["error_code"] == "enterprise_environment_product_missing"
    assert doc["required_distribution"] == "flywheel-env-service-desk-incident"


def test_dedicated_product_api_and_cli_from_source(tmp_path):
    """Catches environment products that remain hidden behind the Flywheel module CLI."""
    add_product_src()
    from service_desk_incident_env import product

    identity = product.identity()
    assert identity["distribution"] == "flywheel-env-service-desk-incident"
    assert identity["engine_requirement"] == "flywheel-verify>=0.6.1,<0.7"

    env = {**os.environ, "PYTHONPATH": product_pythonpath()}
    descriptor = subprocess.run(
        [sys.executable, "-m", "service_desk_incident_env.cli", "descriptor", "--json"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    assert descriptor.returncode == 0, descriptor.stderr
    assert json.loads(descriptor.stdout)["environment_id"] == "service-desk-incident/v1"

    out = tmp_path / "source-cli"
    e2e = subprocess.run(
        [sys.executable, "-m", "service_desk_incident_env.cli", "e2e", "--out", str(out)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    assert e2e.returncode == 0, e2e.stderr
    packet = json.loads(e2e.stdout)
    verify = product.verify_artifacts(Path(packet["artifact_dir"]))
    assert verify["observed_state"] == "pass"


def test_product_verify_rejects_wrong_state_and_tampered_receipt(tmp_path):
    """Catches installed review flows that trust receipt text over recomputed state."""
    add_product_src()
    from service_desk_incident_env import product

    packet = product.run_e2e(tmp_path / "e2e")
    artifact_dir = Path(packet["artifact_dir"])

    wrong_state_dir = tmp_path / "wrong-state"
    shutil.copytree(artifact_dir, wrong_state_dir)
    after_path = wrong_state_dir / "domain-state-after.json"
    after = json.loads(after_path.read_text(encoding="utf-8"))
    for row in after["tables"]["incident"]:
        if row["number"] == "INC0010001":
            row["state"] = "Closed"
    after_path.write_text(json.dumps(after, sort_keys=True), encoding="utf-8")

    tampered_dir = tmp_path / "tampered-receipt"
    shutil.copytree(artifact_dir, tampered_dir)
    receipt_path = tampered_dir / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["run_receipt_sha256"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")

    wrong_state = product.verify_artifacts(wrong_state_dir)
    tampered = product.verify_artifacts(tampered_dir)
    assert wrong_state["observed_state"] == "fail"
    assert "target_incident_not_open" in wrong_state["failure_codes"]
    assert tampered["observed_state"] == "fail"
    assert "run_receipt_sha256_mismatch" in tampered["failure_codes"]


def test_installed_target_loads_package_data_and_module_cli(tmp_path):
    """Catches source-only products with missing package data after install."""
    install_target = tmp_path / "site"
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-build-isolation", "--no-deps", "--target", str(install_target), str(PACKAGE_ROOT)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr

    env = {**os.environ, "PYTHONPATH": product_pythonpath(install_target)}
    identity = subprocess.run(
        [sys.executable, "-m", "service_desk_incident_env.cli", "identity", "--json"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    assert identity.returncode == 0, identity.stderr
    doc = json.loads(identity.stdout)
    assert doc["distribution"] == "flywheel-env-service-desk-incident"
    assert doc["source_basis_manifest_sha256"]

    doctor = subprocess.run(
        [sys.executable, "-m", "service_desk_incident_env.cli", "doctor", "--out", str(tmp_path / "doctor"), "--json"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
    )
    assert doctor.returncode == 0, doctor.stderr
    doctor_doc = json.loads(doctor.stdout)
    assert doctor_doc["installed_artifact_verification"]["observed_state"] == "pass"
    assert doctor_doc["tamper_controls"]["wrong_state"]["observed_state"] == "fail"
    assert doctor_doc["tamper_controls"]["tampered_receipt"]["observed_state"] == "fail"
