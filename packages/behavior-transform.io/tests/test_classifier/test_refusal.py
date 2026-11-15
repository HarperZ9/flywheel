import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import pytest
from classifier import _refusal
from classifier._policy import _active_policy


def test_refusal_probability_returns_float():
    policy = _active_policy()
    hits = []
    result = _refusal.refusal_probability(hits, 10)
    assert isinstance(result, float)
    assert 0.0 <= result <= 1.0


def test_refusal_probability_with_hits():
    hits = [{"severity": "tier1"}, {"severity": "tier2"}]
    result = _refusal.refusal_probability(hits, 50)
    assert isinstance(result, float)
    assert 0.0 <= result <= 1.0


def test_refusal_label_returns_str():
    label = _refusal._refusal_label(0.5)
    assert isinstance(label, str)


def test_refusal_label_negligible():
    assert _refusal._refusal_label(0.05) == "NEGLIGIBLE"


def test_refusal_label_low():
    assert _refusal._refusal_label(0.15) == "LOW"


def test_refusal_label_moderate():
    assert _refusal._refusal_label(0.35) == "MODERATE"


def test_refusal_label_high():
    assert _refusal._refusal_label(0.60) == "HIGH"


def test_refusal_label_critical():
    assert _refusal._refusal_label(0.90) == "CRITICAL"


def test_refusal_modulator_init():
    policy = _active_policy()
    mod = _refusal.RefusalModulator(target_prob=0.1, policy=policy)
    assert hasattr(mod, "target_prob")
    assert mod.target_prob == 0.1


def test_refusal_modulator_modulate_returns_dict():
    policy = _active_policy()
    mod = _refusal.RefusalModulator(target_prob=0.1, policy=policy)
    result = mod.modulate("hello world")
    assert isinstance(result, dict)
    assert "calibrated" in result
    assert "target_met" in result


def test_refusal_modulator_modulate_calibrated_is_str():
    policy = _active_policy()
    mod = _refusal.RefusalModulator(target_prob=0.1, policy=policy)
    result = mod.modulate("hello world")
    assert isinstance(result["calibrated"], str)


def test_refusal_modulator_estimate_returns_dict():
    policy = _active_policy()
    mod = _refusal.RefusalModulator(target_prob=0.1, policy=policy)
    result = mod.estimate("hello world")
    assert isinstance(result, dict)
    assert "probability" in result
    assert "label" in result


def test_refusal_manage_cmd_stdin_error():
    # supply a non-existent file path — should return error
    result = _refusal.refusal_manage_cmd(
        source="nonexistent_file_xyz123.md",
        output=None,
        target_prob=0.10,
        include_tier2=True,
        dry_run=True,
    )
    assert "error" in result