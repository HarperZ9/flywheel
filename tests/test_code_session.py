"""Falsifiers for `flywheel code`: a multi-turn agentic session in the base install.

A scripted backend stands in for the model, so these run with no network, no
key and no GPU. The backend is driven through the real LocalAgent, so history
carried across turns is the agent's own, not a test double's.
"""
import json
from types import SimpleNamespace

import pytest

from harness.code_session import cli, slash
from harness.code_session.backends import build_agent
from harness.code_session.session import new_session


class ScriptBackend:
    """Replies in order; records every message list it was sent."""
    name = "script"
    model = "script-1"

    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []

    def health(self):
        return True

    def chat(self, messages, *, system, max_tokens, temperature, seed):
        self.seen.append([dict(m) for m in messages])
        return {"text": self.replies.pop(0), "model_ref": "script:script-1", "seed": seed}


def _bare_runner(cmd, root):
    import subprocess
    p = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, text=True, timeout=60)
    return p.returncode == 0, f"[exit {p.returncode}]\n{p.stdout}{p.stderr}"


def _session(tmp_path, replies, mode="auto", approver=None):
    backend = ScriptBackend(replies)
    agent = build_agent([backend])
    s = new_session(agent, str(tmp_path), mode=mode, approver=approver, runner=_bare_runner)
    return s, backend


def test_second_turn_builds_on_the_first_turns_edit(tmp_path):
    s, backend = _session(tmp_path, [
        'TOOL write_file {"path": "notes.txt", "content": "alpha"}',
        "Wrote notes.txt.",
        'TOOL edit_file {"path": "notes.txt", "old": "alpha", "new": "alpha beta"}',
        "Appended beta.",
    ])
    first = s.turn("create notes.txt with alpha")
    second = s.turn("now add beta")
    assert (tmp_path / "notes.txt").read_text() == "alpha beta"
    assert first.final == "Wrote notes.txt." and second.final == "Appended beta."
    # the model saw turn 1 when it answered turn 2: history carried across turns
    last_call = backend.seen[-1]
    assert any("create notes.txt" in m["content"] for m in last_call)
    assert s.ledger.verify() and s.turns == 2


def test_ask_mode_refusal_never_reaches_the_tool(tmp_path):
    s, _ = _session(tmp_path, [
        'TOOL write_file {"path": "x.txt", "content": "nope"}',
        "Understood, not writing.",
    ], mode="ask", approver=lambda name, args: "no")
    s.turn("write x.txt")
    assert not (tmp_path / "x.txt").exists()
    decisions = [json.loads(e.content) for e in s.ledger.entries if e.kind == "approval"]
    assert decisions == [{"by": "user:no", "class": "write", "decision": "deny",
                          "mode": "ask", "tool": "write_file"}]


def test_always_answer_is_remembered_for_that_tool(tmp_path):
    asked = []
    s, _ = _session(tmp_path, [
        'TOOL write_file {"path": "a.txt", "content": "1"}',
        'TOOL write_file {"path": "b.txt", "content": "2"}',
        "done",
    ], mode="ask", approver=lambda name, args: asked.append(name) or "always")
    s.turn("write two files")
    assert (tmp_path / "a.txt").exists() and (tmp_path / "b.txt").exists()
    assert asked == ["write_file"]


def test_plan_mode_refuses_writes_even_if_the_policy_is_bypassed(tmp_path):
    s, _ = _session(tmp_path, ['TOOL write_file {"path": "p.txt", "content": "x"}', "ok"],
                    mode="plan")
    s.turn("write p.txt")
    assert not (tmp_path / "p.txt").exists()
    # the inner gate is also closed: a direct call past the policy still fails
    assert s.executor.gate.allow_write is False and s.executor.gate.allow_exec is False


def test_edit_mode_writes_freely_and_asks_for_commands(tmp_path):
    asked = []
    s, _ = _session(tmp_path, [
        'TOOL write_file {"path": "w.txt", "content": "w"}',
        'TOOL run {"cmd": "echo hi"}',
        "done",
    ], mode="edit", approver=lambda n, a: asked.append(n) or "no")
    s.turn("write then run")
    assert (tmp_path / "w.txt").exists()
    assert asked == ["run"]


def test_slash_mode_switch_is_recorded_and_enforced(tmp_path):
    s, _ = _session(tmp_path, ['TOOL write_file {"path": "m.txt", "content": "x"}', "ok"],
                    mode="auto")
    assert slash.dispatch(s, "/mode plan") == "mode: plan"
    s.turn("write m.txt")
    assert not (tmp_path / "m.txt").exists()
    assert any(e.kind == "mode" and e.content == "plan" for e in s.ledger.entries)
    assert "unknown mode" in slash.dispatch(s, "/mode yolo")


def test_slash_commands_never_call_the_model(tmp_path):
    s, backend = _session(tmp_path, [])
    for line in ("/help", "/status", "/model", "/mode", "/clear", "/nope"):
        assert isinstance(slash.dispatch(s, line), str)
    assert slash.dispatch(s, "/exit") is slash.EXIT
    assert slash.dispatch(s, "not a command") is None
    assert backend.seen == []
    assert json.loads(slash.dispatch(s, "/status"))["chain_ok"] is True


def test_model_switch_changes_the_live_backend_model(tmp_path):
    s, backend = _session(tmp_path, [])
    assert "script-2" in slash.dispatch(s, "/model script-2")
    assert backend.model == "script-2"


def test_instructions_are_loaded_and_recorded(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "AGENTS.md").write_text("Always use tabs.", encoding="utf-8")
    s, backend = _session(tmp_path, ["fine"])
    loaded = s.load_instructions(home=None)
    assert [p.split("\\")[-1].split("/")[-1] for p in (i.path for i in loaded)] == ["AGENTS.md"]
    assert "Always use tabs." in s.agent.system
    assert any(e.kind == "instructions" for e in s.ledger.entries)


def test_print_mode_runs_one_request_and_exits(tmp_path, capsys):
    backend = ScriptBackend(["The answer is 4."])
    args = cli.parse_args(["-p", "what is 2+2", "--root", str(tmp_path), "--no-instructions"])
    session = cli.build_session(args, backends=[backend], approver=None, runner=_bare_runner)
    code = cli.run_turn(session, args.prompt)
    assert code == 0
    assert capsys.readouterr().out.strip() == "The answer is 4."


def test_no_backend_is_a_clear_error_not_a_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "ladder", lambda **kw: [])
    monkeypatch.setattr(cli, "_home", lambda: str(tmp_path / "home"))
    code = cli.main(["-p", "hi", "--root", str(tmp_path)])
    assert code == 2
    assert "No model is reachable" in capsys.readouterr().err


def test_code_is_a_packaged_command():
    from harness import cli_entry
    assert cli_entry._PACKAGED["code"] == "harness.code_session.cli"


@pytest.mark.parametrize("answer, expected", [("y", "yes"), ("a", "always"), ("", "no"),
                                              ("n", "no")])
def test_prompt_approver_answers(monkeypatch, answer, expected):
    monkeypatch.setattr("builtins.input", lambda _p: answer)
    assert cli.prompt_approver("write_file", {"path": "x"}) == expected


def test_prompt_approver_end_of_input_is_no(monkeypatch):
    def eof(_p):
        raise EOFError
    monkeypatch.setattr("builtins.input", eof)
    assert cli.prompt_approver("run", {"cmd": "ls"}) == "no"


def test_instructions_walk_up_to_the_repo_top_nearest_last(tmp_path):
    from harness.code_session.instructions import load_instructions
    (tmp_path / ".git").mkdir()
    (tmp_path / "AGENTS.md").write_text("top rule", encoding="utf-8")
    sub = tmp_path / "pkg"
    sub.mkdir()
    (sub / "CLAUDE.md").write_text("pkg rule", encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    (home / "AGENTS.md").write_text("user rule", encoding="utf-8")
    texts = [i.text for i in load_instructions(str(sub), str(home))]
    assert texts == ["user rule", "top rule", "pkg rule"]


def test_instructions_never_climb_to_the_home_folder(tmp_path):
    from harness.code_session.instructions import _chain
    home = tmp_path / "home"
    project = home / "work" / "proj"
    project.mkdir(parents=True)
    (home / ".git").mkdir()                      # a home folder that is a repo
    chain = _chain(project.resolve(), stop=home)
    assert home.resolve() not in chain and chain[-1] == project.resolve()


def test_instructions_are_capped_and_flag_truncation(tmp_path):
    from harness.code_session.instructions import load_instructions
    (tmp_path / ".git").mkdir()
    (tmp_path / "AGENTS.md").write_text("x" * 100, encoding="utf-8")
    loaded = load_instructions(str(tmp_path), None, max_bytes=10)
    assert loaded[0].text == "x" * 10 and loaded[0].truncated


def test_init_drafts_agents_md_and_never_overwrites(tmp_path):
    from harness.code_session.instructions import write_init
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    ok, _ = write_init(str(tmp_path))
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert ok and "Python" in text and "pytest" in text
    (tmp_path / "AGENTS.md").write_text("mine", encoding="utf-8")
    ok, msg = write_init(str(tmp_path))
    assert not ok and (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "mine"


def test_session_runner_gives_commands_scratch_temp_and_no_tree_caches(monkeypatch):
    import harness.sandboxed_runner as sr
    seen = {}

    def fake(cmd, root, **kw):
        seen.update(kw)
        return True, "[exit 0]\n"
    monkeypatch.setattr(sr, "sandboxed_run", fake)
    assert cli._runner()("python -m pytest -q", ".") == (True, "[exit 0]\n")
    assert seen["scratch_home"] is True
    assert seen["extra_env"]["PYTEST_ADDOPTS"] == "-p no:cacheprovider"


def test_session_runner_refuses_without_a_sandbox_by_default(monkeypatch):
    import harness.sandboxed_runner as sr
    import harness.tool_sandbox_bridge as tb

    def none(cmd, root, **kw):
        raise sr.SandboxUnavailable("no backend")
    monkeypatch.setattr(sr, "sandboxed_run", none)
    monkeypatch.setattr(tb, "fallback_from_env", lambda *a, **k: "refuse")
    ok, out = cli._runner()("echo hi", ".")
    assert not ok and out.startswith("[refused]")


@pytest.mark.skipif(__import__("os").name != "nt", reason="the low-integrity sandbox is Windows")
def test_pytest_runs_inside_the_windows_sandbox(tmp_path):
    (tmp_path / "test_ok.py").write_text("def test_x():\n    assert 1\n", encoding="utf-8")
    ok, out = cli._runner()("python -m pytest -q test_ok.py", str(tmp_path))
    assert ok, out
    assert "1 passed" in out


def test_plain_output_uses_words_not_symbols(monkeypatch, capsys):
    monkeypatch.setenv("FLYWHEEL_SCREEN_READER", "1")
    cli.print_event({"type": "tool_call", "name": "run", "args": {"cmd": "ls"}})
    cli.print_event({"type": "tool_result", "ok": False, "output": "boom"})
    err = capsys.readouterr().err
    assert err.startswith("Tool call: run") and "Tool result, failed: boom" in err
    assert ">" not in err
    monkeypatch.delenv("FLYWHEEL_SCREEN_READER")
    cli.print_event({"type": "tool_call", "name": "run", "args": {}})
    assert capsys.readouterr().err.startswith("  > run")
