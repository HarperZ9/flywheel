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


def test_sorry_is_refused_before_the_kernel_runs():
    """Lean exits 0 on `sorry` with only a warning, so a false statement
    wearing an admitted hole would pass a naive exit-code check. The
    oracle must refuse admitted holes and smuggled axioms outright, and
    say why. Found live on 2026-07-14: the pre-fix oracle accepted
    `n + 0 = n + 1 := by sorry`."""
    hole = "theorem hole (n : Nat) : n + 0 = n + 1 := by sorry\n"
    doc = lean_check(hole, runner=lambda argv, code: (0, ""))
    assert doc["passed"] is False
    assert "sorry" in doc["kernel_output"]
    ax = "axiom bad : 1 = 2\ntheorem t : 1 = 2 := bad\n"
    doc2 = lean_check(ax, runner=lambda argv, code: (0, ""))
    assert doc2["passed"] is False
    assert "axiom" in doc2["kernel_output"]


def test_sorry_warning_in_kernel_output_is_refused_belt_and_braces():
    # even if the text sneaks past the screen, the kernel's own warning
    # is treated as refusal
    doc = lean_check("theorem t : True := trivial",
                     runner=lambda argv, code:
                     (0, "warning: declaration uses `sorry`"))
    assert doc["passed"] is False


@pytest.mark.skipif(not lean_available(), reason="lean toolchain not installed")
def test_live_kernel_refuses_a_sorry_hole():
    doc = lean_check("theorem hole (n : Nat) : n + 0 = n + 1 := by sorry\n")
    assert doc["passed"] is False, doc


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


def test_admit_and_kernel_bypass_are_refused_before_the_kernel():
    for code in (
        "theorem t (n : Nat) : n = n + 1 := by admit",
        "theorem t : False := sorryAx False true",
        "theorem t : (2:Nat)=2 := by native_decide",
        "set_option debug.skipKernelTC true\ntheorem t : False := rfl",
    ):
        doc = lean_check(code, runner=lambda argv, c: (0, ""))
        assert doc["passed"] is False, code


def test_single_quoted_sorry_warning_is_refused_belt_and_braces():
    doc = lean_check("theorem t : True := trivial",
                     runner=lambda argv, c:
                     (0, "warning: declaration uses 'sorry'"))
    assert doc["passed"] is False


def _audit_runner(footprint_line: str):
    """First call judges the candidate clean; the audit call (the code carries
    #print axioms) answers with the given footprint line."""
    def run(argv, code):
        if "#print axioms" in code:
            return 0, footprint_line
        return 0, ""
    return run


def test_forbidden_axiom_footprint_is_refused_after_accept():
    # A compiled-evaluation escape type-checks to rc==0 with no sorry warning;
    # only the axiom footprint betrays it (Lean.ofReduceBool). The oracle must
    # ask and refuse.
    doc = lean_check(GOOD, runner=_audit_runner(
        "'one_plus_one' depends on axioms: [Lean.ofReduceBool]"))
    assert doc["passed"] is False
    assert "ofReduceBool" in doc["kernel_output"]


def test_classical_trio_footprint_is_accepted_and_carried():
    doc = lean_check(GOOD, runner=_audit_runner(
        "'one_plus_one' depends on axioms: [propext, Classical.choice, Quot.sound]"))
    assert doc["passed"] is True
    assert doc["axiom_footprint"] == {
        "one_plus_one": ["propext", "Classical.choice", "Quot.sound"]}


def test_audit_run_failure_fail_closes():
    def run(argv, code):
        if "#print axioms" in code:
            return 1, "unknown constant"
        return 0, ""
    doc = lean_check(GOOD, runner=run)
    assert doc["passed"] is False
    assert "footprint" in doc["kernel_output"]


@pytest.mark.skipif(not lean_available(), reason="lean toolchain not installed")
def test_live_kernel_reports_the_axiom_footprint():
    doc = lean_check(GOOD)
    assert doc["passed"] is True, doc["kernel_output"]
    assert "one_plus_one" in doc["axiom_footprint"]
