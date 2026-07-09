from pathlib import Path

from scripts.run_flywheel_integration_benchmark import run_spin_benchmark


def test_run_spin_benchmark_restores_original_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = Path.cwd()

    result = run_spin_benchmark(tmp_path / "bench", turns=1)

    assert result["schema"] == "flywheel.spin/integration/v1"
    assert Path.cwd() == before
