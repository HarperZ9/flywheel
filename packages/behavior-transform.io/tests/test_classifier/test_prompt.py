import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import dataclasses
import pytest
from classifier import _prompt
from classifier._policy import _active_policy


def test_parse_prompt_returns_list():
    result = _prompt._parse_prompt("Hello, how can I help?", "text")
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["role"] == "user"
    assert result[0]["content"] == "Hello, how can I help?"


def test_parse_prompt_json_object():
    import json
    obj = json.dumps({"role": "system", "content": "You are helpful."})
    result = _prompt._parse_prompt(obj, "json")
    assert isinstance(result, list)
    assert result[0]["role"] == "system"


def test_parse_prompt_json_array():
    import json
    arr = json.dumps([
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ])
    result = _prompt._parse_prompt(arr, "messages")
    assert isinstance(result, list)
    assert len(result) == 2


def test_parse_prompt_invalid_json_fallback():
    result = _prompt._parse_prompt("not json {{{", "json")
    assert isinstance(result, list)
    assert result[0]["role"] == "user"


def test_prompt_modulator_init():
    policy = _active_policy()
    mod = _prompt.PromptModulator(role="user", fmt="text", policy=policy)
    assert mod.role == "user"
    assert mod.fmt == "text"


def test_prompt_modulator_invalid_role():
    with pytest.raises(ValueError):
        _prompt.PromptModulator(role="unknown", fmt="text")


def test_prompt_modulator_invalid_fmt():
    with pytest.raises(ValueError):
        _prompt.PromptModulator(role="user", fmt="xml")


def test_prompt_modulator_modulate_returns_dict():
    policy = _active_policy()
    mod = _prompt.PromptModulator(role="user", fmt="text", policy=policy)
    result = mod.modulate("Hello world")
    assert isinstance(result, dict)
    assert "calibrated" in result
    assert "target_met" in result


def test_prompt_modulator_modulate_calibrated_is_str():
    policy = _active_policy()
    mod = _prompt.PromptModulator(role="user", fmt="text", policy=policy)
    result = mod.modulate("Hello world")
    assert isinstance(result["calibrated"], str)


def test_prompt_modulator_repr():
    mod = _prompt.PromptModulator(role="system", fmt="text")
    r = repr(mod)
    assert "PromptModulator" in r
    assert "system" in r


def test_family_profile_is_dataclass():
    assert dataclasses.is_dataclass(_prompt.FamilyProfile)


def test_family_profile_fields():
    fp = _prompt.FamilyProfile(
        name="test",
        description="test desc",
        default_target_prob=0.10,
        inference_strength="moderate",
        active_categories=["framing"],
        pressure_threshold=20.0,
    )
    assert fp.name == "test"
    assert fp.default_target_prob == 0.10


def test_family_modulator_init():
    mod = _prompt.FamilyModulator(family="auto", role="user")
    assert mod.family == "auto"
    assert mod.role == "user"


def test_family_modulator_invalid_family():
    with pytest.raises(ValueError):
        _prompt.FamilyModulator(family="unknown_family")


def test_family_modulator_invalid_role():
    with pytest.raises(ValueError):
        _prompt.FamilyModulator(family="claude", role="unknown")


def test_family_modulator_modulate_returns_dict():
    mod = _prompt.FamilyModulator(family="claude", role="user")
    result = mod.modulate("Hello world")
    assert isinstance(result, dict)
    assert "calibrated" in result
    assert "family" in result
    assert result["family"] == "claude"


def test_family_modulator_modulate_calibrated_is_str():
    mod = _prompt.FamilyModulator(family="auto", role="user")
    result = mod.modulate("Hello world")
    assert isinstance(result["calibrated"], str)


def test_family_modulator_repr():
    mod = _prompt.FamilyModulator(family="openai", role="user")
    r = repr(mod)
    assert "FamilyModulator" in r
    assert "openai" in r


def test_family_list_cmd_returns_list():
    result = _prompt.family_list_cmd()
    assert isinstance(result, list)
    assert len(result) > 0


def test_family_list_cmd_has_required_keys():
    result = _prompt.family_list_cmd()
    for entry in result:
        assert "name" in entry
        assert "description" in entry
        assert "target_prob" in entry
        assert "inference_strength" in entry


def test_family_profiles_known_families():
    result = _prompt.family_list_cmd()
    names = {e["name"] for e in result}
    assert "claude" in names
    assert "auto" in names


def test_prompt_modulate_cmd_dry_run():
    result = _prompt.prompt_modulate_cmd(
        text="Hello world",
        role="user",
        fmt="text",
        output=None,
        dry_run=True,
    )
    assert isinstance(result, dict)
    assert "calibrated" in result
