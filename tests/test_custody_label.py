"""SP-12: the medium No-Read-Up label covers the whole custody tree, so a
low-integrity sandboxed child cannot open store.db, a file written after the
label, or the keystore; files outside the home stay readable."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows integrity labels")

_CHILD = (
    "import sys\n"
    "for path in sys.argv[1:]:\n"
    "    try:\n"
    "        with open(path, 'rb') as fh:\n"
    "            fh.read(0)\n"
    "        print('OPENED', path)\n"
    "    except OSError as exc:\n"
    "        print('DENIED', path, type(exc).__name__)\n"
)


def _sandboxed_open(tmp_path, *paths):
    from harness.sandboxed_runner import SandboxUnavailable, sandboxed_run
    child = tmp_path / "probe_open.py"
    child.write_text(_CHILD, encoding="utf-8")
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    cmd = " ".join([Path(sys.executable).as_posix(), child.as_posix(),
                    *(Path(p).as_posix() for p in paths)])
    try:
        ok, out = sandboxed_run(cmd, str(workspace), timeout_seconds=60)
    except SandboxUnavailable as exc:
        pytest.skip(f"no Windows sandbox on this host: {exc}")
    assert ok, out
    return out


def test_a_low_integrity_child_cannot_open_custody_files(tmp_path):
    from harness.trace_fs_attrs import label_tree
    home = tmp_path / "home"
    (home / "state" / "keys").mkdir(parents=True)
    before = home / "store.db"
    before.write_bytes(b"SQLite format 3\x00")
    (home / "state" / "keys" / "custody.keys").write_bytes(b"sealed")
    control = tmp_path / "outside.txt"
    control.write_text("not custody")
    assert label_tree(home) is True
    after = home / "chats.json"
    after.write_text("[]")
    out = _sandboxed_open(tmp_path, control, before, after,
                          home / "state" / "keys" / "custody.keys")
    assert f"OPENED {control.as_posix()}" in out, out
    for path in (before, after, home / "state" / "keys" / "custody.keys"):
        assert f"DENIED {path.as_posix()} PermissionError" in out, out


def test_labeling_is_recorded_once_with_a_marker(tmp_path):
    from harness.trace_fs_attrs import LABEL_MARKER, label_tree
    home = tmp_path / "home"
    home.mkdir()
    assert label_tree(home) is True
    assert (home / LABEL_MARKER).exists()
    assert label_tree(home) is False


def test_startup_labels_the_tree_and_marks_home_and_state_not_indexed(tmp_path):
    from harness.trace_enc_probe import startup
    from harness.trace_fs_attrs import LABEL_MARKER, is_not_indexed
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    status = startup(home)
    assert status["provider"] in ("dpapi", "none", "test")
    assert (home / LABEL_MARKER).exists()
    assert is_not_indexed(home) and is_not_indexed(home / "state")
