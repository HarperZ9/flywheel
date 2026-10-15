"""Falsifiers for project memory notes in `flywheel code`."""
import json

from harness.code_session import slash
from harness.code_session.backends import build_agent
from harness.code_session.memory import memory_file, notes
from harness.code_session.session import new_session
from tests.test_code_session import ScriptBackend, _bare_runner


def _session(tmp_path, replies, mode="auto", approver=None):
    s = new_session(build_agent([ScriptBackend(replies)]), str(tmp_path / "proj"), mode=mode,
                    approver=approver, runner=_bare_runner)
    s.set_memory(str(tmp_path / "home"))
    return s


def test_a_note_reaches_the_next_session_and_lives_outside_the_tree(tmp_path):
    (tmp_path / "proj").mkdir()
    s = _session(tmp_path, ['TOOL remember {"note": "tests run with python -m pytest -q"}', "ok"])
    s.turn("remember how to test")
    path = memory_file(str(tmp_path / "home"), str(tmp_path / "proj"))
    assert path.is_file() and (tmp_path / "proj") not in path.parents
    assert notes(path)[0].endswith("tests run with python -m pytest -q")
    later = _session(tmp_path, [])
    assert "tests run with python -m pytest -q" in later.agent.system


def test_memory_asks_in_ask_mode_and_is_refused_in_plan(tmp_path):
    (tmp_path / "proj").mkdir()
    asked = []
    s = _session(tmp_path, ['TOOL remember {"note": "x"}', "ok"], mode="ask",
                 approver=lambda n, a: asked.append(n) or "no")
    s.turn("note it")
    assert asked == ["remember"]
    p = _session(tmp_path, ['TOOL remember {"note": "x"}', "ok"], mode="plan")
    p.turn("note it")
    assert notes(memory_file(str(tmp_path / "home"), str(tmp_path / "proj"))) == []


def test_memory_and_forget_commands(tmp_path):
    (tmp_path / "proj").mkdir()
    s = _session(tmp_path, ['TOOL remember {"note": "one"}', 'TOOL remember {"note": "two"}', "ok"])
    s.turn("two notes")
    listing = slash.dispatch(s, "/memory")
    assert listing.splitlines()[0].endswith("one") and listing.splitlines()[1].endswith("two")
    assert slash.dispatch(s, "/forget 1") == "forgot note 1"
    assert slash.dispatch(s, "/memory").splitlines()[0].endswith("two")
    assert slash.dispatch(s, "/forget 9").startswith("usage")
    assert any(e.kind == "forget" for e in s.ledger.entries)


def test_different_folders_keep_different_notes(tmp_path):
    a, b = memory_file(str(tmp_path), str(tmp_path / "a")), memory_file(str(tmp_path), str(tmp_path / "b"))
    assert a != b and a.parent == b.parent
