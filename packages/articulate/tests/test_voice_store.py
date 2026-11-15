"""The voice store keeps profiles in one local folder the author can see, list
and delete, and keeps the folder out of version control."""
import builtins
import importlib
import json
import os
import socket
import subprocess

import pytest

from voice_fixtures import VARIED


def store():
    return importlib.import_module("articulate.voice_store")


def _profile():
    return importlib.import_module("articulate.voice").build_profile([t for _, _, t in VARIED])


def test_save_writes_gitignore_and_profile(tmp_path):
    s = store()
    path = s.save(_profile(), "mine", tmp_path)
    assert path.name == "mine.json" and path.parent == tmp_path
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8").strip() == "*"
    assert json.loads(path.read_text(encoding="utf-8"))["schema"] == "articulate/voice-profile/v1"
    assert s.load("mine", tmp_path) == _profile()
    assert s.names(tmp_path) == ["mine"]


def test_delete_removes_the_file_and_returns_its_path(tmp_path):
    s = store()
    path = s.save(_profile(), "mine", tmp_path)
    assert s.delete("mine", tmp_path) == path
    assert not path.exists()
    assert s.names(tmp_path) == []
    with pytest.raises(FileNotFoundError):
        s.delete("mine", tmp_path)


@pytest.mark.parametrize("bad", ["../x", "a/b", "", ".hidden", "a b", "x" * 80, "con\\x"])
def test_unsafe_names_are_refused(tmp_path, bad):
    with pytest.raises(ValueError):
        store().profile_path(bad, tmp_path)


def test_store_location_order(monkeypatch, tmp_path):
    s = store()
    assert s.store_dir(tmp_path) == tmp_path
    monkeypatch.setenv("ARTICULATE_VOICE_DIR", str(tmp_path / "env"))
    assert s.store_dir() == tmp_path / "env"
    monkeypatch.delenv("ARTICULATE_VOICE_DIR")
    if os.name == "nt":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "lad"))
        assert s.store_dir() == tmp_path / "lad" / "articulate" / "voice"
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
        assert s.store_dir() == tmp_path / "xdg" / "articulate" / "voice"


def test_learning_opens_no_socket_and_starts_no_process(monkeypatch, tmp_path):
    def refuse(*a, **k):
        raise AssertionError("voice learn reached outside the machine")
    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(subprocess, "Popen", refuse)
    sample = tmp_path / "s.md"
    sample.write_text(VARIED[0][2], encoding="utf-8")
    from articulate import cli
    assert cli.main(["voice", "learn", str(sample), "--name", "mine", "--mine",
                     "--dir", str(tmp_path / "store")]) == 0
    assert (tmp_path / "store" / "mine.json").is_file()


def test_save_is_atomic_and_leaves_no_temp_file(tmp_path):
    s = store()
    s.save(_profile(), "mine", tmp_path)
    s.save(_profile(), "mine", tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == [".gitignore", "mine.json"]


def test_load_reads_only_in_read_mode(monkeypatch, tmp_path):
    s = store()
    s.save(_profile(), "mine", tmp_path)
    modes = []
    real = builtins.open

    def spy(file, mode="r", *a, **k):
        modes.append(mode)
        return real(file, mode, *a, **k)
    monkeypatch.setattr(builtins, "open", spy)
    s.load("mine", tmp_path)
    assert modes and all(not set(m) & set("wax+") for m in modes)
