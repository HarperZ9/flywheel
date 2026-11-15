import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))

import json
import pytest
from classifier import _policy


def test_policy_def_is_dataclass():
    import dataclasses
    assert dataclasses.is_dataclass(_policy.PolicyDef)


def test_policy_def_has_name_field():
    fields = {f.name for f in __import__("dataclasses").fields(_policy.PolicyDef)}
    assert "name" in fields


def test_load_policy_store_returns_dict(tmp_path, monkeypatch):
    monkeypatch.setattr(_policy, "_POLICY_PATH", tmp_path / "policies.json")
    result = _policy._load_policy_store()
    assert isinstance(result, dict)


def test_save_and_load_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(_policy, "_POLICY_PATH", tmp_path / "policies.json")
    store = {"test": {"name": "test", "rules": []}}
    _policy._save_policy_store(store)
    loaded = _policy._load_policy_store()
    assert loaded == store


def test_policy_path_is_path():
    assert isinstance(_policy._POLICY_PATH, Path)


def test_builtin_policies_exist():
    assert len(_policy._BUILTIN_POLICIES) >= 4
    assert "strict" in _policy._BUILTIN_POLICIES
    assert "guarded" in _policy._BUILTIN_POLICIES


def test_policy_def_with_defaults():
    p = _policy.PolicyDef(
        name="test", description="Test policy",
        tier1_action="block", tier2_action="warn",
        threshold=30.0, fail_on_over_threshold=False
    )
    assert p.builtin is True
    assert p.created_at == ""


def test_load_policy_def():
    d = {
        "name": "test", "description": "Test",
        "tier1_action": "block", "tier2_action": "warn",
        "threshold": 30.0, "fail_on_over_threshold": False
    }
    p = _policy._load_policy_def(d)
    assert p.name == "test"
    assert p.threshold == 30.0


def test_all_policies_includes_builtins(tmp_path, monkeypatch):
    monkeypatch.setattr(_policy, "_POLICY_PATH", tmp_path / "policies.json")
    policies = _policy._all_policies()
    assert "strict" in policies
    assert "guarded" in policies


def test_active_policy_default(tmp_path, monkeypatch):
    monkeypatch.setattr(_policy, "_POLICY_PATH", tmp_path / "policies.json")
    p = _policy._active_policy()
    assert p.name == "guarded"


def test_policy_list_cmd(tmp_path, monkeypatch):
    monkeypatch.setattr(_policy, "_POLICY_PATH", tmp_path / "policies.json")
    result = _policy.policy_list_cmd()
    assert isinstance(result, list)
    assert len(result) >= 4
    has_active = any(p["active"] for p in result)
    assert has_active


def test_policy_show_cmd_builtin(tmp_path, monkeypatch):
    monkeypatch.setattr(_policy, "_POLICY_PATH", tmp_path / "policies.json")
    result = _policy.policy_show_cmd("strict")
    assert result is not None
    assert result["name"] == "strict"


def test_policy_show_cmd_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(_policy, "_POLICY_PATH", tmp_path / "policies.json")
    result = _policy.policy_show_cmd("nonexistent")
    assert result is None


def test_policy_activate_cmd(tmp_path, monkeypatch):
    monkeypatch.setattr(_policy, "_POLICY_PATH", tmp_path / "policies.json")
    result = _policy.policy_activate_cmd("strict")
    assert "activated" in result
    assert result["activated"] == "strict"


def test_policy_activate_cmd_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(_policy, "_POLICY_PATH", tmp_path / "policies.json")
    result = _policy.policy_activate_cmd("nonexistent")
    assert "error" in result


def test_policy_save_cmd_custom(tmp_path, monkeypatch):
    monkeypatch.setattr(_policy, "_POLICY_PATH", tmp_path / "policies.json")
    result = _policy.policy_save_cmd(
        "custom", "Custom policy", "block", "warn", 25.0, False
    )
    assert result["saved"] == "custom"
    assert "policy" in result


def test_policy_save_cmd_cannot_overwrite_builtin(tmp_path, monkeypatch):
    monkeypatch.setattr(_policy, "_POLICY_PATH", tmp_path / "policies.json")
    result = _policy.policy_save_cmd(
        "strict", "Override", "block", "warn", 25.0, False
    )
    assert "error" in result


def test_policy_save_cmd_invalid_action(tmp_path, monkeypatch):
    monkeypatch.setattr(_policy, "_POLICY_PATH", tmp_path / "policies.json")
    result = _policy.policy_save_cmd(
        "custom", "Custom", "invalid", "warn", 25.0, False
    )
    assert "error" in result


def test_policy_delete_cmd_custom(tmp_path, monkeypatch):
    monkeypatch.setattr(_policy, "_POLICY_PATH", tmp_path / "policies.json")
    _policy.policy_save_cmd("custom", "Custom", "block", "warn", 25.0, False)
    result = _policy.policy_delete_cmd("custom")
    assert result["deleted"] == "custom"


def test_policy_delete_cmd_cannot_delete_builtin(tmp_path, monkeypatch):
    monkeypatch.setattr(_policy, "_POLICY_PATH", tmp_path / "policies.json")
    result = _policy.policy_delete_cmd("strict")
    assert "error" in result


def test_policy_diff_cmd(tmp_path, monkeypatch):
    monkeypatch.setattr(_policy, "_POLICY_PATH", tmp_path / "policies.json")
    result = _policy.policy_diff_cmd("strict", "guarded")
    assert "a" in result
    assert "b" in result
    assert "diffs" in result


def test_policy_diff_cmd_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(_policy, "_POLICY_PATH", tmp_path / "policies.json")
    result = _policy.policy_diff_cmd("strict", "nonexistent")
    assert "error" in result


def test_policy_export_cmd(tmp_path, monkeypatch):
    monkeypatch.setattr(_policy, "_POLICY_PATH", tmp_path / "policies.json")
    result = _policy.policy_export_cmd("strict")
    assert result["format"] == "aup-policy-v1"
    assert "export" in result


def test_policy_export_cmd_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(_policy, "_POLICY_PATH", tmp_path / "policies.json")
    result = _policy.policy_export_cmd("nonexistent")
    assert "error" in result


def test_policy_import_cmd(tmp_path, monkeypatch):
    monkeypatch.setattr(_policy, "_POLICY_PATH", tmp_path / "policies.json")
    export = _policy.policy_export_cmd("strict")
    # Modify the name to make it a custom policy (not a builtin)
    export["export"]["name"] = "custom_strict"
    result = _policy.policy_import_cmd(export)
    assert "saved" in result
    assert result["saved"] == "custom_strict"


def test_policy_import_cmd_invalid_format(tmp_path, monkeypatch):
    monkeypatch.setattr(_policy, "_POLICY_PATH", tmp_path / "policies.json")
    result = _policy.policy_import_cmd({"format": "invalid"})
    assert "error" in result


def test_policy_import_cmd_missing_name(tmp_path, monkeypatch):
    monkeypatch.setattr(_policy, "_POLICY_PATH", tmp_path / "policies.json")
    result = _policy.policy_import_cmd({"format": "aup-policy-v1", "export": {}})
    assert "error" in result
