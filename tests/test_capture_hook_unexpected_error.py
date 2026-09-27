"""An unexpected error inside the hook is still a named, spooled failure: a
Codex hook exits 0 with a systemMessage (as every Codex hook does), and a
Claude Code Stop exits 1 with one stderr line. Neither exits 2."""
import json

import pytest

from delete_fixtures import OWNER
from harness.capture_hooks import __main__ as hook, spool

EVENT = json.dumps({"session_id": "0f6d2c1e-4b7a-4c55-9a51-2f0e7c9d1a3b",
                    "hook_event_name": "Stop", "last_assistant_message": "a"}).encode()


@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    (home / "owner.ref").write_text(OWNER)
    work = tmp_path / "work"
    work.mkdir()

    def boom(*a, **k):
        raise RuntimeError("planted")
    monkeypatch.setattr(hook, "_act", boom)
    return home, work


def test_codex_gets_exit_zero_and_a_system_message(home):
    home, work = home
    code, out, err = hook.run(["stop", "--client", "codex", "--home", str(home)], EVENT,
                              {}, str(work))
    assert code == 0 and "HOOK_ERROR" in json.loads(out)["systemMessage"]
    assert [r["reason_code"] for r in spool.failures(home)] == ["HOOK_ERROR"]


def test_claude_code_stop_exits_one_with_one_line(home):
    home, work = home
    code, out, err = hook.run(["stop", "--client", "claude-code", "--home", str(home)], EVENT,
                              {}, str(work))
    assert code == 1 and out == "" and "HOOK_ERROR" in err
    assert [r["reason_code"] for r in spool.failures(home)] == ["HOOK_ERROR"]
