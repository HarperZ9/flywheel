import json

from harness.studio_body_engine_resolution import REQUIRED_STUDIO_ENGINE_FILES


def test_runtime_manifest_lists_engine_files_and_accountable_dependency_closure(tmp_path):
    from harness.studio_body_runtime_manifest import build_studio_body_runtime_manifest

    engine = tmp_path / "engine"
    for rel in REQUIRED_STUDIO_ENGINE_FILES:
        path = engine / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[project]\nname = \"studio-engine\"\n" if rel == "pyproject.toml" else "# engine\n",
                        encoding="utf-8")

    src = tmp_path / "accountable" / "src"
    pkg = src / "accountable_surface"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "remote_actuation.py").write_text(
        "from .remote_durable import run_authorized_remote_actuation\n",
        encoding="utf-8")
    (pkg / "remote_durable.py").write_text(
        "from accountable_surface.effector import RefusedActuation\n"
        "from coherence_membrane.certificate import Certificate\n",
        encoding="utf-8")
    (pkg / "effector.py").write_text("class RefusedActuation(Exception): pass\n",
                                     encoding="utf-8")
    proof = tmp_path / "proof" / "src"
    proof_pkg = proof / "proof_surface"
    proof_pkg.mkdir(parents=True)
    (proof_pkg / "__init__.py").write_text(
        "from .pre_execution_gate import evaluate_gate\n", encoding="utf-8")
    (proof_pkg / "pre_execution_gate.py").write_text(
        "from ._validate import Issue\n\ndef evaluate_gate(request): return None\n",
        encoding="utf-8")
    (proof_pkg / "_validate.py").write_text("class Issue: pass\n", encoding="utf-8")

    membrane = tmp_path / "membrane" / "src"
    membrane_pkg = membrane / "coherence_membrane"
    membrane_pkg.mkdir(parents=True)
    (membrane_pkg / "certificate.py").write_text(
        "from .composition import compose\nclass Certificate: pass\n", encoding="utf-8")
    (membrane_pkg / "composition.py").write_text("def compose(): pass\n", encoding="utf-8")

    doc = build_studio_body_runtime_manifest(
        studio_engine_src=engine,
        accountable_surface_src=src,
        coherence_membrane_src=membrane,
        proof_surface_src=proof,
        created_at="2026-09-15T13:00:00Z",
    )

    assert doc["schema"] == "flywheel.studio-body-runtime-manifest/v1"
    assert doc["studio_engine"]["required_files"] == list(REQUIRED_STUDIO_ENGINE_FILES)
    assert doc["studio_engine"]["status"] == "ready"
    assert doc["accountable_surface"]["files"] == [
        "accountable_surface/effector.py",
        "accountable_surface/remote_actuation.py",
        "accountable_surface/remote_durable.py",
    ]
    assert doc["proof_surface"]["files"] == [
        "proof_surface/__init__.py",
        "proof_surface/_validate.py",
        "proof_surface/pre_execution_gate.py",
    ]
    assert doc["coherence_membrane"]["files"] == [
        "coherence_membrane/certificate.py", "coherence_membrane/composition.py",
    ]
    assert doc["packaging_actions"][0]["action"] == "install_studio_engine_wheel"
    assert doc["packaging_actions"][1]["action"] == "copy_studio_engine_runtime"
    assert "C:/dev" not in json.dumps(doc)
