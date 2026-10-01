"""`flywheel monitor ...`: the owner's command line for coverage, review and verify.

Success criteria: coverage lists every path E1 to E14 with PRE, POST or NONE and
never reports an uncovered path as PRE; `approve` refuses without a terminal
(an agent's shell has none) and needs the typed confirmation code; `pending`
lists open holds; `verify` exits 0 on MATCH and 1 on DRIFT.
"""
from __future__ import annotations

import io
import json

from harness.cli_entry import _PACKAGED
from harness.preaction import cli
from harness.preaction.coverage import REGISTRY
from tests.preaction_fixtures import call, ctx, monitor


def _cli(*argv, stdin="", isatty=False):
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(list(argv), stdout=out, stderr=err, stdin=io.StringIO(stdin),
                    isatty=lambda: isatty)
    return code, out.getvalue(), err.getvalue()


def test_monitor_is_a_packaged_command():
    assert _PACKAGED["monitor"] == "harness.preaction.cli"


def test_coverage_lists_every_path_honestly(tmp_path):
    code, out, _ = _cli("coverage", "--home", str(tmp_path), "--json")
    rows = {r["path_id"]: r["state"] for r in json.loads(out)}
    assert code == 0 and set(rows) >= {f"E{i}" for i in range(1, 15)}
    assert rows["E1"] == "PRE" and rows["E10"] == "POST"
    assert rows["E12"] == "NONE" and rows["E7"] == "NONE"
    assert set(REGISTRY) == set(rows)


def test_pending_and_approve_need_a_terminal_and_the_code(tmp_path):
    mon = monitor(tmp_path, clock=cli._clock)
    held = mon.gate(call("run", cmd="git push --force"), ctx())
    code, out, _ = _cli("pending", "--home", str(tmp_path), "--json")
    assert [p["hold_id"] for p in json.loads(out)] == [held.hold_id]
    code, _, err = _cli("approve", held.hold_id, "--home", str(tmp_path))
    assert code == 2 and "terminal" in err
    code, _, _ = _cli("approve", held.hold_id, "--home", str(tmp_path), stdin="nope\n", isatty=True)
    assert code == 1
    pending = mon.escalator.read_pending(held.hold_id)
    code, _, _ = _cli("approve", held.hold_id, "--home", str(tmp_path),
                      stdin=pending["confirm_code"] + "\n", isatty=True)
    assert code == 0
    assert mon.gate(call("run", cmd="git push --force"), ctx()).run


def test_reject_from_cli(tmp_path):
    mon = monitor(tmp_path, clock=cli._clock)
    held = mon.gate(call("run", cmd="git push --force"), ctx())
    pending = mon.escalator.read_pending(held.hold_id)
    code, _, _ = _cli("reject", held.hold_id, "--home", str(tmp_path),
                      stdin=pending["confirm_code"] + "\n", isatty=True)
    assert code == 0 and mon.escalator.pending() == []


def test_verify_exit_codes(tmp_path):
    mon = monitor(tmp_path)
    mon.gate(call("run", cmd="git push --force"), ctx())
    assert _cli("verify", str(tmp_path))[0] == 0
    path = tmp_path / "records.jsonl"
    path.write_text(path.read_text(encoding="utf-8").replace('"HOLD"', '"ALLOW"'), encoding="utf-8")
    assert _cli("verify", str(tmp_path))[0] == 1


def test_install_prints_settings_without_writing(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "importable", lambda python: (True, ""))
    code, out, _ = _cli("install", "claude-code", "--home", str(tmp_path), "--print")
    assert code == 0 and "PreToolUse" in json.loads(out)["hooks"]


def test_install_refuses_an_interpreter_that_cannot_import_the_hook(tmp_path, monkeypatch):
    # A hook that cannot import exits 1, which Claude Code and Codex treat as
    # non-blocking: every call would run unassessed. Install must refuse.
    monkeypatch.setattr(cli, "importable", lambda python: (False, "No module named harness.preaction"))
    code, out, err = _cli("install", "claude-code", "--home", str(tmp_path), "--print")
    assert code == 1 and out == "" and "cannot import" in err


def test_install_quotes_an_interpreter_path_with_spaces():
    from harness.preaction.install import settings_block
    cmd = settings_block("claude-code", python="C:/Program Files/Python/python.exe",
                         home="C:/mon home")["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert cmd.startswith('"C:/Program Files/Python/python.exe" -P -E -m')
    assert '--home "C:/mon home"' in cmd


def test_late_approval_from_cli_is_refused_and_recorded(tmp_path):
    from tests.preaction_fixtures import Clock
    mon = monitor(tmp_path, clock=Clock("2020-01-01T00:00:00Z"))
    held = mon.gate(call("run", cmd="git push --force"), ctx())
    pending = mon.escalator.read_pending(held.hold_id)
    code, _, err = _cli("approve", held.hold_id, "--home", str(tmp_path),
                        stdin=pending["confirm_code"] + "\n", isatty=True)
    assert code == 1 and "expired" in err
