# CALIBRATED VIEW
# audit_counts: {}
#
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import pytest
import _core


def test_tools_path_default():
    p = _core.tools_path()
    assert p.is_dir()
    assert (p / "vocabulary_map.py").exists()


def test_tools_path_respects_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("BEHAVIOR_TRANSFORM_TOOLS", str(tmp_path))
    result = _core.tools_path()
    assert result == tmp_path


def test_tools_path_ignores_nonexistent_env_var(monkeypatch):
    monkeypatch.setenv("BEHAVIOR_TRANSFORM_TOOLS", "/nonexistent/path/xyz")
    p = _core.tools_path()
    assert p.is_dir()
    assert p != Path("/nonexistent/path/xyz")


def test_build_engine_returns_calibration_engine():
    _core._ENGINE = None
    engine = _core.build_engine()
    assert isinstance(engine, _core.CalibrationEngine)


def test_build_engine_returns_same_instance():
    _core._ENGINE = None
    e1 = _core.build_engine()
    e2 = _core.build_engine()
    assert e1 is e2


def test_engine_is_frozen():
    _core._ENGINE = None
    engine = _core.build_engine()
    with pytest.raises((TypeError, AttributeError)):
        engine.tier1_cals = ()  # type: ignore[misc]


def test_apply_returns_tuple_of_three():
    _core._ENGINE = None
    engine = _core.build_engine()
    result = engine.apply("hello world")
    assert isinstance(result, tuple)
    assert len(result) == 3
    text, t1, t2 = result
    assert isinstance(text, str)
    assert isinstance(t1, int)
    assert isinstance(t2, int)


def test_score_zero_for_clean_text():
    _core._ENGINE = None
    engine = _core.build_engine()
    score = engine.score("the quick brown fox jumps over the lazy dog")
    assert score == 0.0


def test_resolve_mode_returns_on_or_off():
    mode = _core.resolve_mode()
    assert mode in ("on", "off")


def test_score_positive_for_tier1_hit():
    _core._ENGINE = None
    engine = _core.build_engine()
    from vocabulary_map import by_severity
    t1 = by_severity("tier1")
    if not t1:
        pytest.skip("no tier1 calibrations defined")
    term = t1[0].original
    score = engine.score(term)
    assert score > 0.0
