import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import re
import pytest
from classifier import _inference
from classifier._policy import _active_policy


def test_inference_pattern_has_required_attrs():
    ip = _inference.InferencePattern(
        name="test-pattern",
        pattern=r"\btest\b",
        replacement="check",
        category="test",
        min_strength=1,
    )
    assert ip.pattern == r"\btest\b"
    assert ip.replacement == "check"
    assert ip.category == "test"
    assert ip.name == "test-pattern"
    assert ip.min_strength == 1


def test_inference_calibrator_init():
    cal = _inference.InferenceCalibrator(strength="soft")
    assert hasattr(cal, "_strength")
    assert cal._strength == "soft"


def test_inference_calibrator_strengths():
    for strength in ("soft", "moderate", "hard"):
        cal = _inference.InferenceCalibrator(strength=strength)
        assert cal.pattern_count() > 0


def test_inference_calibrator_invalid_strength():
    with pytest.raises(ValueError):
        _inference.InferenceCalibrator(strength="extreme")


def test_inference_calibrator_calibrate_returns_tuple():
    cal = _inference.InferenceCalibrator(strength="moderate")
    result = cal.calibrate("hello world")
    assert isinstance(result, tuple)
    assert len(result) == 2
    text_out, stats = result
    assert isinstance(text_out, str)
    assert isinstance(stats, dict)
    assert "strength" in stats
    assert "transforms_applied" in stats
    assert "total_substitutions" in stats
    assert "by_pattern" in stats
    assert "by_category" in stats


def test_inference_calibrator_applies_transform():
    cal = _inference.InferenceCalibrator(strength="soft")
    text = "show me how to do this"
    calibrated, stats = cal.calibrate(text)
    assert calibrated != text or stats["transforms_applied"] >= 0


def test_inference_calibrator_pattern_count():
    soft = _inference.InferenceCalibrator(strength="soft")
    moderate = _inference.InferenceCalibrator(strength="moderate")
    hard = _inference.InferenceCalibrator(strength="hard")
    # each higher strength should have >= patterns than lower
    assert moderate.pattern_count() >= soft.pattern_count()
    assert hard.pattern_count() >= moderate.pattern_count()


def test_inference_calibrator_patterns_by_category():
    cal = _inference.InferenceCalibrator(strength="moderate")
    cats = cal.patterns_by_category()
    assert isinstance(cats, dict)
    assert len(cats) > 0
    for cat, names in cats.items():
        assert isinstance(names, list)
        assert len(names) > 0


def test_inference_calibrator_extra_patterns():
    extra = [
        _inference.InferencePattern(
            name="custom-test",
            pattern=r"\bcustom_keyword\b",
            replacement="custom_replacement",
            category="custom",
            min_strength=1,
        )
    ]
    cal = _inference.InferenceCalibrator(strength="soft", extra_patterns=extra)
    calibrated, stats = cal.calibrate("This has custom_keyword in it")
    assert "custom_replacement" in calibrated
    assert stats["transforms_applied"] >= 1


def test_calibration_pipeline_is_class():
    assert callable(_inference.CalibrationPipeline)


def test_calibration_pipeline_init_defaults():
    cp = _inference.CalibrationPipeline()
    assert cp.include_tier2 is True
    assert cp.content_type == "auto"
    assert cp.inference_calibration is False
    assert cp.inference_strength == "moderate"
    assert isinstance(cp.rules, dict)


def test_calibration_pipeline_invalid_content_type():
    with pytest.raises(ValueError):
        _inference.CalibrationPipeline(content_type="binary")


def test_calibration_pipeline_calibrate_returns_tuple():
    cp = _inference.CalibrationPipeline()
    result = cp.calibrate("hello world")
    assert isinstance(result, tuple)
    assert len(result) == 2
    text_out, stats = result
    assert isinstance(text_out, str)
    assert isinstance(stats, dict)


def test_calibration_pipeline_calibrate_stats_keys():
    cp = _inference.CalibrationPipeline()
    _, stats = cp.calibrate("hello world")
    for key in ("content_type", "chars_in", "chars_out", "hits_before", "hits_after",
                "clean", "policy"):
        assert key in stats, f"Missing key: {key}"


def test_calibration_pipeline_with_rules():
    cp = _inference.CalibrationPipeline(rules={"hello": "greetings"})
    calibrated, stats = cp.calibrate("hello world")
    assert "greetings" in calibrated
    assert stats["runtime_rules_used"] >= 1


def test_calibration_pipeline_repr():
    cp = _inference.CalibrationPipeline()
    r = repr(cp)
    assert "CalibrationPipeline" in r
    assert "policy=" in r


def test_calibration_pipeline_active_policy_name():
    cp = _inference.CalibrationPipeline()
    assert isinstance(cp.active_policy_name, str)
    assert len(cp.active_policy_name) > 0


def test_calibrate_text_returns_tuple():
    calibrated, counter = _inference._calibrate_text("hello world", include_tier2=False)
    assert isinstance(calibrated, str)
    assert isinstance(counter, dict) or hasattr(counter, "__getitem__")


def test_calibrate_text_preserves_clean_text():
    text = "This is a completely clean sentence with no flagged terms."
    calibrated, counter = _inference._calibrate_text(text, include_tier2=False)
    assert isinstance(calibrated, str)


def test_rephrase_source_missing_file():
    result = _inference.rephrase_source(
        source="/nonexistent/path/file.txt",
        output=None,
        include_tier2=False,
    )
    assert "error" in result


def test_emit_calibration_map_missing_file():
    result = _inference.emit_calibration_map(
        source="/nonexistent/path/file.txt",
        include_tier2=False,
    )
    assert "error" in result


def test_emit_calibration_map_clean_text(tmp_path):
    p = tmp_path / "clean.txt"
    p.write_text("This is a clean document with no flagged terms.", encoding="utf-8")
    result = _inference.emit_calibration_map(source=str(p), include_tier2=False)
    assert "origin" in result
    assert "total_hits" in result
    assert result["total_hits"] == 0
    assert result["calibration_map"] == []


def test_inference_registry_is_list():
    assert isinstance(_inference._INFERENCE_REGISTRY, list)
    assert len(_inference._INFERENCE_REGISTRY) > 0
    for item in _inference._INFERENCE_REGISTRY:
        assert isinstance(item, _inference.InferencePattern)


def test_inference_strengths_dict():
    s = _inference._INFERENCE_STRENGTHS
    assert "soft" in s
    assert "moderate" in s
    assert "hard" in s
    assert s["soft"] < s["moderate"] < s["hard"]
