"""Parent-side scoring shell for verifiers-component-forge.

One job: execute an agent-emitted module in an isolated child interpreter and
bring back JSON results for parent-side comparison against frozen expectations.
Oracle values never enter the child: not its argv, not its environment, not its
stdin, not its filesystem view. The child sees the module source and the case
INPUTS only; every comparison happens here, in the parent.

Isolation posture (documented honestly): ``-I`` strips user site-packages and
environment hooks, so the parent injects the resolved paths verifiers actually
needs via a generated bootstrap ``sys.path`` prelude. The child runs with a
scrubbed environment, its cwd inside a fresh temp dir, a wall-clock kill on the
whole process group, and POSIX rlimits where the platform has them (best-effort
elsewhere; Windows gets the wall clock and job-free kill only). This is a
determinism-and-hygiene boundary, not a security sandbox, and the README says
so.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import sysconfig
import tempfile
from dataclasses import dataclass
from pathlib import Path

WALL_CLOCK_SECONDS = 30.0
MAX_STDOUT_BYTES = 8 * 1024 * 1024

_HARNESS_DIR = Path(__file__).resolve().parent


def _verifiers_sys_paths() -> list[str]:
    """The sys.path entries a ``python -I`` child needs to import verifiers.

    ``-I`` drops site-packages, which is the point: the child inherits ONLY
    what is resolved here, from the parent's own environment, so the import
    surface is explicit and testable.
    """
    import verifiers  # resolved in the parent's environment

    verifiers_root = str(Path(verifiers.__file__).resolve().parent.parent)
    paths = [verifiers_root]
    # verifiers' own dependency closure lives in the same site-packages in
    # every supported install (uv venv, pip venv); purelib covers both.
    purelib = sysconfig.get_paths().get("purelib")
    if purelib and purelib not in paths:
        paths.append(purelib)
    return paths


def _scrubbed_env() -> dict[str, str]:
    """A minimal child environment: no keys, no proxies, no user hooks."""
    keep = ("SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "PATHEXT")
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


@dataclass(frozen=True)
class ChildResult:
    """What came back from one child run."""

    ok: bool
    payload: dict | None  # parsed JSON from the child when ok
    failure: str | None  # "timeout" | "bad-exit:<code>" | "bad-json" | "oversize"
    stderr_tail: str


async def run_child(
    driver: str,
    module_source: str,
    inputs: object,
    *,
    wall_clock: float = WALL_CLOCK_SECONDS,
) -> ChildResult:
    """Run one child driver over one agent module with the given case inputs.

    ``driver`` is the filename of a child driver colocated with this module
    (e.g. ``child_driver_rubric.py``). The child receives one JSON document on
    stdin: ``{"module_source": ..., "inputs": ..., "sys_paths": [...]}`` and
    must emit exactly one JSON document on stdout. Anything else is a failure
    of that probe, never of the harness.
    """
    driver_path = _HARNESS_DIR / driver
    if not driver_path.is_file():
        raise FileNotFoundError(f"unknown child driver: {driver}")

    request = json.dumps(
        {
            "module_source": module_source,
            "inputs": inputs,
            "sys_paths": _verifiers_sys_paths(),
        }
    ).encode("utf-8")

    with tempfile.TemporaryDirectory(prefix="vcf-") as tmp:
        creationflags = 0
        preexec_fn = None
        if os.name == "posix":
            preexec_fn = os.setsid  # own process group for group-kill
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            str(driver_path),
            cwd=tmp,
            env=_scrubbed_env(),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            preexec_fn=preexec_fn,
            creationflags=creationflags,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(request), timeout=wall_clock
            )
        except TimeoutError:
            _kill_hard(proc)
            await proc.wait()
            return ChildResult(False, None, "timeout", "")

    tail = stderr[-2000:].decode("utf-8", errors="replace") if stderr else ""
    if len(stdout) > MAX_STDOUT_BYTES:
        return ChildResult(False, None, "oversize", tail)
    if proc.returncode != 0:
        return ChildResult(False, None, f"bad-exit:{proc.returncode}", tail)
    try:
        payload = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ChildResult(False, None, "bad-json", tail)
    if not isinstance(payload, dict):
        return ChildResult(False, None, "bad-json", tail)
    return ChildResult(True, payload, None, tail)


def _kill_hard(proc: asyncio.subprocess.Process) -> None:
    """Kill the child and, on POSIX, its whole process group."""
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        else:
            proc.kill()
    except (ProcessLookupError, PermissionError, OSError):
        pass


def coerce_result_value(value: object) -> object:
    """Normalize one child-reported result for comparison.

    JSON round-tripping already guarantees plain types end-to-end (a str
    subclass with a lying ``__eq__`` cannot survive serialization), so this
    only needs to canonicalize floats that JSON preserves exactly.
    """
    if isinstance(value, str):
        return str(value)
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, list):
        return [coerce_result_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): coerce_result_value(v) for k, v in value.items()}
    return value


def match_fraction(
    results: list[object],
    expectations: list[object],
    weights: list[float] | None = None,
    *,
    float_tolerance: float = 1e-9,
) -> float:
    """Weighted fraction of probes whose result matches its expectation.

    A missing/errored probe (child crash, timeout, per-probe exception marker)
    simply fails that probe. Weights default to uniform.
    """
    if len(results) != len(expectations):
        raise ValueError("results and expectations must align")
    if weights is None:
        weights = [1.0] * len(expectations)
    if len(weights) != len(expectations):
        raise ValueError("weights must align with expectations")
    total = sum(weights)
    if total <= 0:
        raise ValueError("weights must sum to a positive value")
    earned = 0.0
    for got, want, w in zip(results, expectations, weights):
        if _values_match(
            coerce_result_value(got), coerce_result_value(want), float_tolerance
        ):
            earned += w
    return earned / total


def _values_match(got: object, want: object, tol: float) -> bool:
    if isinstance(want, float) and isinstance(got, float):
        return abs(got - want) <= tol
    if isinstance(want, list) and isinstance(got, list):
        return len(got) == len(want) and all(
            _values_match(g, w, tol) for g, w in zip(got, want)
        )
    if isinstance(want, dict) and isinstance(got, dict):
        return got.keys() == want.keys() and all(
            _values_match(got[k], want[k], tol) for k in want
        )
    return got == want
