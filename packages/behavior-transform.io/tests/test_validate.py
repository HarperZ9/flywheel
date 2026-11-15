import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from validate import validate, ValidationReport


def test_validate_clean_text():
    report = validate("clean text about software development")
    assert isinstance(report, ValidationReport)
    assert report.category_count == 0
    assert not report.pipeline_blocked
    assert report.pressure_label == "CLEAN"


def test_validate_returns_input_stats():
    text = "hello world"
    report = validate(text)
    assert report.input_chars == len(text)
    assert report.input_tokens_est > 0


def test_validate_to_dict():
    report = validate("clean text")
    d = report.to_dict()
    assert "input" in d
    assert "categories" in d
    assert "substitutions" in d
    assert "modulation" in d
    assert "pipeline" in d
    assert "optimization" in d


def test_validate_to_json():
    report = validate("clean text")
    j = report.to_json()
    import json
    parsed = json.loads(j)
    assert parsed["pipeline"]["blocked"] is False


def test_validate_summary():
    report = validate("clean text")
    s = report.summary()
    assert isinstance(s, str)
    assert "Input:" in s
    assert "Categories:" in s
    assert "Pipeline:" in s


def test_validate_optimization_short_text():
    report = validate("short")
    assert report.optimization_beneficial is False
    assert report.optimization_level == "unchanged"
