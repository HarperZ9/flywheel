"""oracle_registry falsifier -- the routing that makes one loop span every domain.

The claims, each with a test that fails if it is false:
  - a registered domain resolves to its oracle and drives the loop to a verdict;
  - an UNregistered domain returns UNVERIFIABLE, not a fabricated PASS/FAIL, and
    spends no proposal;
  - the honest-null carries a reason and a does_not_prove, never a bare verdict;
  - aliases resolve to the canonical domain;
  - registering a new domain oracle extends coverage without touching the loop.
"""
from pathlib import Path

import pytest

from harness.oracle import StubOracle
from harness.oracle_registry import (
    EngineVerdict, OracleRegistry, canonical_domain, default_registry,
    run_verified, unverifiable_result)
from harness.proposer import StubProposer
from harness.task import load_task

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"
CORRECT = "def add(a, b):\n    return a + b\n"


@pytest.fixture
def task(tmp_path):
    return load_task(TASK_DIR, workdir=tmp_path / "w")


# --- registry mechanics ------------------------------------------------------

def test_default_registry_has_the_code_domain():
    reg = default_registry()
    assert "code" in reg
    assert reg.resolve("code") is not None
    assert reg.resolve("code").oracle_type == "pytest"


def test_aliases_resolve_to_canonical_domain():
    assert canonical_domain("python") == "code"
    assert canonical_domain("pytest") == "code"
    assert canonical_domain("Proof") == "math"
    assert canonical_domain("MEASUREMENT") == "ml"
    reg = default_registry()
    assert reg.resolve("python") is reg.resolve("code")


def test_register_extends_coverage():
    reg = default_registry()
    assert "biology" not in reg
    reg.register("biology", StubOracle(True), does_not_prove=("in vitro only",))
    assert "biology" in reg
    assert reg.resolve("biology") is not None
    assert "biology" in reg.domains()


def test_empty_domain_name_is_rejected():
    reg = OracleRegistry()
    with pytest.raises(ValueError):
        reg.register("   ", StubOracle(True))


# --- the entrypoint: registered domain drives the loop ----------------------

def test_registered_domain_drives_loop_to_pass(task, tmp_path):
    reg = OracleRegistry()
    reg.register("code", StubOracle(True))
    v = run_verified(task, StubProposer(CORRECT), domain="code", registry=reg,
                     envelopes_dir=tmp_path / "env", witness_recheck=False)
    assert isinstance(v, EngineVerdict)
    assert v.verdict == "PASS"
    assert v.accepted is True
    assert v.domain == "code"
    assert v.loop is not None


def test_registered_domain_carries_fail(task, tmp_path):
    reg = OracleRegistry()
    reg.register("code", StubOracle(False))
    v = run_verified(task, StubProposer(CORRECT), domain="code", registry=reg,
                     envelopes_dir=tmp_path / "env", witness_recheck=False)
    assert v.verdict == "FAIL"
    assert v.accepted is False


# --- the honest null: unregistered domain never fabricates a verdict --------

def test_unregistered_domain_is_unverifiable_not_pass(task, tmp_path):
    reg = default_registry()   # has code, not chemistry
    v = run_verified(task, StubProposer(CORRECT), domain="chemistry",
                     registry=reg, envelopes_dir=tmp_path / "env")
    assert v.verdict == "UNVERIFIABLE"
    assert v.accepted is False
    assert v.verdict not in ("PASS", "FAIL")


def test_unverifiable_states_reason_and_available_domains(task, tmp_path):
    reg = default_registry()
    v = run_verified(task, StubProposer(CORRECT), domain="chemistry",
                     registry=reg, envelopes_dir=tmp_path / "env")
    assert "ORACLE_UNAVAILABLE" in v.reason
    assert "code" in v.reason            # tells the caller what IS available
    assert v.does_not_prove              # carries an honest does-not-prove
    assert v.loop is None                # no proposal was spent


def test_unverifiable_result_object_is_not_dispositive(task):
    r = unverifiable_result("chemistry", task)
    assert r.verdict() == "UNVERIFIABLE"
    assert r.unverifiable_reason == "ORACLE_UNAVAILABLE"
    assert r.does_not_prove
    with pytest.raises(Exception):
        _ = r.passed   # a non-dispositive verdict must refuse boolean coercion


def test_trace_is_serializable_and_leaks_no_candidate(task, tmp_path):
    import json
    reg = default_registry()
    v = run_verified(task, StubProposer(CORRECT), domain="chemistry",
                     registry=reg, envelopes_dir=tmp_path / "env")
    trace = v.to_trace()
    assert json.dumps(trace)
    assert trace["verdict"] == "UNVERIFIABLE"
    assert trace["accepted"] is False
