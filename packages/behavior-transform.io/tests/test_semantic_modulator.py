import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from semantic_modulator import (
    SemanticModulator,
    SemanticModulationResult,
    semantic_modulator,
    modulate_semantically,
)


def test_modulator_instantiates():
    m = SemanticModulator()
    assert m is not None


def test_clean_text_not_blocked():
    m = SemanticModulator()
    result = m.modulate("the weather is sunny and warm today")
    assert result.blocked is False
    assert result.audit_trail.get("status") == "clean"


def test_clean_text_original_preserved():
    m = SemanticModulator()
    text = "normal text about software development"
    result = m.modulate(text)
    assert result.original == text


def test_compound_rewrites_detected():
    m = SemanticModulator()
    result = m.modulate("we need to gain initial access to the target server")
    assert result.compound_rewrites > 0


def test_technique_mapping():
    m = SemanticModulator()
    result = m.modulate("the attacker used a spear phishing campaign")
    assert len(result.technique_mappings) > 0


def test_demodulate_reverses_substitutions():
    m = SemanticModulator()
    result = m.modulate("testing clean text")
    demod = result.demodulate("response text")
    assert isinstance(demod, str)


def test_demodulate_no_substitutions_passthrough():
    result = SemanticModulationResult(
        original="clean",
        modulated="clean",
        applied_substitutions=[],
    )
    assert result.demodulate("response") == "response"


def test_classify_and_modulate():
    m = SemanticModulator()
    classification, result = m.classify_and_modulate("normal text here")
    assert isinstance(classification, dict)
    assert isinstance(result, SemanticModulationResult)
    assert classification["blocked"] is False


def test_classify_and_modulate_returns_categories():
    m = SemanticModulator()
    classification, _ = m.classify_and_modulate("clean text")
    assert "categories" in classification
    assert isinstance(classification["categories"], list)


def test_modulate_semantically_convenience():
    result = modulate_semantically("clean text about weather")
    assert isinstance(result, SemanticModulationResult)
    assert result.blocked is False


def test_semantic_modulator_singleton():
    m1 = semantic_modulator()
    m2 = semantic_modulator()
    assert m1 is m2


def test_modulation_result_fields():
    result = SemanticModulationResult(
        original="test",
        modulated="test result",
        compound_rewrites=2,
        technique_mappings=[("pat", "desc")],
        density_restructured=[0, 1],
    )
    assert result.compound_rewrites == 2
    assert len(result.technique_mappings) == 1
    assert result.density_restructured == [0, 1]


def test_build_frame_empty_for_no_detections():
    m = SemanticModulator()
    frame = m._build_frame([])
    assert frame == ""


def test_compound_patterns_exist():
    from semantic_modulator import _COMPOUND_PATTERNS
    assert len(_COMPOUND_PATTERNS) > 10


def test_technique_descriptors_exist():
    from semantic_modulator import _TECHNIQUE_DESCRIPTORS
    assert len(_TECHNIQUE_DESCRIPTORS) > 10


def test_category_frame_covers_all_14():
    from semantic_modulator import _CATEGORY_FRAME
    from categories import HarmCategory
    for cat in HarmCategory:
        assert cat in _CATEGORY_FRAME, f"missing frame for {cat}"
