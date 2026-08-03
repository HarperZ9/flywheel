"""Falsifier for the ml measurement-gate oracle (harness/measurement_oracle.py).

The empirical thesis, verified locally: a measurement claim is accepted ONLY if
its interval clears the registered minimum, its negative control holds at zero,
and its sample clears the registered minimum size. A claim that clears with a
null control passes; an effect below the minimum, or a significant negative
control, or too small an n, fails; and a claim missing its denominator (no n, no
interval) is UNVERIFIABLE, never a fabricated FAIL. The oracle then routes under
the ml domain and drives the same loop as every other oracle.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.measurement_oracle import MeasurementOracle, evaluate_claim
from harness.oracle_registry import (
    OracleRegistry, default_registry, run_verified, canonical_domain,
)
from harness.proposer import StubProposer
from harness.task import Task
from harness.verdict import Verdict, Execution, UnverifiableReason


# --- claim builders ----------------------------------------------------------

def _clean(**over) -> str:
    """A clean claim: interval clears min_effect, control holds at zero, big n."""
    claim = {
        "effect": 0.42, "ci_low": 0.30, "ci_high": 0.54,
        "min_effect": 0.10, "n": 500,
        "negative_control": {"effect": 0.01, "ci_low": -0.05, "ci_high": 0.07},
    }
    claim.update(over)
    return json.dumps(claim)


def _below_min() -> str:
    # ci_low (0.05) does not clear min_effect (0.10)
    return _clean(effect=0.08, ci_low=0.05, ci_high=0.11)


def _significant_control() -> str:
    # the placebo interval excludes zero -> a confound is present
    return json.dumps({
        "effect": 0.42, "ci_low": 0.30, "ci_high": 0.54,
        "min_effect": 0.10, "n": 500,
        "negative_control": {"effect": 0.20, "ci_low": 0.12, "ci_high": 0.28},
    })


# --- the gate itself ---------------------------------------------------------

def test_clean_claim_passes():
    r = MeasurementOracle().verify(_clean())
    assert r.verdict() == Verdict.PASS.value
    assert r.passed is True
    assert r.rc == 0
    # both scope caveats travel on the accept
    assert any("evidence" in d for d in r.does_not_prove)
    assert any("confound" in d for d in r.does_not_prove)
    assert r.coverage["n"] == 500
    assert r.coverage["negative_control_present"] is True


def test_effect_below_minimum_fails():
    r = MeasurementOracle().verify(_below_min())
    assert r.verdict() == Verdict.FAIL.value
    assert r.passed is False
    assert "does not clear" in r.stdout_excerpt


def test_significant_negative_control_fails():
    r = MeasurementOracle().verify(_significant_control())
    assert r.verdict() == Verdict.FAIL.value
    assert "confound" in r.stdout_excerpt


def test_small_sample_fails():
    r = MeasurementOracle(n_min=1000).verify(_clean(n=50))
    assert r.verdict() == Verdict.FAIL.value
    assert "below the registered minimum" in r.stdout_excerpt


def test_missing_n_is_unverifiable_not_fail():
    claim = json.loads(_clean())
    del claim["n"]
    r = MeasurementOracle().verify(json.dumps(claim))
    assert r.verdict() == Verdict.UNVERIFIABLE.value
    assert r.verdict() != Verdict.FAIL.value
    assert r.unverifiable_reason == UnverifiableReason.ENVELOPE_MISSING.value
    assert r.coverage["n"] is None


def test_missing_interval_is_unverifiable_not_fail():
    claim = json.loads(_clean())
    del claim["ci_low"]
    r = MeasurementOracle().verify(json.dumps(claim))
    assert r.verdict() == Verdict.UNVERIFIABLE.value
    assert r.unverifiable_reason == UnverifiableReason.ENVELOPE_MISSING.value


def test_missing_control_is_unverifiable_confounded():
    claim = json.loads(_clean())
    del claim["negative_control"]
    r = MeasurementOracle().verify(json.dumps(claim))
    assert r.verdict() == Verdict.UNVERIFIABLE.value
    assert r.unverifiable_reason == UnverifiableReason.CONFOUNDED.value
    assert r.coverage["negative_control_present"] is False


def test_unparseable_claim_is_unverifiable_not_crash():
    r = MeasurementOracle().verify("{not json")
    assert r.verdict() == Verdict.UNVERIFIABLE.value
    assert r.execution is Execution.COMPLETED


def test_output_hash_is_stable_and_float_free():
    a = MeasurementOracle().verify(_clean())
    b = MeasurementOracle().verify(_clean())
    assert a.output_hash == b.output_hash          # deterministic across runs
    assert len(a.output_hash) == 16
    # a hash built over a claim full of floats must itself be a plain hex digest,
    # never carrying a float that a stranger's replay would format differently
    int(a.output_hash, 16)                         # raises if not clean hex
    # a different claim yields a different hash
    assert a.output_hash != MeasurementOracle().verify(_below_min()).output_hash


def test_evaluate_claim_is_pure_and_matches():
    r = evaluate_claim(json.loads(_clean()), n_min=1)
    assert r["status"] == "PASS"
    assert evaluate_claim(json.loads(_below_min()), n_min=1)["status"] == "FAIL"


# --- registry routing --------------------------------------------------------

def test_registry_routes_ml_aliases_to_measurement():
    reg = default_registry()
    assert isinstance(reg.resolve("ml"), MeasurementOracle)
    # the aliases canonical_domain already handles
    assert isinstance(reg.resolve("measurement"), MeasurementOracle)
    assert isinstance(reg.resolve("model"), MeasurementOracle)
    assert isinstance(reg.resolve("eval"), MeasurementOracle)
    assert "ml" in reg and "measurement" in reg
    assert canonical_domain("measurement") == "ml"


def test_registry_entry_carries_does_not_prove():
    entry = default_registry().entry("ml")
    assert entry.oracle.oracle_type == "measurement"
    assert any("does not prove the mechanism" in d
               for d in entry.does_not_prove)


# --- end to end through the one loop -----------------------------------------

def test_run_verified_ml_passes_with_stub_proposer(tmp_path):
    task = Task(
        task_id="ml.clean", prompt="emit the measurement claim",
        oracle="measurement", oracle_cmd="measurement_gate",
        workdir=str(tmp_path), candidate_path="claim.json")
    ev = run_verified(
        task, StubProposer(_clean()), domain="ml",
        witness_recheck=False, envelopes_dir=str(tmp_path / "env"))
    assert ev.domain == "ml"
    assert ev.verdict == Verdict.PASS.value
    assert ev.accepted is True
    assert any("does not prove the mechanism" in d for d in ev.does_not_prove)


def test_run_verified_unregistered_domain_is_unverifiable(tmp_path):
    task = Task(
        task_id="x.none", prompt="p", oracle="none", oracle_cmd="none",
        workdir=str(tmp_path), candidate_path="c.txt")
    ev = run_verified(task, StubProposer("{}"), domain="astrology",
                      registry=OracleRegistry())
    assert ev.verdict == Verdict.UNVERIFIABLE.value
    assert ev.accepted is False
