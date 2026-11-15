import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import pytest
from classifier import _analysis


def test_baseline_path_is_path():
    assert isinstance(_analysis._BASELINE_PATH, Path)


def test_budget_summary_returns_dict(tmp_path, monkeypatch):
    monkeypatch.setattr(_analysis, "_BASELINE_PATH", tmp_path / "baseline.json")
    args_paths = [tmp_path]
    result = _analysis.budget_summary(args_paths, include_tier2=False, threshold=30.0)
    assert isinstance(result, dict)
    assert "total_score" in result


def test_drift_report_returns_dict(tmp_path, monkeypatch):
    monkeypatch.setattr(_analysis, "_BASELINE_PATH", tmp_path / "baseline.json")
    args_paths = [tmp_path]
    result = _analysis.drift_report(args_paths, include_tier2=False)
    assert isinstance(result, dict)