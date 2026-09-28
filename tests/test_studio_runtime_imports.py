from pathlib import Path

import pytest

from scripts.studio_runtime_imports import verify_payload_imports


def test_missing_cross_package_dependency_fails_then_staged_dependency_loads(tmp_path, monkeypatch):
    runtime = tmp_path / "payload/studio_runtime_python"
    component = runtime / "actuator"
    component.mkdir(parents=True)
    (component / "__init__.py").write_text("from verifier.certificate import Certificate\n")
    outside = tmp_path / "developer/verifier"
    outside.mkdir(parents=True)
    (outside / "__init__.py").write_text("")
    (outside / "certificate.py").write_text("class Certificate: pass\n")
    monkeypatch.setenv("PYTHONPATH", str(outside.parent))
    with pytest.raises(RuntimeError, match="No module named 'verifier'"):
        verify_payload_imports(runtime.parent, ["actuator"])

    verifier = runtime / "verifier"
    verifier.mkdir()
    (verifier / "__init__.py").write_text("")
    (verifier / "certificate.py").write_text("class Certificate: pass\n")
    rows = verify_payload_imports(runtime.parent, ["actuator", "verifier.certificate"])
    assert [row["module"] for row in rows] == ["actuator", "verifier.certificate"]
    assert all(row["path"].startswith("studio_runtime_python/") for row in rows)
    assert not list(runtime.rglob("*.pyc"))


def test_modules_resolved_outside_payload_are_rejected(tmp_path):
    with pytest.raises(RuntimeError, match="import closure failed"):
        verify_payload_imports(tmp_path, ["json"])
