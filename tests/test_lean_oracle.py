"""The apex oracle: the Lean kernel decides, nothing else. A passing proof
is a receipt anyone can re-run; a failing one carries the kernel's own
words; a missing toolchain is a named DECLARED state, never a fake pass.
The live smoke tests run only when the kernel is actually present."""

import pytest

from harness.lean_oracle import SCHEMA, lean_available, lean_check

GOOD = "theorem one_plus_one : 1 + 1 = 2 := rfl\n"
BAD = "theorem one_plus_one : 1 + 1 = 3 := rfl\n"


def test_injected_kernel_verdicts_shape_the_receipt():
    doc = lean_check(GOOD, runner=lambda argv, code: (0, ""))
    assert doc["schema"] == SCHEMA
    assert doc["passed"] is True
    assert len(doc["code_sha256"]) == 64
    fail = lean_check(BAD, runner=lambda argv, code: (1, "type mismatch"))
    assert fail["passed"] is False
    assert "type mismatch" in fail["kernel_output"]


def test_missing_toolchain_is_declared_not_faked(monkeypatch):
    import harness.lean_oracle as lo
    monkeypatch.setattr(lo, "_lean_exe", lambda: None)
    doc = lean_check(GOOD)
    assert doc["passed"] is None
    assert "toolchain" in doc["kernel_output"]


@pytest.mark.skipif(not lean_available(), reason="lean toolchain not installed")
def test_live_kernel_accepts_a_true_theorem():
    doc = lean_check(GOOD)
    assert doc["passed"] is True, doc["kernel_output"]
    assert doc["toolchain"].startswith("Lean")


@pytest.mark.skipif(not lean_available(), reason="lean toolchain not installed")
def test_live_kernel_refuses_a_false_theorem():
    doc = lean_check(BAD)
    assert doc["passed"] is False
    assert doc["kernel_output"], "the kernel must say why"
