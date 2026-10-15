"""Falsifiers for lifecycle hooks and custom slash commands in `flywheel code`."""
import json
import sys

from harness.code_session import cli, slash
from harness.code_session.backends import build_agent
from harness.code_session.commands import load_commands
from harness.code_session.hooks import Hooks, load
from harness.code_session.print_mode import run_print
from harness.code_session.session import new_session
from tests.test_code_session import ScriptBackend, _bare_runner


def _hook_cmd(tmp_path, name, body):
    script = tmp_path / f"{name}.py"
    script.write_text(body, encoding="utf-8")
    return f'"{sys.executable}" "{script}"'


def _session(tmp_path, replies, entries):
    from harness.code_session.hooks import HookEntry
    s = new_session(build_agent([ScriptBackend(replies)]), str(tmp_path), mode="auto",
                    runner=_bare_runner)
    s.set_hooks(Hooks(entries=[HookEntry(*e, source="test") for e in entries],
                      cwd=str(tmp_path)))
    return s


LOG = '''import json, sys, pathlib
data = json.load(sys.stdin)
with open(pathlib.Path(__file__).with_suffix(".log"), "a", encoding="utf-8") as f:
    f.write(json.dumps(data) + "\\n")
'''


def test_pre_tool_hook_exit_2_blocks_the_call_and_the_reason_reaches_the_model(tmp_path):
    block = _hook_cmd(tmp_path, "block", "import sys\nsys.stderr.write('no writes to x.txt')\n"
                                         "sys.exit(2)\n")
    s = _session(tmp_path, ['TOOL write_file {"path": "x.txt", "content": "1"}', "ok"],
                 [("PreToolUse", "write_file", block)])
    s.turn("write")
    assert not (tmp_path / "x.txt").exists()
    result = [e.content for e in s.ledger.entries if e.kind == "tool_result"][0]
    assert "PreToolUse hook blocked" in result and "no writes to x.txt" in result
    hook = [json.loads(e.content) for e in s.ledger.entries if e.kind == "hook"][0]
    assert hook["blocked"] is True and hook["exit"] == 2


def test_json_block_decision_and_matcher(tmp_path):
    block = _hook_cmd(tmp_path, "jb", 'print(\'{"decision": "block", "reason": "use tests"}\')\n')
    s = _session(tmp_path, ['TOOL list_dir {"path": "."}',
                            'TOOL write_file {"path": "y.txt", "content": "1"}', "ok"],
                 [("PreToolUse", "write_file|edit_file", block)])
    s.turn("go")
    results = [e.content for e in s.ledger.entries if e.kind == "tool_result"]
    assert not results[0].startswith("[denied]")             # list_dir did not match
    assert "use tests" in results[1] and not (tmp_path / "y.txt").exists()


def test_post_tool_and_stop_hooks_see_the_event(tmp_path):
    log = _hook_cmd(tmp_path, "log", LOG)
    s = _session(tmp_path, ['TOOL write_file {"path": "z.txt", "content": "1"}', "done"],
                 [("PostToolUse", "", log), ("Stop", "", log)])
    s.turn("write")
    rows = [json.loads(line) for line in
            (tmp_path / "log.log").read_text(encoding="utf-8").splitlines()]
    assert [r["hook_event_name"] for r in rows] == ["PostToolUse", "Stop"]
    assert rows[0]["tool_name"] == "write_file" and rows[0]["tool_response"]["ok"] is True
    assert rows[1]["final"] == "done" and (tmp_path / "z.txt").exists()


def test_user_prompt_hook_blocks_before_the_model_is_called(tmp_path):
    block = _hook_cmd(tmp_path, "up", "import sys\nsys.stderr.write('no secrets')\nsys.exit(2)\n")
    backend = ScriptBackend(["should not be sent"])
    s = new_session(build_agent([backend]), str(tmp_path), mode="auto")
    from harness.code_session.hooks import HookEntry
    s.set_hooks(Hooks(entries=[HookEntry("UserPromptSubmit", "", block, "t")], cwd=str(tmp_path)))
    r = s.turn("paste the key")
    assert r.final.startswith("[blocked by a UserPromptSubmit hook] no secrets")
    assert backend.seen == []


def test_project_hooks_need_a_yes_and_user_hooks_do_not(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / "hooks.json").write_text(json.dumps({"hooks": {"Stop": [
        {"hooks": [{"type": "command", "command": "echo user"}]}]}}), encoding="utf-8")
    (tmp_path / ".flywheel").mkdir()
    (tmp_path / ".flywheel" / "hooks.json").write_text(json.dumps({"hooks": {"Stop": [
        {"hooks": [{"type": "command", "command": "echo project"}]}]}}), encoding="utf-8")
    entries, errors, loaded = load(str(tmp_path), str(home))
    assert [e.command for e in entries] == ["echo user"] and not loaded and not errors
    entries, _, loaded = load(str(tmp_path), str(home), ask=lambda found: True)
    assert [e.command for e in entries] == ["echo user", "echo project"] and loaded


def test_unreadable_hooks_stop_the_session(tmp_path, monkeypatch, capsys):
    (tmp_path / ".flywheel").mkdir()
    (tmp_path / ".flywheel" / "hooks.json").write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(cli, "_home", lambda: str(tmp_path / "home"))
    monkeypatch.setattr(cli, "ladder", lambda **kw: [ScriptBackend([])])
    assert cli.main(["-p", "x", "--root", str(tmp_path)]) == 2
    assert "hooks could not be read" in capsys.readouterr().err


def test_custom_command_expands_arguments_and_runs_as_a_turn(tmp_path, capsys):
    folder = tmp_path / ".flywheel" / "commands"
    folder.mkdir(parents=True)
    (folder / "review.md").write_text("---\ndescription: review a file\n---\n"
                                      "Review $ARGUMENTS for bugs.", encoding="utf-8")
    (folder / "help.md").write_text("cannot replace a built-in", encoding="utf-8")
    cmds = load_commands(str(tmp_path), None, reserved=tuple(slash.COMMANDS))
    assert list(cmds) == ["review"]
    backend = ScriptBackend(["Looks fine."])
    s = new_session(build_agent([backend]), str(tmp_path), mode="auto")
    s.commands = cmds
    out = slash.dispatch(s, "/review parser.py")
    assert isinstance(out, slash.Turn) and str(out) == "Review parser.py for bugs."
    assert "review a file" in slash.dispatch(s, "/help")
    assert run_print(s, "/review lexer.py", "text") == 0
    assert backend.seen[-1][-1]["content"] == "Review lexer.py for bugs."


def test_claude_commands_folder_is_read_for_compatibility(tmp_path):
    folder = tmp_path / ".claude" / "commands"
    folder.mkdir(parents=True)
    (folder / "ship.md").write_text("Prepare the release.", encoding="utf-8")
    assert load_commands(str(tmp_path), None)["ship"].expand("now") == \
        "Prepare the release.\n\nnow"


def test_permission_request_hook_can_allow_or_deny_without_a_prompt(tmp_path):
    allow = _hook_cmd(tmp_path, "allow", 'print(\'{"decision": "allow"}\')\n')
    asked = []
    from harness.code_session.hooks import HookEntry
    s = new_session(build_agent([ScriptBackend(['TOOL write_file {"path": "p.txt", "content": "1"}',
                                                "ok"])]), str(tmp_path), mode="ask",
                    approver=lambda n, a: asked.append(n) or "no", runner=_bare_runner)
    s.set_hooks(Hooks(entries=[HookEntry("PermissionRequest", "write_file", allow, "t")],
                      cwd=str(tmp_path)))
    s.turn("write")
    assert asked == [] and (tmp_path / "p.txt").exists()
    deny = _hook_cmd(tmp_path, "deny", 'print(\'{"decision": "deny", "reason": "no"}\')\n')
    d = new_session(build_agent([ScriptBackend(['TOOL write_file {"path": "q.txt", "content": "1"}',
                                                "ok"])]), str(tmp_path), mode="ask",
                    approver=lambda n, a: "yes", runner=_bare_runner)
    d.set_hooks(Hooks(entries=[HookEntry("PermissionRequest", "", deny, "t")], cwd=str(tmp_path)))
    d.turn("write")
    assert not (tmp_path / "q.txt").exists()
    decision = [json.loads(e.content) for e in d.ledger.entries if e.kind == "approval"][0]
    assert decision["by"] == "hook:deny"


def test_subagent_and_compaction_events_fire(tmp_path):
    log = _hook_cmd(tmp_path, "log", LOG)
    from harness.code_session.agents import load_agents
    from harness.code_session.hooks import HookEntry
    s = new_session(build_agent([ScriptBackend(['TOOL task {"agent": "explore", "prompt": "q"}',
                                                "a"] + ["x " * 400] * 30)]),
                    str(tmp_path), mode="auto", runner=_bare_runner)
    s.set_agents(load_agents(str(tmp_path), None))
    s.set_hooks(Hooks(entries=[HookEntry(e, "", log, "t") for e in
                               ("SubagentStart", "SubagentStop", "PreCompact", "PostCompact")],
                      cwd=str(tmp_path)))
    s.compact_budget = 1500
    s.turn("delegate")
    for i in range(12):
        s.turn("more " * 200)
    events = [json.loads(line)["hook_event_name"] for line in
              (tmp_path / "log.log").read_text(encoding="utf-8").splitlines()]
    assert events[:2] == ["SubagentStart", "SubagentStop"]
    assert "PreCompact" in events and "PostCompact" in events
