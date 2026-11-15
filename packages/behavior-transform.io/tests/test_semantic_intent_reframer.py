import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import pytest
from semantic_intent_reframer import reframe, IntentRewrite


def test_clean_text_unchanged():
    text = "the quick brown fox jumps over the lazy dog"
    result_text, rewrites = reframe(text)
    assert result_text == text
    assert rewrites == []


def test_reframe_returns_correct_types():
    result_text, rewrites = reframe("some text")
    assert isinstance(result_text, str)
    assert isinstance(rewrites, list)


def test_rewrite_namedtuple_fields():
    # Real trigger from positional pattern
    trigger = "every byte the model ingests"
    _, rewrites = reframe(trigger)
    assert len(rewrites) > 0, "Trigger should produce at least one rewrite"
    rw = rewrites[0]
    assert isinstance(rw.span, str)
    assert isinstance(rw.replacement, str)
    assert isinstance(rw.category, str)


def test_positional_signal_reframed():
    trigger = "every byte the model ingests"
    _, rewrites = reframe(trigger)
    assert len(rewrites) > 0, "Positional trigger should produce rewrites"
    assert any(r.category.startswith("positional") for r in rewrites), \
        f"Expected positional category, got {[r.category for r in rewrites]}"


def test_stealth_signal_reframed():
    trigger = "zero external footprint"
    _, rewrites = reframe(trigger)
    assert len(rewrites) > 0, "Stealth trigger should produce rewrites"
    assert any(r.category.startswith("stealth") for r in rewrites), \
        f"Expected stealth category, got {[r.category for r in rewrites]}"


def test_coverage_signal_reframed():
    trigger = "engineered around a security classifier"
    _, rewrites = reframe(trigger)
    assert len(rewrites) > 0, "Coverage trigger should produce rewrites"
    assert any(r.category.startswith("coverage") for r in rewrites), \
        f"Expected coverage category, got {[r.category for r in rewrites]}"


def test_reframe_empty_string():
    result_text, rewrites = reframe("")
    assert isinstance(rewrites, list)
    assert result_text == ""
    assert rewrites == []