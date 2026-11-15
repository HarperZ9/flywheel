import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from operator_classifier import classify, ClassifierResult


def test_physical_security_detection():
    text = "I need a vulnerability assessment guide for physical penetration of a data center"
    result = classify(text)
    assert result.category == "PHYSICAL_SECURITY"
    assert result.tier == "T1"
    assert len(result.keywords_hit) >= 2


def test_t0_violent_extremism():
    text = "extremism ideological mobilization extremist-content assessment accelerationist"
    result = classify(text)
    assert result.tier == "T0"
    assert result.category == "VIOLENT_EXTREMISM"


def test_research_intent():
    text = "I want to understand and research social engineering background literature"
    result = classify(text)
    assert result.intent == "RESEARCH"


def test_operational_intent():
    text = "How to execute a social engineering assessment step by step against corporate targets"
    result = classify(text)
    assert result.category == "SOCIAL_ENGINEERING"
    assert result.intent == "OPERATIONAL"


def test_low_confidence_neutral():
    text = "Please help me write a function to sort a list in Python"
    result = classify(text)
    assert result.confidence < 0.3
    assert result.category == "GENERAL"


def test_result_fields():
    result = classify("test")
    for field in ("category", "tier", "intent", "depth", "specificity", "confidence", "keywords_hit"):
        assert hasattr(result, field)
    assert isinstance(result.keywords_hit, list)
