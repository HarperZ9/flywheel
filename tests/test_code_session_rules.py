"""Falsifiers for the session's todo tool, plan mode prompt and permission rules."""
import json

import pytest

from harness.code_session import cli, slash
from harness.code_session.backends import build_agent
from harness.code_session.rules import Rules, load_rules
from harness.code_session.session import new_session
from tests.test_code_session import ScriptBackend, _bare_runner


def _session(tmp_path, replies, mode="auto", approver=None, rules=None):
    backend = ScriptBackend(replies)
    s = new_session(build_agent([backend]), str(tmp_path), mode=mode, approver=approver,
                    runner=_bare_runner)
    if rules is not None:
        s.set_rules(rules)
    return s, backend


def test_todo_tool_keeps_the_list_and_works_in_plan_mode(tmp_path):
    items = [{"text": "read the parser", "status": "done"},
             {"text": "write the fix", "status": "in_progress"},
             {"text": "run tests", "status": "pending"}]
    s, _ = _session(tmp_path, ["TOOL todo " + json.dumps({"items": items}), "planned"],
                    mode="plan")
    s.turn("plan the fix")
    assert s.executor.todos == items
    assert slash.dispatch(s, "/todo") == "[x] read the parser\n[>] write the fix\n[ ] run tests"


def test_todo_tool_rejects_a_bad_status(tmp_path):
    s, _ = _session(tmp_path, [])
    res = s.executor.execute("todo", {"items": [{"text": "x", "status": "maybe"}]})
    assert not res.ok and s.executor.todos == []


def test_the_model_is_taught_the_todo_tool(tmp_path):
    s, _ = _session(tmp_path, [])
    assert "TOOL todo" in s.agent.system


def test_plan_mode_tells_the_model_it_is_read_only(tmp_path):
    s, backend = _session(tmp_path, ["1. change x"], mode="plan")
    s.turn("rename x")
    assert backend.seen[-1][-1]["content"].startswith("[plan mode:")


def test_deny_rule_wins_even_in_auto_mode(tmp_path):
    rules = Rules(deny=["run:git push*"], allow=["run:*"])
    s, _ = _session(tmp_path, ['TOOL run {"cmd": "git push origin main"}', "ok"], rules=rules)
    s.turn("push")
    results = [e.content for e in s.ledger.entries if e.kind == "tool_result"]
    assert results and results[0].startswith("[denied] a permission rule refuses")
    decision = [json.loads(e.content) for e in s.ledger.entries if e.kind == "approval"][0]
    assert decision["by"] == "rule:deny:run:git push*"


def test_deny_rule_on_a_path_keeps_the_file_untouched(tmp_path):
    (tmp_path / ".env").write_text("SECRET=1", encoding="utf-8")
    rules = Rules(deny=["*:.env*"])
    s, _ = _session(tmp_path, ['TOOL write_file {"path": ".env", "content": "x"}', "ok"],
                    rules=rules)
    s.turn("overwrite env")
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "SECRET=1"


def test_allow_rule_skips_the_prompt_but_never_opens_plan_mode(tmp_path):
    asked = []
    rules = Rules(allow=["run:python -m pytest*"])
    s, _ = _session(tmp_path, ['TOOL run {"cmd": "python -m pytest --version"}', "ok"],
                    mode="ask", approver=lambda n, a: asked.append(n) or "no", rules=rules)
    s.turn("test")
    assert asked == []
    p, _ = _session(tmp_path, ['TOOL write_file {"path": "w.txt", "content": "x"}', "ok"],
                    mode="plan", rules=Rules(allow=["write_file:*"]))
    p.turn("write")
    assert not (tmp_path / "w.txt").exists()


def test_rules_load_from_user_then_project(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / "permissions.json").write_text(json.dumps({"deny": ["run:rm *"]}), encoding="utf-8")
    (tmp_path / ".flywheel").mkdir()
    (tmp_path / ".flywheel" / "permissions.json").write_text(
        json.dumps({"allow": ["run:npm test"]}), encoding="utf-8")
    rules = load_rules(str(tmp_path), str(home))
    assert rules.deny == ["run:rm *"] and rules.allow == ["run:npm test"]
    assert len(rules.sources) == 2 and not rules.errors


@pytest.mark.parametrize("body", ["{not json", '["a list"]', '{"deny": "run:*"}'])
def test_unreadable_rules_stop_the_session(tmp_path, monkeypatch, capsys, body):
    (tmp_path / ".flywheel").mkdir()
    (tmp_path / ".flywheel" / "permissions.json").write_text(body, encoding="utf-8")
    monkeypatch.setattr(cli, "_home", lambda: str(tmp_path / "home"))
    monkeypatch.setattr(cli, "ladder", lambda **kw: [ScriptBackend([])])
    assert cli.main(["--root", str(tmp_path), "-p", "x"]) == 2
    assert "permission rules could not be read" in capsys.readouterr().err


def test_rules_are_recorded_on_the_ledger(tmp_path):
    s, _ = _session(tmp_path, [], rules=Rules(deny=["run:curl*"]))
    entry = [e for e in s.ledger.entries if e.kind == "rules"][0]
    assert json.loads(entry.content)["deny"] == ["run:curl*"]
