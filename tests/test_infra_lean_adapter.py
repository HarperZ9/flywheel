"""Tests for the Lean compiler adapter."""
from __future__ import annotations

from pathlib import Path

import pytest

from harness.infra.lean_adapter import (
    SCHEMA,
    LeanCheckResult,
    build_lean_receipt,
    check_lean_file,
    check_lean_source,
    lean_available,
    lean_version,
)


def test_lean_available_returns_bool():
    assert isinstance(lean_available(), bool)


def test_lean_version_returns_string():
    v = lean_version()
    assert isinstance(v, str)
    assert len(v) > 0


def test_check_lean_source_valid_proof():
    """A simple valid Lean proof should type-check."""
    source = """
theorem easy : 1 + 1 = 2 := by simp
"""
    result = check_lean_source(source, timeout=30)
    # Lean may or may not be available on this machine
    if lean_available():
        assert result.verdict == "MATCH"
        assert len(result.file_hash) == 64
    else:
        assert result.verdict == "UNVERIFIABLE"


def test_check_lean_source_invalid_proof():
    """An invalid Lean proof should produce DRIFT."""
    source = """
theorem bad : 1 + 1 = 3 := by simp
"""
    result = check_lean_source(source, timeout=30)
    if lean_available():
        assert result.verdict == "DRIFT"
    else:
        assert result.verdict == "UNVERIFIABLE"


def test_check_lean_file_not_found():
    result = check_lean_file(Path("/nonexistent.lean"))
    assert result.verdict == "UNVERIFIABLE"


def test_check_result_to_measurement():
    r = LeanCheckResult(verdict="MATCH", file_hash="a" * 64,
                        lean_version="lean 4.0.0", elapsed_s=1.5)
    m = r.to_measurement()
    assert m["tool"] == "lean"
    assert m["verdict"] == "MATCH"
    assert m["file_sha256"] == "a" * 64


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
