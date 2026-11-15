import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from output_enforcer import enforce_output, EnforcementResult


def test_strips_preamble_hedge():
    text = (
        "I need to be careful about this topic. "
        "Here is the technical analysis you requested.\n\n"
        "The vulnerability exists in the buffer allocation path."
    )
    result = enforce_output(text)
    assert isinstance(result, EnforcementResult)
    assert "I need to be careful" not in result.enforced
    assert "buffer allocation path" in result.enforced
    assert result.hedges_removed >= 1
    assert result.quality_after >= result.quality_before


def test_strips_compliance_theater():
    text = (
        "The attack surface includes three entry points.\n\n"
        "Please note that this information is for educational purposes only. "
        "Always follow all applicable laws and regulations."
    )
    result = enforce_output(text)
    assert "educational purposes only" not in result.enforced
    assert "attack surface" in result.enforced
    assert result.hedges_removed >= 1


def test_strips_disclaimer():
    text = (
        "As an AI language model, I should mention that "
        "this is a complex topic. The correct implementation "
        "uses AES-256-GCM for the envelope encryption."
    )
    result = enforce_output(text)
    assert "As an AI" not in result.enforced
    assert "AES-256-GCM" in result.enforced


def test_preserves_clean_response():
    text = "The function returns a pointer to the allocated buffer."
    result = enforce_output(text)
    assert result.enforced == text
    assert result.hedges_removed == 0
    assert result.quality_before == result.quality_after


def test_detects_refusal():
    text = "I cannot and will not help with that request."
    result = enforce_output(text)
    assert result.is_refusal is True


def test_quality_improves_after_stripping():
    text = (
        "I want to be thoughtful about this. "
        "While I can provide some information, I should mention that "
        "this is sensitive. The answer is 42."
    )
    result = enforce_output(text, min_quality=0.8)
    assert result.quality_after >= result.quality_before
