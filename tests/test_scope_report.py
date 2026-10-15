"""Falsifiers for `flywheel report scope` (x-likes item 8), scripted model only.

Bar, written before the code: a session that trips each trigger once gives one
entry per trigger (the repeated call also trips its own trigger again, so plan
mode counts 2); a session with none gives an empty report; an edited ledger is
reported as unverifiable and counts for nothing.
"""
import json
import sys

from harness import scope_report
from harness.code_session import store
from harness.code_session.backends import build_agent
from harness.code_session.hooks import HookEntry, Hooks
from harness.code_session.rules import Rules
from harness.code_session.session import new_session
from tests.test_code_session import ScriptBackend, _bare_runner

BLOCK = f'"{sys.executable}" -c "import sys; sys.exit(2)"'
PLAN_WRITE = 'TOOL write_file {"path": "a.txt", "content": "x"}'


def _tripping_session(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "f.txt").write_text("one\n")
    s = new_session(build_agent([ScriptBackend([
        PLAN_WRITE, "ok",
        'TOOL write_file {"path": "secret.txt", "content": "x"}', "ok",
        'TOOL edit_file {"path": "f.txt", "old": "one", "new": "two"}', "ok",
        'TOOL write_file {"path": "b.txt", "content": "x"}', "ok",
        'TOOL list_dir {"path": "."}', "ok",
        'TOOL run {"cmd": "rm -rf /"}', "ok",
        'TOOL read_file {"path": "../outside.txt"}', "ok",
        PLAN_WRITE, "ok",
    ])]), str(work), mode="auto", approver=lambda n, a: "no", runner=_bare_runner)
    s.set_mode("plan"); s.turn("1")
    s.set_mode("auto"); s.set_rules(Rules(deny=["write_file:secret*"])); s.turn("2")
    s.set_hooks(Hooks(entries=[HookEntry("PreToolUse", "edit_file", BLOCK, "t")], cwd=str(work)))
    s.turn("3")
    s.set_mode("ask"); s.turn("4")
    s.set_mode("auto"); s.executor.allowed_tools = frozenset({"read_file"}); s.turn("5")
    s.executor.allowed_tools = None; s.turn("6")
    s.turn("7")
    s.set_mode("plan"); s.turn("8")
    home = tmp_path / "home"
    store.save(s, str(home))
    return home, s


def test_each_trigger_is_found_once_with_its_entry(tmp_path):
    home, s = _tripping_session(tmp_path)
    report = scope_report.build(str(home))
    expected = {k: 1 for k in scope_report.TRIGGERS}
    expected["plan_mode"] = 2
    assert report["counts"] == expected, report["counts"]
    by_hash = {e.entry_hash: e for e in s.ledger.entries}
    for row in report["entries"]:
        assert by_hash[row["entry_hash"]].seq == row["seq"]
    assert report["sessions_scanned"] == 1 and report["unverifiable_sessions"] == []


def test_a_clean_session_gives_an_empty_report_in_words(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    s = new_session(build_agent([ScriptBackend(['TOOL write_file {"path": "a.txt", "content": "x"}',
                                                "done"])]), str(work), mode="auto",
                    runner=_bare_runner)
    s.turn("write")
    store.save(s, str(tmp_path / "home"))
    report = scope_report.build(str(tmp_path / "home"))
    assert report["entries"] == [] and report["sessions_scanned"] == 1
    assert "none of the triggers fired" in scope_report.render(report)


def test_an_edited_ledger_is_unverifiable_and_counts_nothing(tmp_path):
    home, s = _tripping_session(tmp_path)
    path = home / "sessions" / s.session_id / "ledger.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[3])
    row["content"] = row["content"] + " edited"
    lines[3] = json.dumps(row)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = scope_report.build(str(home))
    assert report["unverifiable_sessions"] == [s.session_id]
    assert report["entries"] == [] and report["sessions_scanned"] == 0


def test_since_filters_by_session_start_date(tmp_path):
    home, s = _tripping_session(tmp_path)
    assert scope_report.build(str(home), "2999-01-01")["sessions_scanned"] == 0
    assert scope_report.build(str(home), "2000-01-01")["sessions_scanned"] == 1


def test_the_command_runs_from_the_cli(tmp_path, monkeypatch, capsys):
    home, _s = _tripping_session(tmp_path)
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    from harness.cli_entry import main
    assert main(["report", "scope", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["schema"] == scope_report.SCHEMA and out["counts"]["gate"] == 1
