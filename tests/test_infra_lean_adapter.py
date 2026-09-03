"""Tests for the Lean compiler adapter.

The interesting property here is load-invariance. An earlier version of the
two proof tests asserted MATCH whenever the compiler was present, so a busy
machine turned a sound proof into a failing test: three `lean` subprocesses
per check, each with a timeout of its own, against pytest's 60-second
ceiling. A verdict that moves with machine load is a defect by this repo's
own standard, so the adapter now names why a check produced no verdict and
these tests assert on what holds either way.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from harness.infra import lean_adapter as la
from harness.infra.lean_adapter import (
    REASON_NONE,
    REASON_NOT_INSTALLED,
    REASON_TIMEOUT,
    SCHEMA,
    LeanCheckResult,
    build_lean_receipt,
    check_lean_file,
    check_lean_source,
    lean_available,
    lean_version,
)

VALID_PROOF = """
theorem easy : 1 + 1 = 2 := by simp
"""

INVALID_PROOF = """
theorem bad : 1 + 1 = 3 := by simp
"""


def _fake_version(cmd, **_kw):
    return subprocess.CompletedProcess(
        cmd, 0, stdout="Lean (version 4.0.0)\n", stderr="")


def test_lean_available_returns_bool():
    assert isinstance(lean_available(), bool)


def test_lean_version_returns_string():
    v = lean_version()
    assert isinstance(v, str)
    assert len(v) > 0


def test_one_subprocess_answers_both_probe_questions(monkeypatch):
    """The cost that caused the flake. `check_lean_file` asked `lean --version`
    twice, through `lean_version` and again through `lean_available`, and the
    test asked a third time. Three extra timeouts around one proof is what
    collided with parallel workers, so the probe runs once per process."""
    la.reset_lean_probe()
    calls: list = []

    def counting_run(cmd, **kw):
        calls.append(cmd)
        return _fake_version(cmd, **kw)

    monkeypatch.setattr(la.subprocess, "run", counting_run)
    try:
        assert la.lean_available() is True
        assert la.lean_version().startswith("Lean")
        assert la.lean_available() is True
        assert len(calls) == 1, f"probed {len(calls)} times, not once"
    finally:
        la.reset_lean_probe()


def test_a_timeout_is_named_as_a_timeout(monkeypatch, tmp_path):
    """UNVERIFIABLE has several causes and they are not interchangeable. Only
    a timeout moves with load, so only a timeout may be tolerated by a test
    without the test going vacuous."""
    src = tmp_path / "slow.lean"
    src.write_text("theorem t : 1 + 1 = 2 := by simp\n", encoding="utf-8")
    la.reset_lean_probe()

    def timing_out_run(cmd, **kw):
        if "--version" in cmd:
            return _fake_version(cmd, **kw)
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 0))

    monkeypatch.setattr(la.subprocess, "run", timing_out_run)
    try:
        result = check_lean_file(src, timeout=1)
    finally:
        la.reset_lean_probe()
    assert result.verdict == "UNVERIFIABLE"
    assert result.reason == REASON_TIMEOUT
    assert result.to_measurement()["reason"] == REASON_TIMEOUT
    assert len(result.file_hash) == 64, "the artifact was read, so it hashes"


def test_an_absent_compiler_is_named_as_absent(monkeypatch, tmp_path):
    """The other half of the distinction: no compiler is a fact about the
    machine and never becomes MATCH by waiting longer."""
    src = tmp_path / "p.lean"
    src.write_text("theorem t : True := trivial\n", encoding="utf-8")
    la.reset_lean_probe()
    monkeypatch.setattr(
        la.subprocess, "run",
        lambda cmd, **kw: (_ for _ in ()).throw(FileNotFoundError("lean")))
    try:
        result = check_lean_file(src, timeout=5)
    finally:
        la.reset_lean_probe()
    assert result.verdict == "UNVERIFIABLE"
    assert result.reason == REASON_NOT_INSTALLED
    assert result.lean_version == la.NOT_INSTALLED


def test_a_valid_proof_never_reads_as_drift():
    """What holds regardless of load: a sound proof is never called unsound.
    A check that finishes says MATCH; a check that runs out of budget says so
    by name rather than by silence."""
    result = check_lean_source(VALID_PROOF, timeout=30)
    assert result.verdict != "DRIFT"
    if not lean_available():
        assert result.verdict == "UNVERIFIABLE"
        assert result.reason == REASON_NOT_INSTALLED
        return
    assert len(result.file_hash) == 64
    if result.reason == REASON_TIMEOUT:
        assert result.verdict == "UNVERIFIABLE"
    else:
        assert result.verdict == "MATCH"
        assert result.reason == REASON_NONE


def test_an_invalid_proof_never_reads_as_match():
    """The mirror. An unsound proof is never called sound, whatever the load."""
    result = check_lean_source(INVALID_PROOF, timeout=30)
    assert result.verdict != "MATCH"
    if not lean_available():
        assert result.verdict == "UNVERIFIABLE"
        assert result.reason == REASON_NOT_INSTALLED
        return
    if result.reason == REASON_TIMEOUT:
        assert result.verdict == "UNVERIFIABLE"
    else:
        assert result.verdict == "DRIFT"


def test_check_lean_file_not_found():
    result = check_lean_file(Path("/nonexistent.lean"))
    assert result.verdict == "UNVERIFIABLE"
    assert result.reason == la.REASON_FILE_MISSING


def test_check_result_to_measurement():
    r = LeanCheckResult(verdict="MATCH", file_hash="a" * 64,
                        lean_version="lean 4.0.0", elapsed_s=1.5)
    m = r.to_measurement()
    assert m["tool"] == "lean"
    assert m["verdict"] == "MATCH"
    assert m["file_sha256"] == "a" * 64
    assert m["reason"] == REASON_NONE


def test_build_lean_receipt_sealed():
    r = LeanCheckResult(verdict="MATCH", file_hash="b" * 64,
                        lean_version="lean 4.0.0", elapsed_s=2.0)
    receipt = build_lean_receipt(r, claim="1+1=2", run_id="test")
    assert receipt["schema"] == SCHEMA
    assert len(receipt["seal_hash"]) == 64
    assert receipt["seal_body"]["verdict"] == "MATCH"
    assert receipt["seal_body"]["claim"] == "1+1=2"


def test_build_lean_receipt_measurement_present():
    r = LeanCheckResult(verdict="DRIFT", file_hash="c" * 64,
                        error="type mismatch")
    receipt = build_lean_receipt(r)
    assert "measurement" in receipt["seal_body"]
    assert receipt["seal_body"]["measurement"]["verdict"] == "DRIFT"
