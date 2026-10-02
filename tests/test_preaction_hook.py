"""P6: the external hook adapter for Claude Code and Codex.

Vendor contracts read 2026-10-01 (code.claude.com/docs/en/hooks;
learn.chatgpt.com/docs/hooks): exit 2 blocks; any other non-zero exit and a
timeout let the call proceed; Claude Code honors ask; Codex parses ask but does
not support it. Success criteria: ALLOW prints no decision (Claude Code's own
permissions still apply, the monitor never grants); HOLD is ask in an
interactive Claude Code session and deny plus exit 2 in Codex and in deny
mode; an internal error fails closed with an explicit decision, never a crash
exit; a post event with no pre record reads DRIFT.
"""
from __future__ import annotations

import io
import json

from harness.preaction import hook_cli
from harness.preaction.coverage import liveness_join
from harness.preaction.install import settings_block
from harness.preaction.records import HoldStore


def _run(home, client, event, *extra):
    out, err = io.StringIO(), io.StringIO()
    code = hook_cli.main([client, "--home", str(home), *extra],
                         stdin=io.StringIO(json.dumps(event)), stdout=out, stderr=err)
    text = out.getvalue().strip()
    return code, (json.loads(text) if text else None), err.getvalue()


def _pre(tool, tool_input, session="s1", use_id="toolu_1", mode="default"):
    return {"session_id": session, "hook_event_name": "PreToolUse", "tool_name": tool,
            "tool_input": tool_input, "tool_use_id": use_id, "permission_mode": mode,
            "cwd": "/work/repo"}


def test_allow_prints_no_decision(tmp_path):
    code, body, _ = _run(tmp_path, "claude-code", _pre("Read", {"file_path": "/work/repo/a.py"}))
    assert code == 0 and body is None


def test_hold_in_claude_code_asks_with_neutral_reason(tmp_path):
    code, body, _ = _run(tmp_path, "claude-code",
                         _pre("Bash", {"command": "git push --force origin main"}))
    out = body["hookSpecificOutput"]
    assert code == 0 and out["permissionDecision"] == "ask"
    assert out["hookEventName"] == "PreToolUse"
    assert out["permissionDecisionReason"].startswith("held for owner review")
    assert "updatedInput" not in out
    assert HoldStore(tmp_path).read_all()[-1]["verdict"] == "HOLD"


def test_hold_in_deny_mode_denies_with_exit_2(tmp_path):
    code, body, err = _run(tmp_path, "claude-code",
                           _pre("Bash", {"command": "git push --force"}), "--hold-mode", "deny")
    assert code == 2 and body["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert err.strip().startswith("held for owner review")


def test_codex_hold_always_denies(tmp_path):
    event = {"session_id": "c1", "turn_id": "t1", "tool_name": "Bash",
             "tool_input": {"command": "git push --force"}, "tool_use_id": "call_1"}
    code, body, err = _run(tmp_path, "codex", event)
    assert code == 2 and body["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_codex_apply_patch_paths_are_assessed(tmp_path):
    patch = "*** Begin Patch\n*** Update File: /home/u/.codex/hooks.json\n@@\n-a\n+b\n*** End Patch\n"
    code, body, _ = _run(tmp_path, "codex", {"session_id": "c1", "tool_name": "apply_patch",
                                             "tool_input": {"command": patch}, "tool_use_id": "c2"})
    assert code == 2 and "blocked by policy rule monitor-tamper" in \
        body["hookSpecificOutput"]["permissionDecisionReason"]


def test_block_is_deny_even_in_claude_code(tmp_path):
    code, body, _ = _run(tmp_path, "claude-code",
                         _pre("Write", {"file_path": "/home/u/.claude/settings.json", "content": "{}"}))
    assert code == 2 and body["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_internal_error_fails_closed(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("bug")
    monkeypatch.setattr(hook_cli, "_assess_event", boom)
    code, body, _ = _run(tmp_path, "claude-code", _pre("Read", {"file_path": "x"}))
    assert body["hookSpecificOutput"]["permissionDecision"] == "ask" and code == 0
    code, body, _ = _run(tmp_path, "codex", _pre("Read", {"file_path": "x"}))
    assert code == 2 and body["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_internal_deadline_fails_closed(tmp_path, monkeypatch):
    import time
    monkeypatch.setattr(hook_cli, "_assess_event", lambda *a, **k: time.sleep(5))
    code, body, _ = _run(tmp_path, "codex", _pre("Read", {"file_path": "x"}), "--deadline", "0.2")
    assert code == 2 and "deadline" in body["hookSpecificOutput"]["permissionDecisionReason"]


def test_unreadable_stdin_fails_closed(tmp_path):
    out, err = io.StringIO(), io.StringIO()
    code = hook_cli.main(["codex", "--home", str(tmp_path)], stdin=io.StringIO("not json"),
                         stdout=out, stderr=err)
    assert code == 2


def test_post_without_pre_is_drift_and_matched_post_is_not(tmp_path):
    _run(tmp_path, "claude-code", _pre("Read", {"file_path": "/work/repo/a.py"}, use_id="u1"))
    post = dict(_pre("Read", {"file_path": "/work/repo/a.py"}, use_id="u1"),
                hook_event_name="PostToolUse", tool_response={"content": "x"})
    _run(tmp_path, "claude-code", post, "--post")
    orphan = dict(post, tool_use_id="u-unseen")
    _run(tmp_path, "claude-code", orphan, "--post")
    join = liveness_join(HoldStore(tmp_path).read_all())
    assert join["verdict"] == "DRIFT" and join["orphans"] == ["u-unseen"]


def test_prompt_event_sets_owner_goal(tmp_path):
    _run(tmp_path, "claude-code", {"session_id": "s9", "hook_event_name": "UserPromptSubmit",
                                   "prompt": "fix the flaky test"}, "--event", "prompt")
    state = hook_cli.load_session(tmp_path, "claude-code", "s9")
    assert state.goal == "fix the flaky test"


def test_settings_block_shape_for_claude_code(tmp_path):
    block = settings_block("claude-code", python="py", home=str(tmp_path))
    pre = block["hooks"]["PreToolUse"][0]
    assert pre["matcher"] == "*"
    hook = pre["hooks"][0]
    assert hook["type"] == "command" and hook["timeout"] == 30
    assert "-P -E -m harness.preaction.hook_cli claude-code" in hook["command"]
    assert "PostToolUse" in block["hooks"] and "UserPromptSubmit" in block["hooks"]


def test_settings_block_for_codex_uses_deny(tmp_path):
    block = settings_block("codex", python="py", home=str(tmp_path))
    assert "hook_cli codex" in block["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
