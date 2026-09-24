"""Every Lean spawn gets an allowlisted environment, never the harness's own.

A Lean candidate runs code while Lean elaborates it. On Lean 4.34.0
(2026-09-23), `#eval IO.getEnv "FLYWHEEL_PROBE_SECRET"` put the variable's
value into the kernel_output of a passing receipt, and the gateway's
/api/lean route stores that receipt. The value was synthetic, as it is here.

The unit tests replace the spawn under run_killable and subprocess.run. They
need no toolchain, and they see the env of every spawn: the version query,
the kernel run, the axiom audit, the prefix query, the .olean compile and
leanchecker. The live tests run only where lean and leanchecker are
installed.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from harness import lean_replay, proc_kill
from harness.lean_oracle import _lean_exe, lean_check, leanchecker_available
from harness.oracle import ENV_ALLOWLIST

PROBE = "FLYWHEEL_PROBE_SECRET"
VALUE = "probe-value-123"
# What the toolchain reads, on top of the oracle's allowlist.
TOOLCHAIN_KEYS = {"ELAN_HOME", "ELAN_TOOLCHAIN", "LEAN_PATH", "LEAN_SYSROOT",
                  "LEAN_NUM_THREADS", "LEAN_STACK_SIZE_KB"}
ALLOWED = ENV_ALLOWLIST | TOOLCHAIN_KEYS
GOOD = "theorem probe_ok : 1 + 1 = 2 := rfl\n"
READ_PROBE = f'#eval IO.getEnv "{PROBE}"\n' + GOOD


class _Proc:
    def __init__(self, rc: int, out: str):
        self.returncode, self._out = rc, out

    def communicate(self, timeout=None):
        return self._out.encode("utf-8"), None


def _fake_toolchain(tmp_path: Path) -> Path:
    prefix = tmp_path / "toolchain"
    suffix = ".exe" if os.name == "nt" else ""
    (prefix / "bin").mkdir(parents=True)
    (prefix / "bin" / f"leanchecker{suffix}").write_bytes(b"")
    (prefix / "lib" / "lean").mkdir(parents=True)
    return prefix


def _record_spawns(monkeypatch, prefix: Path) -> list:
    """Stand in for the process spawn under run_killable. Every step
    succeeds, and the audit run answers for the one named theorem."""
    calls = []

    def spawn(argv, *, env=None, **kw):
        calls.append((list(argv), env))
        if argv[1:] == ["--version"]:
            return _Proc(0, "Lean (version 4.34.0, fake)\n")
        if argv[1:] == ["--print-prefix"]:
            return _Proc(0, f"{prefix}\n")
        if len(argv) == 2 and argv[1].endswith(".lean"):
            if "#print axioms" in Path(argv[1]).read_text(encoding="utf-8"):
                return _Proc(0, "'probe_ok' does not depend on any axioms\n")
        return _Proc(0, "")
    monkeypatch.setattr(proc_kill, "spawn_killable", spawn)
    return calls


def _assert_scrubbed(argv, env, *, elan_home: str = ""):
    """Assertions read key names and booleans only, so a failure report
    never prints a value from the harness environment."""
    assert env is not None, f"{argv} inherited the harness environment"
    extra = sorted(set(env) - ALLOWED)
    assert not extra, (argv, extra)
    leaked = PROBE in env or VALUE in env.values()
    assert not leaked, argv
    if elan_home:
        same = env.get("ELAN_HOME") == elan_home
        assert same, argv


def test_the_allowlist_is_the_oracle_allowlist_plus_the_toolchain_keys():
    from harness.lean_env import LEAN_ENV_ALLOWLIST, lean_env
    assert LEAN_ENV_ALLOWLIST == ALLOWED
    assert lean_env({"LEAN_PATH": "x"})["LEAN_PATH"] == "x"


def test_every_lean_check_spawn_gets_only_allowlisted_keys(monkeypatch,
                                                           tmp_path):
    import harness.lean_oracle as lo
    custom = str(tmp_path / "custom-elan")
    pkgs = str(tmp_path / "pkgs")
    monkeypatch.setenv(PROBE, VALUE)
    monkeypatch.setenv("ELAN_HOME", custom)
    monkeypatch.setenv("LEAN_PATH", pkgs)
    monkeypatch.setattr(lo, "_lean_exe", lambda: "lean-proxy")
    prefix = _fake_toolchain(tmp_path)
    calls = _record_spawns(monkeypatch, prefix)
    doc = lean_check(GOOD)
    assert doc["passed"] is True, doc
    # version, kernel run, audit, prefix query, compile, leanchecker
    assert len(calls) == 6, [argv for argv, _ in calls]
    for argv, env in calls:
        _assert_scrubbed(argv, env, elan_home=custom)
    # The kernel run and the compile read the inherited LEAN_PATH as it is;
    # leanchecker gets the library, the inherited entries, then the build.
    assert calls[1][1]["LEAN_PATH"] == pkgs
    assert calls[4][1]["LEAN_PATH"] == pkgs
    replay_path = calls[5][1]["LEAN_PATH"].split(os.pathsep)
    assert replay_path[:2] == [str(prefix / "lib" / "lean"), pkgs]
    assert replay_path[2].endswith("build")


def test_infra_adapter_spawns_get_only_allowlisted_keys(monkeypatch):
    from harness.infra import lean_adapter as la
    monkeypatch.setenv(PROBE, VALUE)
    seen = []

    def run(argv, **kw):
        seen.append((list(argv), kw.get("env")))
        out = "Lean (version 4.34.0, fake)" if argv[1:] == ["--version"] else ""
        return subprocess.CompletedProcess(argv, 0, out, "")
    monkeypatch.setattr(la.subprocess, "run", run)
    la.reset_lean_probe()
    try:
        result = la.check_lean_source(GOOD, timeout=5)
    finally:
        la.reset_lean_probe()
    assert result.verdict == la.MATCH
    assert len(seen) == 2, seen
    for argv, env in seen:
        _assert_scrubbed(argv, env)


def test_proof_run_and_lean_export_spawns_get_only_allowlisted_keys(
        monkeypatch, tmp_path):
    from harness import lean_export, proof_run
    monkeypatch.setenv(PROBE, VALUE)
    seen = []

    def run(argv, **kw):
        seen.append((list(argv), kw.get("env")))
        return subprocess.CompletedProcess(
            argv, 0, "'confirmed' does not depend on any axioms\n", "")
    monkeypatch.setattr(subprocess, "run", run)
    src = tmp_path / "Answer.lean"
    src.write_text(GOOD, encoding="utf-8")
    assert proof_run.run_proof(src, lean=sys.executable)["verdict"] == "PASS"
    assert lean_export.lean_axioms(GOOD, lean=sys.executable)["ok"] is True
    # proof_run: version query and the run; lean_export: the run
    assert len(seen) == 3, seen
    for argv, env in seen:
        _assert_scrubbed(argv, env)


def _injected(rc: int, *, checker: bool = True):
    def run(argv, code):
        if argv[0] == "leanchecker" and not checker:
            raise OSError("leanchecker not installed")
        if "#print axioms" in code:
            return 0, "'probe_ok' does not depend on any axioms"
        return rc, "" if rc == 0 else "error: type mismatch"
    return run


def _names_the_open_routes(line: str) -> bool:
    # The allowlist empties the Lean process's own environment only. The
    # parent's environment, readable files and the network stay open.
    return all(part in line for part in (
        "allowlisted environment", "the process that started Lean",
        "any file this user can read", "network"))


def test_the_result_names_what_the_allowlist_leaves_open():
    from harness.lean_oracle import LeanOracle
    # Lean ran on every one of these; the last judged nothing because
    # leanchecker could not start, which is UNVERIFIABLE.
    for runner, verdict in ((_injected(0), "PASS"), (_injected(1), "FAIL"),
                            (_injected(0, checker=False), "UNVERIFIABLE")):
        r = LeanOracle(runner=runner).verify(GOOD, None)
        assert r.verdict() == verdict
        assert any(_names_the_open_routes(line)
                   for line in r.does_not_prove), (verdict, r.does_not_prove)
    # Refused before Lean ran: no claim about the environment Lean ran in.
    r = LeanOracle(runner=_injected(0)).verify("theorem t : True := sorry",
                                                None)
    assert r.verdict() == "FAIL"
    assert not any("allowlisted" in line for line in r.does_not_prove)


live = pytest.mark.skipif(not leanchecker_available(),
                          reason="lean or its leanchecker not installed")


@live
def test_live_probe_variable_does_not_reach_the_receipt(monkeypatch):
    monkeypatch.setenv(PROBE, VALUE)
    doc = lean_check(READ_PROBE)
    assert doc["passed"] is True, doc["kernel_output"]
    assert VALUE not in json.dumps(doc)
    # The #eval ran and found no such variable.
    assert "none" in doc["kernel_output"]


@live
def test_live_probe_variable_does_not_reach_a_replay_compile_refusal(
        monkeypatch):
    # A refused .olean compile puts its output in the receipt. This file
    # fails every run, so the replay is driven directly to reach it.
    monkeypatch.setenv(PROBE, VALUE)
    code = (f'#eval (do let v ← IO.getEnv "{PROBE}"; '
            + 'throw (IO.userError s!"leak {v}") : IO Unit)\n' + GOOD)
    res = lean_replay.replay(code, lean=_lean_exe())
    assert res["ok"] is False, res
    assert "leak none" in res["detail"], res["detail"]
    assert VALUE not in res["detail"]


@live
def test_live_infra_adapter_output_carries_no_probe_value(monkeypatch):
    from harness.infra.lean_adapter import build_lean_receipt, check_lean_source
    monkeypatch.setenv(PROBE, VALUE)
    res = check_lean_source(READ_PROBE, timeout=60)
    assert res.verdict == "MATCH", res.error
    assert VALUE not in json.dumps(build_lean_receipt(res, claim="probe"))
    assert "none" in res.output


def _link_dir(link: Path, target: Path) -> None:
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                       check=True, capture_output=True)
    else:
        os.symlink(target, link, target_is_directory=True)


def _unlink_dir(link: Path) -> None:
    """Remove the link itself; the toolchains it points at stay."""
    if os.name == "nt":
        os.rmdir(link)
    else:
        os.unlink(link)


def _custom_elan_home(tmp_path: Path, exe: str) -> "tuple[Path, Path]":
    """An ELAN_HOME outside the default location: the settings pin the
    toolchain the default one resolves to, and `toolchains` links to the
    installed toolchains, so nothing is downloaded."""
    real = Path(exe).resolve().parent.parent
    if not (real / "toolchains").is_dir() or not (real / "settings.toml").is_file():
        pytest.skip("lean on PATH is not an elan proxy")
    _, libdir, _ = lean_replay.toolchain_paths(exe)
    name = Path(libdir).parent.parent.name.replace("---", ":").replace("--", "/")
    custom = tmp_path / "flywheel-custom-elan"
    custom.mkdir()
    settings = (real / "settings.toml").read_text(encoding="utf-8")
    pinned = f'default_toolchain = "{name}"'
    settings, n = re.subn(r"(?m)^default_toolchain\s*=.*$", pinned, settings)
    (custom / "settings.toml").write_text(
        settings if n else pinned + "\n" + settings, encoding="utf-8")
    _link_dir(custom / "toolchains", real / "toolchains")
    return custom, custom / "toolchains"


@live
def test_live_check_under_a_custom_elan_home(monkeypatch, tmp_path):
    # The elan proxy exports the ELAN_HOME it used to the lean it starts, so
    # the #eval shows which home resolved the toolchain. Without ELAN_HOME
    # in the allowlist the proxy would fall back to the default home.
    custom, link = _custom_elan_home(tmp_path, _lean_exe())
    monkeypatch.setenv("ELAN_HOME", str(custom))
    try:
        doc = lean_check('#eval IO.getEnv "ELAN_HOME"\n' + GOOD)
    finally:
        _unlink_dir(link)
    assert doc["passed"] is True, doc["kernel_output"]
    assert doc["validation_level"] == "leanchecker_replay"
    assert "flywheel-custom-elan" in doc["kernel_output"]
