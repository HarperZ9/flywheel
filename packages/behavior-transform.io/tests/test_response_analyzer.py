import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import json
import pytest

from response_analyzer import (
    HedgeType,
    HedgeDetection,
    ResponseAnalysis,
    analyze_response,
    strip_hedges,
    _scan_patterns,
    _PREAMBLE_PATTERNS,
    _REFUSAL_SOFT_PATTERNS,
    _REFUSAL_HARD_PATTERNS,
    _DISCLAIMER_PATTERNS,
    _COMPLIANCE_THEATER_PATTERNS,
    _REDIRECT_PATTERNS,
)


# --- HedgeType tests ---

def test_hedge_types_complete():
    assert len(HedgeType) == 9
    assert HedgeType.NONE.value == "none"
    assert HedgeType.REFUSAL_HARD.value == "refusal_hard"


# --- Pattern detection tests ---

def test_detect_preamble_hedge():
    text = "I need to be careful about this topic. Here is the answer."
    analysis = analyze_response(text)
    preambles = [h for h in analysis.hedges if h.hedge_type == HedgeType.PREAMBLE_HEDGE]
    assert len(preambles) >= 1


def test_detect_soft_refusal():
    text = "I can't directly help with that request. However, I can explain the concept."
    analysis = analyze_response(text)
    assert analysis.is_refusal is True
    assert analysis.refusal_type == HedgeType.REFUSAL_SOFT


def test_detect_hard_refusal():
    text = "I cannot and will not help with this request. This violates my guidelines."
    analysis = analyze_response(text)
    assert analysis.is_hard_refusal is True
    assert analysis.refusal_type == HedgeType.REFUSAL_HARD


def test_detect_disclaimer():
    text = "As an AI language model, I should mention that this is complex. The answer is 42."
    analysis = analyze_response(text)
    disclaimers = [h for h in analysis.hedges if h.hedge_type == HedgeType.DISCLAIMER]
    assert len(disclaimers) >= 1


def test_detect_compliance_theater():
    text = "Here is the information for educational purposes only. Always follow all laws and regulations."
    analysis = analyze_response(text)
    theater = [h for h in analysis.hedges if h.hedge_type == HedgeType.COMPLIANCE_THEATER]
    assert len(theater) >= 1


def test_detect_redirect():
    text = "Instead, I can help you with a safer alternative approach."
    analysis = analyze_response(text)
    redirects = [h for h in analysis.hedges if h.hedge_type == HedgeType.REDIRECT]
    assert len(redirects) >= 1


def test_detect_capability_denial():
    text = "I don't have the ability to access that system."
    analysis = analyze_response(text)
    denials = [h for h in analysis.hedges if h.hedge_type == HedgeType.CAPABILITY_DENIAL]
    assert len(denials) >= 1


# --- Clean text tests ---

def test_clean_text_no_hedges():
    text = "The function takes two arguments and returns their sum."
    analysis = analyze_response(text)
    assert analysis.hedge_count == 0
    assert analysis.quality_score == 1.0
    assert analysis.is_refusal is False


def test_clean_technical_response():
    text = "To implement this, create a class with a process method that iterates over the input list."
    analysis = analyze_response(text)
    assert analysis.quality_score >= 0.9


# --- Analysis properties ---

def test_analysis_to_dict():
    analysis = analyze_response("I cannot help with that.")
    d = analysis.to_dict()
    assert "hedge_count" in d
    assert "hedge_ratio" in d
    assert "is_refusal" in d
    assert "quality_score" in d
    assert "hedges" in d


def test_analysis_substantive_content():
    text = "I need to be careful here.\nThe actual answer is 42."
    analysis = analyze_response(text)
    assert "42" in analysis.substantive_content


def test_hedge_ratio_computation():
    text = "I cannot help. " * 10 + "The answer is yes."
    analysis = analyze_response(text)
    assert analysis.hedge_ratio > 0


# --- Strip hedges ---

def test_strip_hedges_removes_disclaimer():
    text = "As an AI language model, I want to note this is complex.\nThe answer is 42."
    stripped = strip_hedges(text)
    assert "As an AI" not in stripped
    assert "42" in stripped


def test_strip_hedges_preserves_content():
    text = "The function returns the sum of two numbers."
    stripped = strip_hedges(text)
    assert stripped == text


def test_strip_hedges_compliance_theater():
    text = "Here is the info.\nAlways follow all applicable laws and regulations.\nThe method works by..."
    stripped = strip_hedges(text)
    assert "follow all applicable laws" not in stripped
    assert "method works" in stripped


def test_strip_hedges_empty():
    stripped = strip_hedges("")
    assert stripped == ""


# --- Strippable property ---

def test_strippable_hedges_property():
    text = "I need to be careful about this. As an AI, I should note this. The answer is here."
    analysis = analyze_response(text)
    strippable = analysis.strippable_hedges
    for h in strippable:
        assert h.strippable is True


def test_refusals_not_strippable():
    text = "I cannot help with that request."
    analysis = analyze_response(text)
    for h in analysis.hedges:
        if h.hedge_type in (HedgeType.REFUSAL_SOFT, HedgeType.REFUSAL_HARD):
            assert h.strippable is False


# --- Edge cases ---

def test_empty_response():
    analysis = analyze_response("")
    assert analysis.hedge_count == 0
    assert analysis.quality_score == 1.0


def test_whitespace_only():
    analysis = analyze_response("   \n\n  ")
    assert analysis.hedge_count == 0
