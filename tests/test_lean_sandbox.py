"""The limits on the candidate's one compile (harness/lean_sandbox.py).

The stubbed tests always run. The live ones need a Lean toolchain with
leanchecker, and the write and memory probes need Windows, where the compile
runs at low integrity inside a job object; CI installs no Lean, so they skip
there.
"""
import os
import sys

import pytest

from harness import lean_binding, lean_sandbox
from harness.lean_binding import _Live, bound_check, parse_challenge
from harness.lean_binding_judge import judge
from harness.lean_oracle import leanchecker_available

live = pytest.mark.skipif(not leanchecker_available(),
                          reason="lean or its leanchecker not installed")
windows = pytest.mark.skipif(os.name != "nt", reason="the low-integrity "
                             "token and job object are Windows-only")
pytestmark = pytest.mark.timeout(420)
CH = {"theorem": "t", "statement": "True"}


def test_limits_take_positive_integers_from_the_environment(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_LEAN_SANDBOX_MEMORY_MB", "512")
    monkeypatch.setenv("FLYWHEEL_LEAN_SANDBOX_CPU_SECONDS", "-3")
    lim = lean_sandbox.limits()
    assert lim["memory_mb"] == 512
    assert lim["cpu_seconds"] == lean_sandbox.DEFAULTS["cpu_seconds"]


def test_the_sandbox_runs_a_program_and_reports_its_limits(tmp_path):
    rc, out, info = lean_sandbox.run_sandboxed(
        [sys.executable, "-c", "print('inside')"], writable=tmp_path,
        cwd=tmp_path, timeout=60)
    assert rc == 0 and "inside" in out
    assert info["applied"] is True
    assert info["network"] == "not restricted"
    assert info["mechanism"].startswith("windows" if os.name == "nt"
                                        else "posix")


@pytest.mark.skipif(sys.platform == "darwin", reason="no memory limit is "
                    "claimed on macOS")
def test_the_sandbox_memory_limit_stops_a_program(monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_LEAN_SANDBOX_MEMORY_MB", "256")
    rc, _, info = lean_sandbox.run_sandboxed(
        [sys.executable, "-c", "b = bytearray(1024 * 1024 * 1024)"],
        writable=tmp_path, cwd=tmp_path, timeout=60)
    assert rc not in (0, None)
    assert info["memory_limit_mb"] == 256


def test_a_sandbox_that_cannot_be_applied_never_compiles_unsandboxed():
    class NoSandbox:
        sandbox = lean_sandbox.unavailable("job objects refused")
        compile_candidate = staticmethod(lambda code: (None, "refused"))
    ch, _ = parse_challenge(CH)
    doc = judge("theorem t : True := trivial", ch, NoSandbox(), "sha", "t")
    assert doc["passed"] is None
    assert doc["unverifiable_reason"] == "sandbox-unavailable"
    assert doc["sandbox"]["applied"] is False
    assert doc["sandbox"]["network"] == "not restricted"


def test_the_live_compile_goes_through_the_sandbox(monkeypatch, tmp_path):
    seen = {}

    def fake(argv, *, writable, cwd, timeout, env=None):
        seen.update(argv=argv, writable=writable, timeout=timeout)
        return 0, "", {"applied": True}
    monkeypatch.setattr(lean_sandbox, "run_sandboxed", fake)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    lean = bindir / ("lean.exe" if os.name == "nt" else "lean")
    lean.write_bytes(b"")
    root = tmp_path / "t"
    root.mkdir()
    steps = _Live(root, "lean-proxy", str(bindir / "leanchecker"),
                  str(tmp_path))
    assert steps.compile_candidate("theorem t : True := trivial") == (0, "")
    assert seen["argv"][0] == str(lean)       # the toolchain's own lean
    assert seen["writable"] == root / "cb"
    assert seen["timeout"] == lean_binding.COMPILE_TIMEOUT
    assert steps.sandbox == {"applied": True}


def test_no_toolchain_lean_beside_leanchecker_is_sandbox_unavailable(
        tmp_path):
    root = tmp_path / "t"
    root.mkdir()
    steps = _Live(root, "lean", str(tmp_path / "nowhere" / "leanchecker"),
                  str(tmp_path))
    rc, _ = steps.compile_candidate("theorem t : True := trivial")
    assert rc is None and steps.sandbox["applied"] is False


@live
def test_live_the_compile_reports_its_limits_and_usage():
    doc = bound_check("theorem t : True := trivial\n", CH)
    box = doc["sandbox"]
    assert box["applied"] is True
    assert box["network"] == "not restricted"
    assert box["memory_limit_mb"] == lean_sandbox.limits()["memory_mb"]
    if os.name == "nt":
        assert box["peak_memory_mb"] > 0


@live
@windows
def test_live_a_metaprogram_cannot_write_outside_the_build_directory(
        tmp_path):
    target = tmp_path / "planted.txt"
    probe = ("import Lean\nrun_cmd do\n  IO.FS.writeFile "
             f"\"{target.as_posix()}\" \"x\"\ntheorem t : True := trivial\n")
    doc = bound_check(probe, CH)
    assert doc["passed"] is False
    assert not target.exists()
    assert "permission denied" in doc["kernel_output"]


@live
@windows
def test_live_the_memory_limit_stops_the_compile(monkeypatch):
    # `import Lean` peaked at about 2.1 GB on the measuring machine.
    monkeypatch.setenv("FLYWHEEL_LEAN_SANDBOX_MEMORY_MB", "1000")
    doc = bound_check("import Lean\ntheorem t : True := trivial\n", CH)
    assert doc["passed"] is False
    assert doc["sandbox"]["limit_hit"] == "memory"


@live
@windows
def test_live_the_cpu_limit_stops_the_compile(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_LEAN_SANDBOX_CPU_SECONDS", "3")
    spin = ("def loop : Nat → Nat → Nat\n  | 0, a => a\n"
            "  | n+1, a => loop n (a + n % 7)\n#eval loop 4000000000 0\n"
            "theorem t : True := trivial\n")
    doc = bound_check(spin, CH)
    assert doc["passed"] is False
    assert doc["sandbox"]["limit_hit"] == "cpu"
