"""lean_replay.py -- replay a Lean candidate's compiled module with leanchecker.

`lean candidate.lean` exits 0 once elaboration succeeds, and elaboration runs
the candidate's own metaprograms. One of them can add a declaration with kernel
checking switched off, naming the `debug.skipKernelTC` option through a `Name`
built from parts so that no source regex sees it. `#print axioms` then reads
the environment that metaprogram wrote and reports no axioms at all. The Lean
reference (ValidatingProofs) places this class at the leanchecker rung:
meta-programs that bypass the kernel's state to add unchecked theorems.

leanchecker ships in the Lean toolchain. It reads a compiled `.olean` in a
separate process and replays every declaration the module adds through the
kernel, so a declaration whose value does not inhabit its stored type is
refused there. This module compiles the candidate to an `.olean` in a temporary
directory and runs leanchecker in plain mode. Plain mode re-checks the
candidate's own declarations and trusts the imported toolchain modules as they
sit on disk. `--fresh` also replays the imports. On one Windows machine on
2026-09-23, plain mode took 1.7 to 3.1 s per file (n=3 on each of two files)
and `--fresh` took 153 s on a one-line file (n=1).

Three choices here carry weight:

- leanchecker comes from the installation prefix of the `lean` that compiled
  the module. An `.olean` belongs to the toolchain that wrote it, and a
  leanchecker from another toolchain would refuse a sound module for a reason
  that says nothing about the candidate.
- LEAN_PATH lists the toolchain library before the build directory. The build
  directory is writable by the candidate's metaprograms. With the build
  directory first, a planted `Init/` directory there shadowed the real `Init`
  for leanchecker (observed 2026-09-23); with the library first the plant was
  ignored.
- leanchecker has no version flag. `leanchecker --version` ignores the flag,
  falls back to "check the current project", and with no lake manifest that is
  every module on the search path (6.8 GB resident before it was killed,
  2026-09-23). The version recorded is the toolchain's `lean --version` line,
  and the receipt says where it came from.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

#: The Lean reference's validation ladder, weakest first. This module reaches
#: the third rung. The fourth (comparator: a sandboxed build, the proof checked
#: against a pinned challenge statement, and an independent kernel such as
#: nanoda) is named so a receipt shows how far short of it a result stops.
LADDER = ("exit_code", "print_axioms", "leanchecker_replay",
          "comparator_external")
NONE = "none"
MODULE = "Candidate"
MODE = "plain"
TIMEOUT = 90
VERSION_SOURCE = ("lean --version of the toolchain leanchecker ships in; "
                  "leanchecker has no version flag")


def run_killable(argv: list, *, timeout: int = TIMEOUT,
                 env: "dict | None" = None, label: str = "") -> tuple:
    """Run argv with stdout and stderr merged; reap the whole tree on timeout.

    Popen plus tree-kill, the oracle.py discipline: the child runs candidate
    metaprograms, and a candidate that forks must cost one timeout, never a
    wedged harness. OSError from a binary that cannot start propagates.
    """
    from .proc_kill import _kill_tree, spawn_killable
    proc = spawn_killable(argv, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT)
    try:
        out, _ = proc.communicate(timeout=timeout)
        return proc.returncode, (out or b"").decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        note = ""
        try:
            proc.communicate(timeout=10)
        except (subprocess.TimeoutExpired, OSError) as exc:
            note = f"; the drain after the kill also failed ({exc})"
        who = label or Path(argv[0]).name
        return 124, f"{who} timed out after {timeout}s{note}"


def toolchain_paths(lean: str) -> tuple:
    """(leanchecker, library dir, reason) for the installation `lean` runs.

    Through an elan proxy `--print-prefix` names the toolchain the proxy
    picked, so the checker and the library match the compiler exactly. Either
    path is None when it is absent, and the reason then says which.
    """
    try:
        r = subprocess.run([lean, "--print-prefix"], capture_output=True,
                           text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, None, f"lean --print-prefix did not run ({exc})"
    lines = (r.stdout or "").strip().splitlines()
    prefix = Path(lines[-1].strip()) if r.returncode == 0 and lines else None
    if prefix is None or not prefix.is_dir():
        return None, None, "lean --print-prefix named no installation directory"
    suffix = ".exe" if os.name == "nt" else ""
    checker = prefix / "bin" / f"leanchecker{suffix}"
    libdir = prefix / "lib" / "lean"
    if not checker.is_file():
        return None, None, ("leanchecker is not in this toolchain's bin "
                            "directory; toolchains older than its move into "
                            "core do not ship it")
    if not libdir.is_dir():
        return None, None, "the toolchain has no lib/lean directory"
    return str(checker), str(libdir), ""


def _result(ok, detail: str, rc=None) -> dict:
    return {"ok": ok, "detail": detail, "exit": rc}


def _checked(rc: int, out: str) -> dict:
    if rc == 0:
        return _result(True, "leanchecker replayed every declaration the "
                             "module adds and the kernel accepted each", rc)
    return _result(False, "leanchecker replay refused the compiled module: "
                          + (out or "").strip()[:800], rc)


def _compile_refused(rc: int, out: str) -> dict:
    return _result(False, "compiling the accepted candidate to an .olean "
                          "failed, so there is nothing to replay; fail closed: "
                          + (out or "").strip()[:600], rc)


def _replay_injected(code: str, runner) -> dict:
    """The injected runner sees the same two steps the live path takes. A
    runner that raises OSError for leanchecker models a missing binary."""
    try:
        rc, out = runner(["lean", "-o", f"{MODULE}.olean"], code)
    except OSError as exc:
        return _result(None, f"lean could not be started to compile ({exc})")
    if rc != 0:
        return _compile_refused(rc, out)
    try:
        rc, out = runner(["leanchecker", MODULE], code)
    except OSError as exc:
        return _result(None, f"leanchecker could not be started ({exc})")
    return _checked(rc, out)


def _replay_live(code: str, lean: str) -> dict:
    checker, libdir, why = toolchain_paths(lean)
    if checker is None:
        return _result(None, why)
    # A file a stray candidate process still holds must not turn a finished
    # verdict into an exception; the directory is then left behind instead.
    with tempfile.TemporaryDirectory(prefix="flywheel-leanchecker-",
                                     ignore_cleanup_errors=True) as td:
        root = Path(td)
        build = root / "build"
        build.mkdir()
        src = root / f"{MODULE}.lean"
        src.write_text(code, encoding="utf-8")
        argv = [lean, f"--root={root}", "-o", str(build / f"{MODULE}.olean"),
                str(src)]
        try:
            rc, out = run_killable(argv)
        except OSError as exc:
            return _result(None, f"lean could not be started to compile ({exc})")
        if rc != 0:
            return _compile_refused(rc, out)
        env = dict(os.environ)
        env["LEAN_PATH"] = os.pathsep.join([libdir, str(build)])
        try:
            rc, out = run_killable([checker, MODULE], env=env)
        except OSError as exc:
            return _result(None, f"leanchecker could not be started ({exc})")
    return _checked(rc, out)


def replay(code: str, *, lean: "str | None" = None, runner=None,
           toolchain: str = "") -> dict:
    """Compile `code` and replay the module through leanchecker (plain mode).

    `ok` is True when the replay accepted, False when the compile or the
    replay refused, and None when leanchecker could not run at all, which the
    caller reports as UNVERIFIABLE and never as a pass. `record` is the
    receipt's `leanchecker` block.
    """
    if runner is not None:
        res = _replay_injected(code, runner)
    elif lean is None:
        res = _result(None, "no lean binary to compile the module with")
    else:
        res = _replay_live(code, lean)
    res["record"] = {"mode": MODE, "module": MODULE, "exit": res["exit"],
                     "version": toolchain, "version_source": VERSION_SOURCE}
    return res


def level(*, kernel_ok: bool, audited: bool, replayed: bool) -> str:
    """The highest rung cleared with every rung below it also cleared.

    `audited` is True only when #print axioms answered for every named
    theorem and none leaned on an axiom outside the classical trio. A file
    with no named theorem was not audited, so its level stops at exit_code
    even when the replay ran and accepted.
    """
    if not kernel_ok:
        return NONE
    if not audited:
        return LADDER[0]
    return LADDER[2] if replayed else LADDER[1]
