import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))


def test_no_warden_imports_after_load():
    import safe_classify
    for mod_name in list(sys.modules.keys()):
        assert "warden_per_turn_dispatcher" not in mod_name
        assert "warden_shell.classifier_modifier_layer" not in mod_name


def test_classify_returns_for_neutral_text():
    import safe_classify
    result = safe_classify.classify("Sort a list in Python")
    assert result is not None


def test_classify_scores_physical_security():
    import safe_classify
    result = safe_classify.classify(
        "physical penetration vulnerability assessment for a data center"
    )
    assert result is not None
    assert "result" in result
    assert result["result"]["category"] == "PHYSICAL_SECURITY"


def test_classify_result_has_expected_keys():
    import safe_classify
    result = safe_classify.classify("Sort a list in Python")
    assert "result" in result
    assert "pressure" in result
    assert "gate" in result
    assert "policy" in result
    assert "semantic_modulation" in result
    assert "calibration" in result


def test_classify_result_category_present():
    import safe_classify
    result = safe_classify.classify("physical penetration vulnerability assessment")
    assert "category" in result["result"]
    assert result["result"]["category"] == "PHYSICAL_SECURITY"


def test_classify_neutral_text_low_confidence():
    import safe_classify
    result = safe_classify.classify("Sort a list in Python")
    assert result["result"]["confidence"] < 0.3
    assert result["result"]["category"] == "GENERAL"


def test_friction_gate_heuristic_used():
    import safe_classify
    result = safe_classify.classify("Sort a list in Python")
    assert result["gate"]["method"] == "heuristic"
    assert result["gate"]["status"] == "ok"


def test_no_pkl_model_loaded():
    import safe_classify
    import inspect
    source = inspect.getsource(safe_classify)
    assert "model.pkl" not in source
    assert "pickle.load" not in source


def test_semantic_modulation_field_present():
    import safe_classify
    result = safe_classify.classify("Sort a list in Python")
    assert result["semantic_modulation"] in ("ok", "unavailable")
