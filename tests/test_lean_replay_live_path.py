"""The live replay path, run without a Lean toolchain.

CI installs no Lean, so the live tests in test_lean_replay.py always skip
there. These tests drive `_replay_live` with the toolchain lookup and the
spawn replaced, and check what the live tests cannot pin in CI: the compile
argv, the LEAN_PATH leanchecker gets, the shadowed-module refusal, the
timeout mapping, and the tree kill behind `run_killable`.
"""
import os
import sys
import time

from harness import lean_replay
from harness.lean_replay import MODULE, run_killable

GOOD = "theorem one_plus_one : 1 + 1 = 2 := rfl\n"
UNLOADED = ("leanchecker found a problem in Candidate\nuncaught exception: "
            "unknown module prefix 'MyLib'\n\nNo directory 'MyLib' or file "
            "'MyLib.olean' in the search path entries:\n...")


def _fake_toolchain(monkeypatch, tmp_path):
    libdir = tmp_path / "toolchain" / "lib" / "lean"
    libdir.mkdir(parents=True)
    checker = str(tmp_path / "toolchain" / "bin" / "leanchecker")
    monkeypatch.setattr(lean_replay, "toolchain_paths",
                        lambda lean: (checker, str(libdir), ""))
    return checker, str(libdir)


def _fake_spawn(monkeypatch, *, checker=(0, ""), calls=None):
    """Record each spawn; the compile succeeds, leanchecker answers as told."""
    def spawn(argv, *, timeout=lean_replay.TIMEOUT, env=None, label="",
              stderr=None):
        if calls is not None:
            calls.append((list(argv), env))
        return checker if argv[1:] == [MODULE] else (0, "")
    monkeypatch.setattr(lean_replay, "run_killable", spawn)


def test_compile_argv_and_the_replay_search_path(monkeypatch, tmp_path):
    checker, libdir = _fake_toolchain(monkeypatch, tmp_path)
    monkeypatch.setenv("LEAN_PATH", os.pathsep.join(["/pkgs/a", "/pkgs/b"]))
    calls = []
    _fake_spawn(monkeypatch, calls=calls)
    res = lean_replay.replay(GOOD, lean="lean", toolchain="Lean (version x)")
    assert res["ok"] is True, res
    (compile_argv, compile_env), (check_argv, check_env) = calls
    root = compile_argv[1].split("=", 1)[1]
    assert compile_argv == [
        "lean", f"--root={root}", "-o",
        os.path.join(root, "build", f"{MODULE}.olean"),
        os.path.join(root, f"{MODULE}.lean")]
    # The compile inherits the harness environment unchanged.
    assert compile_env is None
    assert check_argv == [checker, MODULE]
    # Toolchain library first, inherited entries in order, build dir last.
    assert check_env["LEAN_PATH"].split(os.pathsep) == [
        libdir, "/pkgs/a", "/pkgs/b", os.path.join(root, "build")]


def test_no_inherited_lean_path_gives_library_then_build(monkeypatch,
                                                         tmp_path):
    _, libdir = _fake_toolchain(monkeypatch, tmp_path)
    monkeypatch.delenv("LEAN_PATH", raising=False)
    calls = []
    _fake_spawn(monkeypatch, calls=calls)
    assert lean_replay.replay(GOOD, lean="lean")["ok"] is True
    entries = calls[1][1]["LEAN_PATH"].split(os.pathsep)
    assert entries[0] == libdir and len(entries) == 2
    assert entries[1].endswith("build")


def test_an_earlier_entry_holding_the_module_name_is_unverifiable(
        monkeypatch, tmp_path):
    _fake_toolchain(monkeypatch, tmp_path)
    for shape in ("file", "dir"):
        pkgs = tmp_path / f"pkgs-{shape}"
        pkgs.mkdir()
        if shape == "file":
            (pkgs / f"{MODULE}.olean").write_bytes(b"not the candidate")
        else:
            (pkgs / MODULE).mkdir()
        monkeypatch.setenv("LEAN_PATH", str(pkgs))
        calls = []
        _fake_spawn(monkeypatch, calls=calls)
        res = lean_replay.replay(GOOD, lean="lean")
        assert res["ok"] is None, res
        assert res["reason"] == lean_replay.R_SHADOW
        assert str(pkgs) in res["detail"]
        # Only the compile ran; leanchecker never saw the shadowed path.
        assert len(calls) == 1


def test_checker_timeout_is_a_refusal_never_a_pass(monkeypatch, tmp_path):
    _fake_toolchain(monkeypatch, tmp_path)
    _fake_spawn(monkeypatch,
                checker=(124, "leanchecker timed out after 90s"))
    res = lean_replay.replay(GOOD, lean="lean")
    assert res["ok"] is False
    assert "timed out" in res["detail"] and res["exit"] == 124


def test_unloadable_import_is_unverifiable_not_fail(monkeypatch, tmp_path):
    _fake_toolchain(monkeypatch, tmp_path)
    _fake_spawn(monkeypatch, checker=(1, UNLOADED))
    res = lean_replay.replay(GOOD, lean="lean")
    assert res["ok"] is None
    assert res["reason"] == lean_replay.R_IMPORT


def test_compile_that_cannot_start_names_the_compile(monkeypatch, tmp_path):
    _fake_toolchain(monkeypatch, tmp_path)

    def spawn(argv, **kw):
        raise FileNotFoundError(argv[0])
    monkeypatch.setattr(lean_replay, "run_killable", spawn)
    res = lean_replay.replay(GOOD, lean="lean")
    assert res["ok"] is None
    assert res["reason"] == lean_replay.R_COMPILE


def test_toolchain_paths_goes_through_the_tree_kill_spawn(monkeypatch,
                                                          tmp_path):
    prefix = tmp_path / "tc"
    suffix = ".exe" if os.name == "nt" else ""
    (prefix / "bin").mkdir(parents=True)
    (prefix / "bin" / f"leanchecker{suffix}").write_bytes(b"")
    (prefix / "lib" / "lean").mkdir(parents=True)
    seen = []

    def spawn(argv, **kw):
        seen.append((argv, kw))
        return 0, f"{prefix}\n"
    monkeypatch.setattr(lean_replay, "run_killable", spawn)
    checker, libdir, why = lean_replay.toolchain_paths("lean")
    assert why == "" and checker.endswith(f"leanchecker{suffix}")
    assert libdir == str(prefix / "lib" / "lean")
    assert seen[0][0] == ["lean", "--print-prefix"]
    assert seen[0][1]["timeout"] == 30

    monkeypatch.setattr(lean_replay, "run_killable", lambda argv, **kw: (
        124, "lean --print-prefix timed out after 30s"))
    checker, libdir, why = lean_replay.toolchain_paths("lean")
    assert checker is None and "timed out" in why


def test_run_killable_reaps_a_grandchild_holding_the_pipe():
    # The child starts a grandchild that inherits the output pipe. Killing
    # only the child would leave the drain waiting on the grandchild, and
    # run_killable would then report the failed drain.
    code = ("import subprocess, sys, time\n"
            "subprocess.Popen([sys.executable, '-c', "
            "'import time; time.sleep(60)'], stdout=sys.stdout, "
            "stderr=sys.stderr)\n"
            "print('started', flush=True)\n"
            "time.sleep(60)\n")
    started = time.monotonic()
    rc, out = run_killable([sys.executable, "-c", code], timeout=3,
                           label="tree")
    elapsed = time.monotonic() - started
    assert rc == 124
    assert "tree timed out after 3s" in out
    assert "drain" not in out, out
    assert elapsed < 20, f"{elapsed:.1f}s"
