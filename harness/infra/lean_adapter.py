"""lean_adapter.py -- Lean compiler integration for crucible.

A measurement adapter that runs `lean` over a proof artifact and emits a
crucible-compatible measurement. This closes the ten-proofs verification gap:
a mathematical claim paired with a Lean proof becomes a crucible thesis whose
measurement is the type-check result.

The adapter is a stdlib-only subprocess wrapper. It does not import Lean; it
shells out to the `lean` binary. If Lean is not installed, the adapter returns
UNVERIFIABLE (never a silent pass).

Schema: flywheel.lean-check/v1. Sealed.
"""
from __future__ import annotations

import functools
import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA = "flywheel.lean-check/v1"

MATCH = "MATCH"
DRIFT = "DRIFT"
UNVERIFIABLE = "UNVERIFIABLE"

NOT_INSTALLED = "not installed"

# Why a check produced no verdict. UNVERIFIABLE is honest but silent about its
# cause, and the causes are not interchangeable: an absent compiler is a fact
# about the machine, a timeout is a fact about the budget, and only the second
# one moves with load. A caller that cannot tell them apart has to guess, and a
# test that guesses becomes load-dependent.
REASON_NONE = ""
REASON_NOT_INSTALLED = "lean-not-installed"
REASON_TIMEOUT = "lean-timed-out"
REASON_FILE_MISSING = "file-not-found"
REASON_ERROR = "check-failed"


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


@functools.lru_cache(maxsize=1)
def _probe_lean() -> str:
    """One `lean --version` per process.

    A check used to spawn this twice, once through `lean_version` and again
    through `lean_available`, and each spawn carries a timeout of its own.
    Three subprocesses to type-check one small file is how a 30-second proof
    budget reached pytest's 60-second ceiling under parallel workers.
    """
    try:
        result = subprocess.run(
            ["lean", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return result.stdout.strip().split("\n")[0]
    except (OSError, subprocess.SubprocessError):
        pass
    return NOT_INSTALLED


def reset_lean_probe() -> None:
    """Drop the memoized probe, for a caller that changes what is installed."""
    _probe_lean.cache_clear()


def lean_available() -> bool:
    """True if the `lean` binary is on PATH. Shares one probe with
    `lean_version`, so asking both costs one subprocess rather than two."""
    return _probe_lean() != NOT_INSTALLED


def lean_version() -> str:
    """Return the Lean version string, or 'not installed'."""
    return _probe_lean()


@dataclass
class LeanCheckResult:
    """The result of type-checking a Lean file."""
    verdict: str  # MATCH / DRIFT / UNVERIFIABLE
    file_hash: str = ""
    output: str = ""
    error: str = ""
    elapsed_s: float = 0.0
    lean_version: str = ""
    reason: str = REASON_NONE

    def to_measurement(self) -> dict[str, Any]:
        """Convert to a crucible-compatible measurement dict."""
        return {
            "tool": "lean",
            "verdict": self.verdict,
            "file_sha256": self.file_hash,
            "lean_version": self.lean_version,
            "elapsed_s": round(self.elapsed_s, 3),
            "output_excerpt": self.output[:500] if self.output else "",
            "error_excerpt": self.error[:500] if self.error else "",
            "reason": self.reason,
        }


def check_lean_file(path: Path, *, timeout: int = 60) -> LeanCheckResult:
    """Type-check a Lean file using the `lean` compiler.

    Returns MATCH if the file type-checks successfully, DRIFT if it has errors,
    UNVERIFIABLE if Lean is not installed or the check could not run.
    """
    path = Path(path)
    if not path.exists():
        return LeanCheckResult(verdict=UNVERIFIABLE, reason=REASON_FILE_MISSING,
                               error=f"file not found: {path}")

    file_hash = _sha256_hex(path.read_bytes())
    ver = lean_version()

    if ver == NOT_INSTALLED:
        return LeanCheckResult(
            verdict=UNVERIFIABLE, file_hash=file_hash,
            reason=REASON_NOT_INSTALLED,
            error="lean binary not found on PATH", lean_version=ver)

    import time
    start = time.monotonic()
    try:
        result = subprocess.run(
            ["lean", str(path)],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(path.parent),
        )
        elapsed = time.monotonic() - start
        if result.returncode == 0:
            return LeanCheckResult(
                verdict=MATCH, file_hash=file_hash,
                output=result.stdout, elapsed_s=elapsed, lean_version=ver)
        return LeanCheckResult(
            verdict=DRIFT, file_hash=file_hash,
            output=result.stdout, error=result.stderr,
            elapsed_s=elapsed, lean_version=ver)
    except subprocess.TimeoutExpired:
        # The budget ran out, which says nothing about the proof. The reason
        # travels with the verdict so a reader cannot mistake a busy machine
        # for an unsound argument.
        return LeanCheckResult(
            verdict=UNVERIFIABLE, file_hash=file_hash, reason=REASON_TIMEOUT,
            elapsed_s=time.monotonic() - start,
            error=f"lean timed out after {timeout}s", lean_version=ver)
    except Exception as e:
        return LeanCheckResult(
            verdict=UNVERIFIABLE, file_hash=file_hash, reason=REASON_ERROR,
            error=str(e), lean_version=ver)


def check_lean_source(source: str, *, timeout: int = 60) -> LeanCheckResult:
    """Type-check Lean source code from a string.

    Writes the source to a temporary file and runs `lean` on it.
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".lean", delete=False, encoding="utf-8"
    ) as f:
        f.write(source)
        f.flush()
        tmp_path = Path(f.name)
    try:
        return check_lean_file(tmp_path, timeout=timeout)
    finally:
        tmp_path.unlink(missing_ok=True)


def build_lean_receipt(result: LeanCheckResult, *,
                       claim: str = "", source_hash: str = "",
                       run_id: str = "lean-check") -> dict[str, Any]:
    """Build a sealed Lean check receipt."""
    seal_body = {
        "run_id": run_id,
        "claim": claim,
        "source_hash": source_hash or result.file_hash,
        "verdict": result.verdict,
        "lean_version": result.lean_version,
        "elapsed_s": round(result.elapsed_s, 3),
        "measurement": result.to_measurement(),
    }
    seal_hash = _sha256_hex(_canonical_bytes(seal_body))
    return {"schema": SCHEMA, "seal_hash": seal_hash, "seal_body": seal_body}
