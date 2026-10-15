"""Falsifiers for subagents and the `task` tool in `flywheel code`."""
import json

from harness.code_session.agents import BUILTIN, load_agents
from harness.code_session.backends import build_agent
from harness.code_session.session import new_session
from harness.local_session import SessionLedger
from tests.test_code_session import ScriptBackend, _bare_runner


class Shared(ScriptBackend):
    """One script for parent and child, in call order."""


def _session(tmp_path, replies, mode="auto", approver=None):
    backend = Shared(replies)
    s = new_session(build_agent([backend]), str(tmp_path), mode=mode, approver=approver,
                    runner=_bare_runner)
    return s, backend


def test_task_runs_a_child_with_its_own_ledger_and_returns_its_answer(tmp_path):
    (tmp_path / "a.txt").write_text("needle here", encoding="utf-8")
    s, backend = _session(tmp_path, [
        'TOOL task {"agent": "explore", "prompt": "where is the needle?"}',   # parent
        'TOOL grep {"pattern": "needle"}',                                    # child
        "It is in a.txt line 1.",                                             # child final
        "The explorer found it in a.txt.",                                    # parent final
    ])
    s.set_agents(load_agents(str(tmp_path), None))
    r = s.turn("find the needle")
    assert r.final == "The explorer found it in a.txt."
    result = [e.content for e in s.ledger.entries if e.kind == "tool_result"][0]
    assert "It is in a.txt line 1." in result and result.startswith("[explore |")
    rec = [json.loads(e.content) for e in s.ledger.entries if e.kind == "subagent"][0]
    assert rec["agent"] == "explore" and rec["chain_ok"] is True
    # the child saw its own system prompt and only the task, not the parent's request
    child_call = backend.seen[1]
    assert child_call == [{"role": "user", "content": "where is the needle?"}]


def test_explore_cannot_write_even_in_auto_mode(tmp_path):
    s, _ = _session(tmp_path, [
        'TOOL task {"agent": "explore", "prompt": "write x"}',
        'TOOL write_file {"path": "x.txt", "content": "1"}',
        "could not",
        "done",
    ])
    s.set_agents(load_agents(str(tmp_path), None))
    s.turn("go")
    assert not (tmp_path / "x.txt").exists()


def test_child_inherits_ask_mode_and_the_users_answer(tmp_path):
    folder = tmp_path / ".flywheel" / "agents"
    folder.mkdir(parents=True)
    (folder / "writer.md").write_text("---\nname: writer\ndescription: writes files\n---\n"
                                      "You write files.", encoding="utf-8")
    asked = []
    s, _ = _session(tmp_path, [
        'TOOL task {"agent": "writer", "prompt": "make y"}',
        'TOOL write_file {"path": "y.txt", "content": "1"}',
        "asked",
        "done",
    ], mode="ask", approver=lambda n, a: asked.append(n) or "no")
    s.set_agents(load_agents(str(tmp_path), None))
    s.turn("go")
    assert asked == ["write_file"] and not (tmp_path / "y.txt").exists()


def test_a_child_cannot_start_a_grandchild(tmp_path):
    s, _ = _session(tmp_path, [
        'TOOL task {"agent": "explore", "prompt": "nest"}',
        'TOOL task {"agent": "explore", "prompt": "deeper"}',
        "stopped",
        "done",
    ])
    s.set_agents(load_agents(str(tmp_path), None))
    s.turn("go")
    assert len([e for e in s.ledger.entries if e.kind == "subagent"]) == 1


def test_child_edits_undo_with_the_parent_turn(tmp_path):
    folder = tmp_path / ".flywheel" / "agents"
    folder.mkdir(parents=True)
    (folder / "w.md").write_text("---\nname: w\n---\nwrite", encoding="utf-8")
    s, _ = _session(tmp_path, ['TOOL task {"agent": "w", "prompt": "make z"}',
                               'TOOL write_file {"path": "z.txt", "content": "1"}', "made", "ok"])
    s.set_agents(load_agents(str(tmp_path), None))
    s.turn("go")
    assert (tmp_path / "z.txt").exists()
    s.undo()
    assert not (tmp_path / "z.txt").exists()


def test_saved_session_keeps_the_child_ledger(tmp_path):
    from harness.code_session.store import sessions_dir
    s, _ = _session(tmp_path, ['TOOL task {"agent": "explore", "prompt": "q"}', "a", "b"])
    s.home, s.session_id = str(tmp_path / "home"), "20261015-000000-abcdef"
    s.set_agents(load_agents(str(tmp_path), None))
    s.turn("go")
    files = list((sessions_dir(s.home) / s.session_id / "subagents").glob("*.jsonl"))
    assert len(files) == 1 and SessionLedger.load(str(files[0])).verify()


def test_agent_files_parse_and_claude_folder_is_read(tmp_path):
    folder = tmp_path / ".claude" / "agents"
    folder.mkdir(parents=True)
    (folder / "rev.md").write_text("---\nname: reviewer\ndescription: reviews\n"
                                   "tools: read_file, grep\nmodel: m2\n---\nReview.",
                                   encoding="utf-8")
    agents = load_agents(str(tmp_path), None)
    assert agents["reviewer"].tools == ("read_file", "grep") and agents["reviewer"].model == "m2"
    assert "explore" in agents and agents["explore"] is BUILTIN["explore"]


def test_unknown_agent_is_an_error_result(tmp_path):
    s, _ = _session(tmp_path, [])
    s.set_agents(load_agents(str(tmp_path), None))
    res = s.executor.execute("task", {"agent": "nope", "prompt": "x"})
    assert not res.ok and "known agent" in res.output
