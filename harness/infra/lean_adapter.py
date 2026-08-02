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


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def lean_available() -> bool:
    """True if the `lean` binary is on PATH."""
    try:
        result = subprocess.run(
            ["lean", "--version"], capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def lean_version() -> str:
    """Return the Lean version string, or 'not installed'."""
    try:
        result = subprocess.run(
            ["lean", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return result.stdout.strip().split("\n")[0]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return "not installed"


@dataclass
class LeanCheckResult:
    """The result of type-checking a Lean file."""
    verdict: str  # MATCH / DRIFT / UNVERIFIABLE
    file_hash: str = ""
    output: str = ""
    error: str = ""
    elapsed_s: float = 0.0
    lean_version: str = ""

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
        }


def check_lean_file(path: Path, *, timeout: int = 60) -> LeanCheckResult:
    """Type-check a Lean file using the `lean` compiler.

    Returns MATCH if the file type-checks successfully, DRIFT if it has errors,
    UNVERIFIABLE if Lean is not installed or the check could not run.
    """
    path = Path(path)
    if not path.exists():
        return LeanCheckResult(verdict=UNVERIFIABLE, error=f"file not found: {path}")

    file_hash = _sha256_hex(path.read_bytes())
    ver = lean_version()

    if not lean_available():
        return LeanCheckResult(
            verdict=UNVERIFIABLE, file_hash=file_hash,
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
        return LeanCheckResult(
            verdict=UNVERIFIABLE, file_hash=file_hash,
            error=f"lean timed out after {timeout}s", lean_version=ver)
    except Exception as e:
        return LeanCheckResult(
            verdict=UNVERIFIABLE, file_hash=file_hash,
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
