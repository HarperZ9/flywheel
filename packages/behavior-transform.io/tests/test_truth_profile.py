import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import json
import pytest

from truth_profile import TruthProfile, TruthInjector


def test_truth_profile_defaults():
    p = TruthProfile()
    assert p.narrative == ""
    assert p.render_mode == "paragraph"
    assert p.extra == {}


def test_truth_profile_init_template():
    p = TruthProfile.init_template()
    assert p.operator_context != ""
    assert p.render_mode == "paragraph"


def test_truth_profile_save_load(tmp_path):
    p = TruthProfile(
        operator_context="test operator",
        session_objective="test objective",
    )
    path = tmp_path / "profile.json"
    p.save(path)
    loaded = TruthProfile.load(path)
    assert loaded.operator_context == "test operator"
    assert loaded.session_objective == "test objective"


def test_truth_profile_load_ignores_unknown_fields(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text(json.dumps({
        "operator_context": "valid",
        "unknown_field": "ignored",
    }))
    loaded = TruthProfile.load(path)
    assert loaded.operator_context == "valid"


def test_injector_raw_mode():
    p = TruthProfile(
        narrative="  raw narrative text  ",
        render_mode="raw",
    )
    result = TruthInjector().render(p)
    assert result == "raw narrative text"


def test_injector_paragraph_mode():
    p = TruthProfile(
        operator_context="Part one.",
        engagement_context="Part two.",
        render_mode="paragraph",
    )
    result = TruthInjector().render(p)
    assert result == "Part one. Part two."


def test_injector_list_mode():
    p = TruthProfile(
        operator_context="First item",
        engagement_context="Second item",
        render_mode="list",
    )
    result = TruthInjector().render(p)
    assert result == "- First item\n- Second item"


def test_injector_empty_fields():
    p = TruthProfile(render_mode="paragraph")
    result = TruthInjector().render(p)
    assert result == ""


def test_injector_extra_fields():
    p = TruthProfile(
        operator_context="Base context.",
        extra={"custom": "Extra detail"},
        render_mode="paragraph",
    )
    result = TruthInjector().render(p)
    assert "Extra detail" in result
    assert "Base context." in result


def test_injector_strips_whitespace():
    p = TruthProfile(
        operator_context="  padded  ",
        render_mode="paragraph",
    )
    result = TruthInjector().render(p)
    assert result == "padded"
