import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_engine_facade_does_not_export_private_default_path():
    from harness import studio_body_engine

    assert "DEFAULT_ENGINE_SRC" not in studio_body_engine.__all__
    assert not hasattr(studio_body_engine, "DEFAULT_ENGINE_SRC")


def test_missing_runtime_is_typed_unavailable_without_private_path_default():
    from harness.studio_body_engine_resolution import (
        StudioEngineUnavailable,
        resolve_studio_engine_runtime,
    )

    with pytest.raises(StudioEngineUnavailable) as caught:
        resolve_studio_engine_runtime(env={}, bundled_roots=(), installed_roots=())

    assert caught.value.code == "studio_engine_unavailable"
    assert "C:/dev" not in str(caught.value)
    assert "studio-engine-accepted-read" not in str(caught.value)


def test_explicit_engine_src_override_is_validated(tmp_path):
    from harness.studio_body_engine_resolution import (
        StudioEngineUnavailable,
        resolve_studio_engine_runtime,
    )

    partial = tmp_path / "partial-engine"
    (partial / "studio_engine").mkdir(parents=True)
    (partial / "studio_engine" / "engine.py").write_text("# partial\n", encoding="utf-8")

    with pytest.raises(StudioEngineUnavailable) as caught:
        resolve_studio_engine_runtime(
            env={"STUDIO_ENGINE_SRC": str(partial)}, bundled_roots=(), installed_roots=())

    assert caught.value.code == "studio_engine_incomplete"
    assert "missing required Studio Engine runtime file" in str(caught.value)


def test_valid_source_override_returns_manifest_without_local_default(tmp_path):
    from harness.studio_body_engine_resolution import (
        REQUIRED_STUDIO_ENGINE_FILES,
        resolve_studio_engine_runtime,
        studio_engine_runtime_manifest,
    )

    root = tmp_path / "engine"
    for rel in REQUIRED_STUDIO_ENGINE_FILES:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        text = _engine_fixture_text(rel)
        path.write_text(text, encoding="utf-8")

    runtime = resolve_studio_engine_runtime(
        env={"STUDIO_ENGINE_SRC": str(root)}, bundled_roots=(), installed_roots=())
    manifest = studio_engine_runtime_manifest(runtime)

    assert runtime.root == root.resolve()
    assert runtime.basis == "env:STUDIO_ENGINE_SRC"
    assert manifest["schema"] == "flywheel.studio-engine-runtime-resolution/v1"
    assert manifest["basis"] == "env:STUDIO_ENGINE_SRC"
    assert manifest["required_files"] == list(REQUIRED_STUDIO_ENGINE_FILES)
    assert "studio-engine-accepted-read" not in str(manifest)


def test_source_identity_rejects_wrong_project_name_with_studio_engine_mentions(tmp_path):
    from harness.studio_body_engine_resolution import (
        REQUIRED_STUDIO_ENGINE_FILES,
        StudioEngineUnavailable,
        resolve_studio_engine_runtime,
    )

    root = tmp_path / "wrong-engine"
    for rel in REQUIRED_STUDIO_ENGINE_FILES:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            """[project]
name = "wrong-engine"
dependencies = ["studio-engine"]
description = "mentions studio-engine but is not it"
# studio-engine appears only outside project.name
""" if rel == "pyproject.toml" else "# fixture\n",
            encoding="utf-8",
        )

    with pytest.raises(StudioEngineUnavailable) as caught:
        resolve_studio_engine_runtime(
            env={"STUDIO_ENGINE_SRC": str(root)}, bundled_roots=(), installed_roots=())

    assert caught.value.code == "studio_engine_identity_mismatch"


def test_installed_wheel_layout_resolves_without_source_env(tmp_path, monkeypatch):
    accepted = os.environ.get("STUDIO_ENGINE_SRC")
    if not accepted:
        pytest.skip("STUDIO_ENGINE_SRC not configured for installed-wheel layout control")
    wheelhouse = tmp_path / "wheelhouse"
    target = tmp_path / "install"
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", accepted, "-w", str(wheelhouse),
         "--no-deps", "--no-input"],
        check=True, capture_output=True, text=True, timeout=60,
    )
    wheel = next(wheelhouse.glob("studio_engine-*.whl"))
    subprocess.run(
        [sys.executable, "-m", "pip", "install", str(wheel), "--target", str(target),
         "--no-deps", "--no-input"],
        check=True, capture_output=True, text=True, timeout=60,
    )
    monkeypatch.syspath_prepend(str(target))

    from harness.studio_body_engine_resolution import (
        REQUIRED_STUDIO_ENGINE_INSTALLED_FILES,
        resolve_studio_engine_runtime,
        studio_engine_runtime_manifest,
    )

    runtime = resolve_studio_engine_runtime(env={}, bundled_roots=(), installed_roots=None)
    manifest = studio_engine_runtime_manifest(runtime)

    assert runtime.basis == "installed:studio-engine"
    assert runtime.package_version == "0.2.0"
    assert (runtime.root / "studio_engine" / "engine.py").is_file()
    assert not (runtime.root / "pyproject.toml").exists()
    assert manifest["required_files"] == list(REQUIRED_STUDIO_ENGINE_INSTALLED_FILES)


def _engine_fixture_text(rel: str) -> str:
    return "[project]\nname = \"studio-engine\"\n" if rel == "pyproject.toml" else "# fixture\n"


def test_engine_bridge_tests_do_not_pin_private_checkout_paths():
    for rel in (
        "tests/test_studio_body_engine_bridge.py",
        "tests/test_studio_body_screen_feedback.py",
    ):
        text = Path(rel).read_text(encoding="utf-8")
        assert "Path(\"C:/dev\")" not in text
        assert "studio-engine-accepted-read" not in text
        assert "accountable-surface-accepted-read" not in text


def test_engine_unavailable_maps_to_service_unavailable_status():
    from harness.studio_body_route_status import body_step_status

    status, code = body_step_status(
        False,
        {"decision": "deny"},
        ["the effector refused the plan before acting: studio_engine_unavailable: missing"],
    )

    assert status == "studio_engine_unavailable"
    assert code == 503
