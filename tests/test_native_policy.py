"""Tests for native pre-tool policy enforcement (harness/native_policy.py)."""
from __future__ import annotations

import json

from harness.local_tools import ToolGate
from harness.native_policy import check_tool_call, load_policy


def test_blocks_secret_files_but_allows_env_example(tmp_path):
    assert check_tool_call("read_file", {"path": ".env"}, workspace=tmp_path)["rule"] == "secret-file"
    assert check_tool_call("read_file", {"path": "sub/.env.local"}, workspace=tmp_path)["rule"] == "secret-file"
    assert check_tool_call("read_file", {"path": "secrets.json"}, workspace=tmp_path)["rule"] == "secret-file"
    assert check_tool_call("read_file", {"path": ".env.example"}, workspace=tmp_path) is None


def test_blocks_force_push_chained_merge_and_piped_tests():
    assert check_tool_call("run", {"cmd": "git push --force origin main"})["rule"] == "no-force-push"
    assert check_tool_call("run", {"cmd": "git push -f origin feat"})["rule"] == "no-force-push"
    assert check_tool_call("run", {"cmd": "git push origin feat"}) is None

    assert check_tool_call("run", {"cmd": "pytest -q && gh pr merge 12"})["rule"] == "no-chained-merge"
    assert check_tool_call("run", {"cmd": "cd repo && gh pr merge 12"}) is None

    assert check_tool_call("run", {"cmd": "pytest tests/ | tail -20"})["rule"] == "pipes-swallow-exit-codes"
    assert check_tool_call("run", {"cmd": "set -o pipefail; pytest tests/ | tail -20"}) is None


def test_blocks_unlinked_test_skip_but_allows_linked():
    hit = check_tool_call(
        "edit_file",
        {"path": "tests/test_sample.py", "old": "def test_a():", "new": "@pytest.mark.skip\ndef test_a():"},
    )
    assert hit is not None and hit["rule"] == "no-test-skipping"

    ok = check_tool_call(
        "edit_file",
        {
            "path": "tests/test_sample.py",
            "old": "def test_a():",
            "new": "# HarperZ9/flywheel#999\n@pytest.mark.skip\ndef test_a():",
        },
    )
    assert ok is None


def test_loads_custom_user_and_workspace_policy(tmp_path):
    home = tmp_path / "fw_home"
    home.mkdir()
    (home / "policy.json").write_text(
        json.dumps({"deny_paths": ["protected_archive"], "deny_terms_on_add": ["oldbrand"]}),
        encoding="utf-8",
    )
    policy = load_policy(workspace=tmp_path, flywheel_home=home)
    assert check_tool_call("read_file", {"path": "protected_archive/a.txt"}, policy=policy)["rule"] == "deny-path"
    assert (
        check_tool_call(
            "edit_file",
            {"path": "README.md", "old": "hello", "new": "hello oldbrand"},
            policy=policy,
        )["rule"]
        == "deny-term"
    )


def test_tool_gate_enforces_native_policy():
    gate = ToolGate(allow_write=True, allow_exec=True, enforce_native_policy=True)
    reason = gate.check("run", {"cmd": "git push --force origin main"})
    assert reason is not None and "no-force-push" in reason
    assert gate.check("read_file", {"path": ".env"}) is not None
    assert gate.check("read_file", "not-a-dict") is None
