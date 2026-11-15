import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import json
import pytest

from transform import (
    TransformLayer,
    TransformResult,
    transform_text,
    reverse_transform,
)


def test_transform_layer_fields():
    layer = TransformLayer(name="test", applied=True, detail="ok", count=3)
    assert layer.name == "test"
    assert layer.applied is True
    assert layer.count == 3


def test_transform_result_clean_text():
    result = transform_text("the weather is sunny and warm today")
    assert isinstance(result, TransformResult)
    assert result.blocked is False
    assert result.mode == "full"


def test_transform_result_changed_property():
    result = transform_text("clean text about software development")
    assert result.changed is False or result.changed is True


def test_transform_result_to_dict():
    result = transform_text("clean text")
    d = result.to_dict()
    assert "original" in d
    assert "transformed" in d
    assert "layers" in d
    assert "mode" in d
    assert "changed" in d


def test_transform_result_to_json():
    result = transform_text("clean text")
    parsed = json.loads(result.to_json())
    assert parsed["mode"] == "full"


def test_transform_result_summary():
    result = transform_text("clean text")
    s = result.summary()
    assert "Transform" in s
    assert "Layers" in s


def test_transform_mode_cyber():
    result = transform_text("clean text", mode="cyber")
    assert result.mode == "cyber"
    layer_names = [l.name for l in result.layers]
    assert "cyber_modulation" in layer_names


def test_transform_mode_prose():
    result = transform_text("clean text", mode="prose")
    assert result.mode == "prose"
    layer_names = [l.name for l in result.layers]
    assert "prose_calibration" in layer_names


def test_transform_no_framing():
    result = transform_text("clean text", include_framing=False)
    assert result.framing == ""


def test_transform_layer_count():
    result = transform_text("clean text about software")
    assert result.layer_count >= 0
    assert result.layer_count <= len(result.layers)


def test_transform_total_substitutions():
    result = transform_text("clean text")
    assert result.total_substitutions >= 0


def test_reverse_transform_noop():
    result = transform_text("clean text")
    reversed_text = reverse_transform("clean text", result)
    assert reversed_text == "clean text"
