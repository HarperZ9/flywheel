"""The house-voice hook: SessionStart returns the brief as additional context,
Stop asks for one revision only in revise mode, and every path exits 0.

The hook reads the event on stdin, the packaged spec and the settings file. It
opens no socket, starts no process and writes no file."""
import builtins
import io
import json
import os
import socket
import subprocess

import pytest

from articulate import house, house_hook
from house_fixtures import HUMAN_CLAIM_REPLY, RESIDUE_REPLY


class _Out(io.StringIO):
    pass


def _run(event, env, monkeypatch):
    for k in ("ARTICULATE_HOUSE_VOICE",):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    raw = event if isinstance(event, bytes) else json.dumps(event).encode("utf-8")
    out, err = _Out(), _Out()
    code = house_hook.main(stdin=io.BytesIO(raw), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def cfg(tmp_path):
    """A fresh settings folder with the house voice turned on, the opt-in a user makes."""
    return {"ARTICULATE_CONFIG_DIR": str(tmp_path), "ARTICULATE_HOUSE_VOICE": "on"}


def test_session_start_is_silent_by_default(tmp_path, monkeypatch):
    code, out, _ = _run({"hook_event_name": "SessionStart", "source": "startup"},
                        {"ARTICULATE_CONFIG_DIR": str(tmp_path)}, monkeypatch)
    assert (code, out) == (0, "")


def test_session_start_returns_the_brief(cfg, monkeypatch):
    code, out, _ = _run({"hook_event_name": "SessionStart", "source": "startup"}, cfg, monkeypatch)
    assert code == 0
    answer = json.loads(out)
    ctx = answer["hookSpecificOutput"]["additionalContext"]
    assert answer["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert ctx.startswith(house.brief())
    assert "house/2" in ctx and "sha256:" in ctx
    assert "ARTICULATE_HOUSE_VOICE=off" in ctx
    assert len(ctx) <= house.BRIEF_CEILING


@pytest.mark.parametrize("source", ["startup", "resume", "clear", "compact"])
def test_every_session_source_gets_the_brief(cfg, monkeypatch, source):
    _, out, _ = _run({"hook_event_name": "SessionStart", "source": source}, cfg, monkeypatch)
    assert "additionalContext" in out


def test_mode_off_prints_nothing(cfg, monkeypatch):
    env = dict(cfg, ARTICULATE_HOUSE_VOICE="off")
    for event in ({"hook_event_name": "SessionStart"},
                  {"hook_event_name": "Stop", "last_assistant_message": HUMAN_CLAIM_REPLY}):
        code, out, err = _run(event, env, monkeypatch)
        assert (code, out) == (0, "")


def test_stop_does_nothing_outside_revise_mode(cfg, monkeypatch):
    code, out, _ = _run({"hook_event_name": "Stop", "last_assistant_message": HUMAN_CLAIM_REPLY},
                        cfg, monkeypatch)
    assert (code, out) == (0, "")


def test_stop_in_revise_mode_asks_for_one_revision(cfg, monkeypatch):
    env = dict(cfg, ARTICULATE_HOUSE_VOICE="revise")
    code, out, _ = _run({"hook_event_name": "Stop", "stop_hook_active": False,
                         "last_assistant_message": HUMAN_CLAIM_REPLY}, env, monkeypatch)
    assert code == 0
    answer = json.loads(out)
    assert answer["decision"] == "block"
    assert "house/human-claim" in answer["reason"] and "L1" in answer["reason"]


def test_stop_hook_active_yields_no_second_request(cfg, monkeypatch):
    env = dict(cfg, ARTICULATE_HOUSE_VOICE="revise")
    code, out, _ = _run({"hook_event_name": "Stop", "stop_hook_active": True,
                         "last_assistant_message": HUMAN_CLAIM_REPLY}, env, monkeypatch)
    assert (code, out) == (0, "")


def test_stop_with_a_clean_reply_says_nothing(cfg, monkeypatch):
    env = dict(cfg, ARTICULATE_HOUSE_VOICE="revise")
    clean = "The test passes on Python 3.12. I ran it twice."
    _, out, _ = _run({"hook_event_name": "Stop", "last_assistant_message": clean}, env, monkeypatch)
    assert out == ""


@pytest.mark.parametrize("raw", [b"", b"{not json", b"[]", b'{"hook_event_name": 7}',
                                 json.dumps({"hook_event_name": "Stop"}).encode()])
def test_malformed_events_exit_zero_without_output(cfg, monkeypatch, raw):
    env = dict(cfg, ARTICULATE_HOUSE_VOICE="revise")
    code, out, _ = _run(raw, env, monkeypatch)
    assert code == 0 and out == ""


def test_hook_is_sealed(cfg, monkeypatch, tmp_path):
    real_open = builtins.open
    attempts = []

    def no(*a, **k):
        attempts.append(a[:1])
        raise AssertionError("escape")

    def read_only(file, mode="r", *a, **k):
        if set(mode) & set("wax+"):
            attempts.append((file, mode))
            raise AssertionError("write")
        return real_open(file, mode, *a, **k)
    monkeypatch.setattr(socket, "socket", no)
    monkeypatch.setattr(subprocess, "Popen", no)
    monkeypatch.setattr(builtins, "open", read_only)
    monkeypatch.chdir(tmp_path)
    env = dict(cfg, ARTICULATE_HOUSE_VOICE="revise")
    _run({"hook_event_name": "SessionStart"}, env, monkeypatch)
    _run({"hook_event_name": "Stop", "last_assistant_message": RESIDUE_REPLY}, env, monkeypatch)
    assert attempts == [] and os.listdir(tmp_path) == []


def test_session_start_does_not_import_the_style_rules():
    import ast
    import pathlib
    src = pathlib.Path(house_hook.__file__).read_text(encoding="utf-8")
    top = [n for n in ast.parse(src).body if isinstance(n, (ast.Import, ast.ImportFrom))]
    names = {a.name for n in top for a in n.names} | {getattr(n, "module", None) for n in top}
    assert "detector" not in names and "house" not in names
