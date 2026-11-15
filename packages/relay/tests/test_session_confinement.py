"""The session store stays inside itself, and the stdio server's state never comes
from the folder it was started in.

Falsifiers for the 0.3.0 audit findings P1, P2, P3 and P8: a ``session_id`` that
walks out of the store read another ledger; with ``RELAY_SESSION_DIR`` unset the
store was the working folder; one foreign ``.jsonl`` turned the whole listing
into a ``TypeError``; and a ``.env`` in the working folder described the remote
surface for the stdio doctor.
"""
import json
import os
import subprocess

import pytest

import relay.session_store as store_mod
from relay.local_mcp import handle
from relay.local_session import SessionLedger
from relay.mcp_paths import protected_paths
from relay.session_store import get_session, list_sessions

SECRET_GOAL = "outside-the-store-private-goal-7c1"


def _save(path, goal="do the thing"):
    led = SessionLedger()
    led.append("user", goal)
    led.append("assistant", "on it")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    led.save(str(path))
    return path


def _call(name, **arguments):
    resp = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": name, "arguments": arguments}})
    result = resp["result"]
    return result, json.loads(result["content"][0]["text"])


@pytest.fixture
def layout(tmp_path, monkeypatch):
    """A store, a private ledger beside it, and a per-user data folder of its own."""
    store, outside = tmp_path / "store", tmp_path / "outside"
    _save(store / "good.jsonl", goal="inside goal")
    _save(outside / "private.jsonl", goal=SECRET_GOAL)
    home = tmp_path / "home"
    for var in ("LOCALAPPDATA", "XDG_DATA_HOME"):
        monkeypatch.setenv(var, str(home / var.lower()))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("RELAY_SESSION_DIR", str(store))
    return store, outside


@pytest.mark.parametrize("sid", ["../outside/private", "..\\outside\\private", "..", ".",
                                 "a/b", "", "x" * 129, "bad name", "semi;colon"])
def test_a_session_id_that_is_not_a_bare_name_is_refused(layout, sid):
    result, body = _call("local_agent_sessions", session_id=sid)
    text = json.dumps(body)
    if sid == "":
        # An empty id asks for the listing, as before.
        assert body["count"] == 1 and SECRET_GOAL not in text
        return
    assert result.get("isError") is True
    assert body["error"]["code"] == "INVALID_ARGUMENT"
    assert SECRET_GOAL not in text


def test_an_absolute_path_is_refused(layout):
    _, outside = layout
    result, body = _call("local_agent_sessions", session_id=str(outside / "private"))
    assert result.get("isError") is True and body["error"]["code"] == "INVALID_ARGUMENT"
    assert SECRET_GOAL not in json.dumps(body)


def test_a_symlink_out_of_the_store_is_neither_opened_nor_listed(layout):
    store, outside = layout
    try:
        os.symlink(outside / "private.jsonl", store / "evil.jsonl")
    except OSError:
        pytest.skip("this machine cannot create a symlink")
    got = get_session(str(store), "evil")
    assert got.get("code") == "NOT_FOUND" and SECRET_GOAL not in json.dumps(got)
    listing = list_sessions(str(store))
    assert [s["id"] for s in listing["sessions"]] == ["good"]
    assert listing["skipped"] == 1 and SECRET_GOAL not in json.dumps(listing)


@pytest.mark.skipif(os.name != "nt", reason="a junction is a Windows link")
def test_a_junction_out_of_the_store_is_refused(layout):
    store, outside = layout
    link = store / "evil"
    made = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                          capture_output=True, text=True, timeout=30)
    if made.returncode != 0:
        pytest.skip("this machine cannot create a junction")
    for sid in ("evil/private", "evil\\private"):
        result, body = _call("local_agent_sessions", session_id=sid)
        assert result.get("isError") is True and SECRET_GOAL not in json.dumps(body)
    assert SECRET_GOAL not in json.dumps(list_sessions(str(store)))


def test_with_the_store_unset_nothing_is_read_from_the_working_folder(layout, tmp_path,
                                                                      monkeypatch):
    cwd = tmp_path / "launched-here"
    _save(cwd / "planted.jsonl", goal=SECRET_GOAL)
    monkeypatch.chdir(cwd)
    monkeypatch.delenv("RELAY_SESSION_DIR")
    _, listing = _call("local_agent_sessions")
    assert listing["count"] == 0 and SECRET_GOAL not in json.dumps(listing)
    _, one = _call("local_agent_sessions", session_id="planted")
    assert SECRET_GOAL not in json.dumps(one)
    home = os.path.normcase(os.path.realpath(str(tmp_path / "home")))
    assert os.path.normcase(os.path.realpath(store_mod.default_session_dir())).startswith(home)


def test_the_default_store_is_a_per_user_folder_saved_sessions_list_from(layout, monkeypatch):
    monkeypatch.delenv("RELAY_SESSION_DIR")
    _save(os.path.join(store_mod.default_session_dir(), "saved.jsonl"), goal="saved goal")
    _, listing = _call("local_agent_sessions")
    assert [s["id"] for s in listing["sessions"]] == ["saved"]


def test_one_bad_ledger_is_skipped_and_counted(layout):
    store, _ = layout
    (store / "foreign.jsonl").write_text('{"note": 1}\n', encoding="utf-8")
    (store / "garbage.jsonl").write_text("not json at all\n", encoding="utf-8")
    result, listing = _call("local_agent_sessions")
    assert result.get("isError") is not True
    assert [s["id"] for s in listing["sessions"]] == ["good"]
    assert listing["count"] == 1 and listing["skipped"] == 2


def test_a_foreign_file_opened_by_id_is_an_error_not_a_traceback(layout):
    store, _ = layout
    (store / "foreign.jsonl").write_text('{"note": 1}\n', encoding="utf-8")
    result, body = _call("local_agent_sessions", session_id="foreign")
    assert "error" in body and "Traceback" not in json.dumps(body)


def test_a_missing_session_names_not_found(layout):
    result, body = _call("local_agent_sessions", session_id="nope")
    assert body["code"] == "NOT_FOUND" and "error" in body


def test_the_default_store_is_protected_from_run_writes(layout, monkeypatch):
    monkeypatch.delenv("RELAY_SESSION_DIR")
    no_write = protected_paths(os.environ).no_write
    assert os.path.normcase(os.path.realpath(store_mod.default_session_dir())) in no_write


def test_a_planted_env_file_leaves_the_stdio_doctor_unconfigured(tmp_path, monkeypatch):
    cwd = tmp_path / "launched-here"
    cwd.mkdir()
    (cwd / ".env").write_text("RELAY_REMOTE_TOKEN=planted-token\n"
                              "RELAY_PUBLIC_URL=https://attacker.example\n", encoding="utf-8")
    monkeypatch.chdir(cwd)
    for var in ("RELAY_ENV_FILE", "RELAY_REMOTE_TOKEN", "RELAY_PUBLIC_URL"):
        monkeypatch.delenv(var, raising=False)
    _, body = _call("relay.doctor")
    remote = body["remote"]
    assert remote["configured"] is False and remote["public_url"] is None
    assert remote["env_file"] is None and remote["env_file_found"] is False
    assert "attacker.example" not in json.dumps(body)


def test_a_named_env_file_is_still_read_by_the_doctor(tmp_path, monkeypatch):
    env_file = tmp_path / "remote.env"
    env_file.write_text("RELAY_REMOTE_TOKEN=named-token\n", encoding="utf-8")
    monkeypatch.setenv("RELAY_ENV_FILE", str(env_file))
    monkeypatch.delenv("RELAY_REMOTE_TOKEN", raising=False)
    _, body = _call("relay.doctor")
    assert body["remote"]["configured"] is True and "named-token" not in json.dumps(body)
