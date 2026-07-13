"""oracle.py — the verifier adapter (HARNESS.md §verifier-registry).

The oracle is the ONLY thing that accepts. No learned model in the accept path
(C2 invariant). M1 ships PytestOracle; M2 promotes SeedOracle (native, via
aleph/seed) and SandboxedOracle (via state/behavior-transform) by implementing
the same Protocol. A new domain = a new Oracle subclass, same loop.

Determinism contract: output_hash is over CANONICAL content (test outcomes),
never raw stdout — pytest's `N passed in X.XXs` timing line would otherwise
break the receipt chain. canonical_hash() is shared by oracle + witness so a
third party re-running oracle_cmd reproduces the hash.
"""
from __future__ import annotations
import hashlib
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .task import Task

JUNIT_NAME = "_oracle_junit.xml"


def clear_bytecode(workdir: Path) -> None:
    for d in Path(workdir).rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)


def run_env() -> dict:
    return {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill a process AND its descendants. proc.kill() alone is insufficient
    for shell=True on Windows: it terminates cmd.exe while the real workload
    (pytest running a hostile candidate) survives and holds the output pipes."""
    if os.name == "nt":
        subprocess.run(f"taskkill /T /F /PID {proc.pid}", shell=True,
                       capture_output=True, timeout=15)
    else:
        try:
            os.killpg(os.getpgid(proc.pid), 9)
        except Exception:
            proc.kill()


@dataclass
class OracleResult:
    passed: bool
    cmd: str
    output_hash: str
    stdout_excerpt: str
    rc: int

    def verdict(self) -> str:
        return "PASS" if self.passed else "FAIL"


class Oracle(Protocol):
    oracle_type: str

    def verify(self, candidate: str, task: Task) -> OracleResult: ...


def _excerpt(stdout: bytes, n: int = 1200) -> str:
    t = stdout.decode("utf-8", errors="replace")
    return t[-n:] if len(t) > n else t


def _pytest_canonical(workdir: Path) -> str:
    jp = workdir / JUNIT_NAME
    if not jp.exists():
        return ""
    outcomes = []
    for tc in ET.parse(jp).iter("testcase"):
        name = f"{tc.get('classname', '')}::{tc.get('name', '')}"
        if tc.find("failure") is not None or tc.find("error") is not None:
            outcomes.append(f"{name}=FAIL")
        elif tc.find("skipped") is not None:
            outcomes.append(f"{name}=SKIP")
        else:
            outcomes.append(f"{name}=PASS")
    return "\n".join(sorted(outcomes))


def canonical_hash(oracle_type: str, workdir: Path, rc: int) -> str:
    if oracle_type == "pytest":
        canon = _pytest_canonical(workdir)
    else:
        canon = ""
    return hashlib.sha256(f"{canon}\n{rc}".encode()).hexdigest()[:16]


class PytestOracle:
    oracle_type = "pytest"

    def __init__(self, timeout: int = 60, *, cmd_attr: str = "oracle_cmd"):
        self.timeout = timeout
        self.cmd_attr = cmd_attr        # which Task command to run (oracle_cmd | held_out_cmd)

    def _cmd(self, task: Task) -> str:
        return f"{getattr(task, self.cmd_attr)} --junitxml={JUNIT_NAME} -q"

    def verify(self, candidate: str, task: Task) -> OracleResult:
        cpath = task.candidate_full()
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_text(candidate, encoding="utf-8")
        clear_bytecode(Path(task.workdir))
        cmd = self._cmd(task)
        # Popen + tree-kill, NOT subprocess.run(timeout=): with shell=True on
        # Windows, run() kills only cmd.exe on timeout — the pytest grandchild
        # (e.g. a candidate with an infinite loop) survives holding the stdout
        # pipe, and run()'s post-kill drain blocks forever. A hostile candidate
        # must cost one timeout, never a wedged harness.
        out: bytes = b""
        proc = subprocess.Popen(
            cmd, cwd=task.workdir, shell=True, env=run_env(),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            out, _ = proc.communicate(timeout=self.timeout)
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            try:
                out, _ = proc.communicate(timeout=10)
            except Exception:
                out = b""
            rc = 124
        return OracleResult(
            passed=rc == 0, cmd=cmd,
            output_hash=canonical_hash("pytest", Path(task.workdir), rc),
            stdout_excerpt=_excerpt(out), rc=rc)


class StubOracle:
    oracle_type = "stub"

    def __init__(self, passed: bool, stdout: str = ""):
        self._passed = passed
        self._stdout = stdout

    def verify(self, candidate: str, task: Task) -> OracleResult:
        rc = 0 if self._passed else 1
        return OracleResult(
            passed=self._passed, cmd=task.oracle_cmd,
            output_hash=hashlib.sha256(
                f"stub\n{self._passed}\n{rc}".encode()).hexdigest()[:16],
            stdout_excerpt=self._stdout[:1200], rc=rc)
