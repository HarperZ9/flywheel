"""test_run_paths.py — the run-root default is portable, and the shipped harness
source carries no absolute build-machine path (the shipped-posture rule)."""
from pathlib import Path

from harness import run_paths


def test_env_var_wins(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", "/tmp/custom-run")
    assert run_paths.run_root_default() == "/tmp/custom-run"


def test_marker_file_used_when_no_env(monkeypatch, tmp_path):
    monkeypatch.delenv("FLYWHEEL_RUN_ROOT", raising=False)
    marker = tmp_path / ".flywheel-run-root"
    marker.write_text("E:/local-model-run\n", encoding="utf-8")
    monkeypatch.setattr(run_paths, "_MARKER", marker)
    assert run_paths.run_root_default() == "E:/local-model-run"


def test_portable_fallback_when_nothing_set(monkeypatch, tmp_path):
    monkeypatch.delenv("FLYWHEEL_RUN_ROOT", raising=False)
    monkeypatch.setattr(run_paths, "_MARKER", tmp_path / "does-not-exist")
    got = run_paths.run_root_default()
    assert got == str(Path.home() / ".flywheel" / "run")
    assert "E:/" not in got and "C:/dev" not in got     # no build-machine path


def test_no_local_path_literals_in_shipped_harness_source():
    """Falsifier for the shipped-posture rule: no absolute build-machine path may
    appear in any harness/*.py. Re-introduce a leak and this fails."""
    harness_dir = Path(run_paths.__file__).resolve().parent
    patterns = ("E:/local-model-run", "E:\\local-model-run", "C:/dev/", "C:\\dev\\")
    offenders = []
    for py in sorted(harness_dir.glob("*.py")):
        text = py.read_text(encoding="utf-8", errors="replace")
        for pat in patterns:
            if pat in text:
                offenders.append(f"{py.name}: {pat}")
    assert offenders == [], f"local-path leak in shipped source: {offenders}"
