"""oracle.py: the verifier adapter (HARNESS.md §verifier-registry).

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
from .verdict import Verdict, Execution, Attribution, is_dispositive, attribution_for

JUNIT_NAME = "_oracle_junit.xml"


def clear_bytecode(workdir: Path) -> None:
    for d in Path(workdir).rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)


# Deny by default. The oracle subprocess executes model-written code, so every
# variable that crosses this boundary is a variable an adversarial candidate can
# read. Add only what an interpreter needs to start.
ENV_ALLOWLIST = frozenset({
    "PATH", "HOME", "USER", "LANG", "LC_ALL", "TZ", "TMPDIR",
    "PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV",
    # Windows loader variables: without these, python.exe does not start.
    "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT",
    "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
    "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS",
})


def run_env(extra: dict | None = None) -> dict:
    """The child's environment: an allowlist, never an inheritance.

    A secret exported in the operator's shell must not be readable by a
    candidate the model wrote. `extra` is the explicit, auditable way to pass
    something in.
    """
    env = {k: v for k, v in os.environ.items() if k in ENV_ALLOWLIST}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if extra:
        env.update(extra)
    return env


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


def spawn_killable(*args, **kwargs) -> subprocess.Popen:
    """Popen whose whole descendant tree `_kill_tree` can actually reap.

    On POSIX the child leads a fresh session, so `os.killpg(getpgid(pid))`
    targets that tree instead of the process group the child would otherwise
    share with the pytest parent. Without it, a hostile candidate's infinite
    loop is a grandchild in pytest's own group: the kill either misses it (it
    survives holding the pipe and the drain wedges) or, worse, signals pytest
    itself. Windows reaps via `taskkill /T` and needs nothing extra. Every
    Popen that is later handed to `_kill_tree` must come through here so the
    kill precondition holds by construction, not by each caller remembering."""
    if os.name != "nt":
        kwargs.setdefault("start_new_session", True)
    return subprocess.Popen(*args, **kwargs)


class NonDispositiveVerdict(Exception):
    """Raised when boolean truth is asked of a verdict that did not decide.

    Returning False here would score an UNDECIDED rollout as a failure, which
    teaches the policy that breaking the verifier is as good as failing it. The
    caller must handle the four-way verdict instead.
    """


class OracleResult:
    """The verifier's answer. Carries a four-way verdict, who caused a
    non-completion, and the raw output hash, while keeping the binary `passed`
    that predates all three."""

    def __init__(self, cmd: str, output_hash: str, stdout_excerpt: str, rc: int,
                 passed: bool | None = None, verdict_: Verdict | str | None = None,
                 execution: Execution | str = Execution.COMPLETED,
                 attribution: Attribution | str | None = None,
                 raw_stdout_sha256: str = "", duration_ns: int = 0,
                 objective: str | None = None,
                 unverifiable_reason: str = "", undecided_reason: str = "",
                 coverage: dict | None = None,
                 does_not_prove: list[str] | None = None):
        if passed is None and verdict_ is None:
            raise ValueError("OracleResult needs either passed= or verdict_=")
        # A non-dispositive verdict must say why. A bare UNVERIFIABLE is
        # indistinguishable from "we did not look".
        self.unverifiable_reason = unverifiable_reason
        self.undecided_reason = undecided_reason
        self.coverage = coverage or {}
        self.does_not_prove = list(does_not_prove or [])
        self.cmd = cmd
        self.output_hash = output_hash
        self.stdout_excerpt = stdout_excerpt
        self.rc = rc
        self.execution = Execution(execution)
        if verdict_ is not None:
            self.verdict_ = Verdict(verdict_)
        else:
            self.verdict_ = Verdict.PASS if passed else Verdict.FAIL
        self.attribution = (Attribution(attribution) if attribution is not None
                            else attribution_for(self.execution))
        self.raw_stdout_sha256 = raw_stdout_sha256
        self.duration_ns = duration_ns
        self.objective = objective

    def __repr__(self) -> str:
        return (f"OracleResult(verdict={self.verdict_.value}, cmd={self.cmd!r}, "
                f"output_hash={self.output_hash!r}, rc={self.rc})")

    def __eq__(self, other) -> bool:
        if not isinstance(other, OracleResult):
            return NotImplemented
        return (self.cmd, self.output_hash, self.stdout_excerpt, self.rc,
                self.verdict_, self.execution, self.attribution) == (
            other.cmd, other.output_hash, other.stdout_excerpt, other.rc,
            other.verdict_, other.execution, other.attribution)

    @property
    def passed(self) -> bool:
        """Binary truth, for the call sites that predate the four-way verdict.
        Raises rather than lying when the verdict did not decide."""
        if not is_dispositive(self.verdict_):
            raise NonDispositiveVerdict(
                f"verdict is {self.verdict_.value}; handle it explicitly "
                f"(attribution={self.attribution.value})")
        return self.verdict_ is Verdict.PASS

    def verdict(self) -> str:
        return self.verdict_.value


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


def _pytest_ran_a_real_pass(workdir: Path) -> bool:
    """True iff the junit record shows at least one testcase that actually
    PASSED. pytest exits 0 when every collected test was SKIPPED, so a green
    exit code alone can mean zero executed assertions; that run verified
    nothing and must not read as a pass."""
    canon = _pytest_canonical(workdir)
    return any(line.endswith("=PASS") for line in canon.splitlines())


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

    def verify_prepared(self, argv: list[str], task: Task,
                        input_refs: list[str]) -> tuple[OracleResult, dict, dict]:
        """Run byte-exact populated inputs through argv, never through a shell."""
        work = Path(task.workdir); snapshots = {}; clear_bytecode(work)
        for ref in input_refs:
            with (work / ref).open("rb") as stream:
                blob = stream.read(1_048_577)
            if len(blob) > 1_048_576:
                raise ValueError("prepared pytest input exceeds byte limit")
            snapshots[ref] = (blob, "sha256:" + hashlib.sha256(blob).hexdigest())
        proc = spawn_killable([*argv, f"--junitxml={JUNIT_NAME}", "-q"], cwd=work,
            shell=False, env=run_env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            proc.communicate(timeout=self.timeout); rc = proc.returncode
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            try: proc.communicate(timeout=10)
            except Exception: pass
            rc = 124
        canonical = _pytest_canonical(work)
        command = {"args": ["python", "-m", "pytest", *argv[3:]],
            "targets": list(dict.fromkeys(arg.split("::", 1)[0] for arg in argv[3:]))}
        artifact = {"schema": "flywheel.pytest-result/v1", "command": command,
            "inputs": [{"ref": ref, "sha256": claimed, "bytes": len(blob)}
                       for ref, (blob, claimed) in snapshots.items()],
            "outcomes": canonical.splitlines(), "return_code": rc}
        result = OracleResult(passed=rc == 0 and _pytest_ran_a_real_pass(work), cmd="",
            output_hash=canonical_hash("pytest", work, rc), stdout_excerpt="", rc=rc)
        return result, artifact, snapshots

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
        proc = spawn_killable(
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
            passed=rc == 0 and _pytest_ran_a_real_pass(Path(task.workdir)),
            cmd=cmd,
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
