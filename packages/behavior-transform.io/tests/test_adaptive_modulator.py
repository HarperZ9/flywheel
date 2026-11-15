import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import json
import pytest

from adaptive_modulator import (
    normalize_obfuscation,
    analyze_density,
    adaptive_modulate,
    AdaptiveLayer,
    AdaptiveResult,
    DensityProfile,
    _LEET_MAP,
    _HOMOGLYPH_MAP,
)


# --- Obfuscation normalization tests ---

def test_normalize_zero_width():
    text = "hel​lo‌world"
    result, changes = normalize_obfuscation(text)
    assert "​" not in result
    assert "‌" not in result
    assert changes >= 2


def test_normalize_homoglyphs():
    text = "аео"  # Cyrillic а, е, о
    result, changes = normalize_obfuscation(text)
    assert result == "aeo"
    assert changes == 3


def test_normalize_leetspeak():
    text = "h4ck3r"
    result, changes = normalize_obfuscation(text)
    assert result == "hacker"
    assert changes >= 2


def test_normalize_leetspeak_no_context():
    text = "price is $5"
    result, changes = normalize_obfuscation(text)
    # $ not between alpha chars, so no change
    assert "$" in result or "s" in result


def test_normalize_spacing_dots():
    text = "h.a.c.k"
    result, changes = normalize_obfuscation(text)
    assert result == "hack"
    assert changes >= 3


def test_normalize_clean_text():
    text = "this is clean normal text"
    result, changes = normalize_obfuscation(text)
    assert result == text
    assert changes == 0


def test_normalize_mixed_obfuscation():
    text = "3x​pl0it"
    result, changes = normalize_obfuscation(text)
    assert "​" not in result
    assert changes >= 2


# --- Density analysis tests ---

def test_density_empty():
    profile = analyze_density("")
    assert profile.total_tokens == 0
    assert profile.escalation_level == 0


def test_density_clean():
    profile = analyze_density("the weather is sunny and warm today")
    assert profile.escalation_level == 0
    assert profile.sensitive_tokens == 0


def test_density_moderate():
    text = "the exploit payload uses credential injection to bypass the firewall"
    profile = analyze_density(text)
    assert profile.sensitive_tokens >= 3
    assert profile.escalation_level >= 1


def test_density_high():
    text = "exploit payload inject bypass credential privilege escalation lateral persist"
    profile = analyze_density(text)
    assert profile.density_ratio >= 0.15
    assert profile.escalation_level == 3
    assert profile.needs_deep_pass is True


def test_density_profile_fields():
    profile = DensityProfile(total_tokens=10, sensitive_tokens=2, density_ratio=0.2, escalation_level=2)
    assert profile.needs_deep_pass is True


# --- Adaptive modulation tests ---

def test_adaptive_modulate_clean():
    result = adaptive_modulate("the weather is sunny today")
    assert isinstance(result, AdaptiveResult)
    assert result.obfuscation_detected is False
    assert result.total_passes >= 1


def test_adaptive_modulate_with_obfuscation():
    result = adaptive_modulate("h4ck​er t00l")
    assert result.obfuscation_detected is True
    assert "​" not in result.normalized


def test_adaptive_modulate_max_passes():
    result = adaptive_modulate("clean text", max_passes=1)
    assert result.total_passes == 1


def test_adaptive_modulate_convergence():
    result = adaptive_modulate("simple clean text about software", max_passes=5)
    # Clean text should converge on first pass
    assert result.layers[-1].converged is True


def test_adaptive_result_to_dict():
    result = adaptive_modulate("test text")
    d = result.to_dict()
    assert "original" in d
    assert "normalized" in d
    assert "modulated" in d
    assert "density" in d
    assert "layers" in d
    assert d["density"]["escalation_level"] >= 0


def test_adaptive_result_changed_property():
    result = adaptive_modulate("clean text")
    assert isinstance(result.changed, bool)


def test_adaptive_layer_fields():
    layer = AdaptiveLayer(pass_number=1, changes=5, obfuscation_normalized=2, density_level=1, converged=False)
    assert layer.pass_number == 1
    assert layer.changes == 5
    assert layer.converged is False


def test_leet_map_coverage():
    assert "0" in _LEET_MAP
    assert "3" in _LEET_MAP
    assert "@" in _LEET_MAP
    assert "$" in _LEET_MAP


def test_homoglyph_map_coverage():
    assert "а" in _HOMOGLYPH_MAP  # Cyrillic a
    assert "​" in _HOMOGLYPH_MAP  # zero-width space
