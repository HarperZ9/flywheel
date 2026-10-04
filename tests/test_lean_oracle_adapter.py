"""LeanOracle adapter falsifier -- the math domain oracle over the bound check.

The adapter judges a candidate against the statement its task pinned
(harness/lean_binding.py). These tests fix the mapping from that judgment to an
OracleResult, and prove the registry routes `math` to it. Hermetic: the Lean
runner is injected, so no toolchain is required; the toolchain-missing path is
forced deterministically. The live negative probes are in
tests/test_lean_binding_live.py.
"""
import json
from pathlib import Path

import pytest

from harness.lean_oracle import LeanOracle
from harness.oracle_registry import OracleRegistry, default_registry, run_verified
from harness.proposer import StubProposer
from harness.task import load_task

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"


CH = {"theorem": "t", "statement": "True"}


def _bind(axioms=(), status="bound", refusals=()):
    return json.dumps({"status": status, "theorem": "t",
                       "statement_canonical": "t.[] : True",
                       "axioms": list(axioms), "refusals": list(refusals),
                       "lean_version": "4.34.1", "lean_githash": "injected"})


@pytest.fixture
def task(tmp_path):
    t = load_task(TASK_DIR, workdir=tmp_path / "w")
    t.challenge = dict(CH)
    return t


@pytest.fixture
def unpinned(tmp_path):
    return load_task(TASK_DIR, workdir=tmp_path / "u")


def _clean(argv, code):
    return (0, _bind()) if "--run" in argv else (0, "")


def _error(argv, code):
    return (1, "candidate.lean:1:0: error: unknown identifier 'foo'")


def _forbidden_axiom(argv, code):
    # the compile accepts, but the artifact axiom walk finds a smuggled axiom.
    return (0, _bind(axioms=["sorryAx"])) if "--run" in argv else (0, "")


def _refused(argv, code):
    if "--run" in argv:
        return 0, _bind(status="refused",
                        refusals=["the candidate declares no top-level t"])
    return (0, "")


# --- verdict mapping ---------------------------------------------------------

def test_clean_proof_passes(task):
    r = LeanOracle(runner=_clean).verify("theorem t : True := trivial", task)
    assert r.verdict() == "PASS"
    assert r.does_not_prove          # the formalization gap is carried
    assert r.coverage["checker"] == "lean"
    assert r.coverage["statement_binding"] == "pinned"
    assert r.coverage["spec_fidelity"]["status"] == "UNVERIFIED"
    assert len(r.coverage["statement_sha256"]) == 64


def test_unpinned_task_is_never_a_pass(unpinned):
    # The 2026-09-23 defect: example_pass asks for Python, pins no theorem,
    # and an unrelated closed theorem used to earn PASS here.
    r = LeanOracle(runner=_clean).verify("theorem unrelated : True := trivial",
                                         unpinned)
    assert r.verdict() == "UNVERIFIABLE"
    assert r.unverifiable_reason == "SPECIFICATION_UNPINNED"
    assert r.attribution.value == "HARNESS"


def test_unpinned_task_runs_no_lean_at_all(unpinned):
    calls = []
    LeanOracle(runner=lambda a, c: calls.append(a) or (0, "")).verify(
        "theorem t : True := trivial", unpinned)
    assert calls == []


def test_binding_refusal_fails_and_names_why(task):
    r = LeanOracle(runner=_refused).verify(
        "theorem unrelated : True := trivial", task)
    assert r.verdict() == "FAIL"
    assert "declares no top-level t" in r.stdout_excerpt
    assert r.coverage["binding"]["status"] == "refused"


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
        "theorem t : True := trivial", task)
    assert r.verdict() == "FAIL"
    assert "sorryAx" in r.stdout_excerpt


def test_missing_toolchain_is_unverifiable_environment(task, monkeypatch):
    # No runner injected and no toolchain: UNVERIFIABLE, attributed to the
    # environment, never a candidate FAIL.
    monkeypatch.setattr("harness.lean_oracle._lean_exe", lambda: None)
    r = LeanOracle().verify("example : True := trivial", task)
    assert r.verdict() == "UNVERIFIABLE"
    assert r.unverifiable_reason == "TOOLCHAIN_MISSING"
    assert r.attribution.value == "ENVIRONMENT"


def test_output_hash_is_stable(task):
    a = LeanOracle(runner=_clean).verify("theorem t : True := trivial", task)
    b = LeanOracle(runner=_clean).verify("theorem t : True := trivial", task)
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
    v = run_verified(task, StubProposer("theorem t : True := trivial"),
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
