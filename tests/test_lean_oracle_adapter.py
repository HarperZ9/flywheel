"""LeanOracle adapter falsifier -- the math domain oracle over lean_check.

The adapter reuses lean_check (kernel exit, sorry refusal, axiom-footprint audit).
These tests fix the mapping from that checker's judgment to an OracleResult, and
prove the registry now routes `math` to it. Hermetic: the Lean runner is injected,
so no toolchain is required; the toolchain-missing path is forced deterministically.
"""
from pathlib import Path

import pytest

from harness.lean_oracle import LeanOracle
from harness.oracle_registry import OracleRegistry, default_registry, run_verified
from harness.proposer import StubProposer
from harness.task import load_task

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"


@pytest.fixture
def task(tmp_path):
    return load_task(TASK_DIR, workdir=tmp_path / "w")


def _clean(argv, code):
    return (0, "")


def _error(argv, code):
    return (1, "candidate.lean:1:0: error: unknown identifier 'foo'")


def _forbidden_axiom(argv, code):
    # clean initial check, but the #print axioms audit reveals a smuggled axiom.
    if "#print axioms" in code:
        return (0, "'t' depends on axioms: [sorryAx]")
    return (0, "")


# --- verdict mapping ---------------------------------------------------------

def test_clean_proof_passes(task):
    r = LeanOracle(runner=_clean).verify("example : True := trivial", task)
    assert r.verdict() == "PASS"
    assert r.does_not_prove          # the formalization gap is carried
    assert r.coverage["checker"] == "lean"


def test_error_fails(task):
    r = LeanOracle(runner=_error).verify("example : True := foo", task)
    assert r.verdict() == "FAIL"


def test_sorry_is_refused(task):
    # lean_check refuses admitted holes (hygiene screen and/or kernel warning).
    r = LeanOracle(runner=_clean).verify("theorem t : True := sorry", task)
    assert r.verdict() == "FAIL"


def test_forbidden_axiom_footprint_fails(task):
    # A proof that type-checks but leans on an axiom outside the classical trio
    # must not read as PASS; the adapter carries lean_check's refusal.
    r = LeanOracle(runner=_forbidden_axiom).verify(
        "theorem t : True := by native_decide", task)
    assert r.verdict() == "FAIL"


def test_missing_toolchain_is_unverifiable_environment(task, monkeypatch):
    # No runner injected and no toolchain: UNVERIFIABLE, attributed to the
    # environment, never a candidate FAIL.
    monkeypatch.setattr("harness.lean_oracle._lean_exe", lambda: None)
    r = LeanOracle().verify("example : True := trivial", task)
    assert r.verdict() == "UNVERIFIABLE"
    assert r.unverifiable_reason == "TOOLCHAIN_MISSING"
    assert r.attribution.value == "ENVIRONMENT"


def test_output_hash_is_stable(task):
    a = LeanOracle(runner=_clean).verify("example : True := trivial", task)
    b = LeanOracle(runner=_clean).verify("example : True := trivial", task)
    assert a.output_hash == b.output_hash


# --- registry routing --------------------------------------------------------

def test_default_registry_routes_math_to_lean():
    reg = default_registry()
    assert "math" in reg
    assert reg.resolve("math").oracle_type == "lean"
    assert reg.resolve("theorem") is reg.resolve("math")   # alias
    assert reg.resolve("proof") is reg.resolve("math")


def test_run_verified_math_passes_with_injected_kernel(task, tmp_path):
    reg = OracleRegistry()
    reg.register("math", LeanOracle(runner=_clean))
    v = run_verified(task, StubProposer("example : True := trivial"),
                     domain="math", registry=reg,
                     envelopes_dir=tmp_path / "env", witness_recheck=False)
    assert v.verdict == "PASS"
    assert v.accepted is True
    assert v.domain == "math"


def test_registered_math_without_toolchain_is_unverifiable_not_unavailable(
        task, tmp_path, monkeypatch):
    # The key distinction the registration buys: math is IN SCOPE. Without Lean it
    # answers UNVERIFIABLE (toolchain), not ORACLE_UNAVAILABLE (no oracle).
    monkeypatch.setattr("harness.lean_oracle._lean_exe", lambda: None)
    v = run_verified(task, StubProposer("example : True := trivial"),
                     domain="math", registry=default_registry(),
                     envelopes_dir=tmp_path / "env", witness_recheck=False)
    assert v.verdict == "UNVERIFIABLE"
    assert "ORACLE_UNAVAILABLE" not in v.reason   # the domain IS registered
    assert v.loop is not None                     # a proposal ran; math is in scope
