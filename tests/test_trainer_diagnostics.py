"""Falsifier for trainer_diagnostics.py -- the stdlib validator for the frozen
trainer-diagnostics contract (project-docs/prereg/2026-07-27-trainer-diagnostics-
addendum.md, Section 2).

This module does not implement training. PolicyOptimizer stays an unimplemented
Protocol (harness/rl_from_oracle.py). What is tested here is the schema a future
trainer's diagnostics record MUST satisfy: every required field present, the
four fields with no honest-null allowed (arm, rung, step, n_eval) actually
non-null, the frozen arm/rung vocabularies enforced, pass_at_k shaped as the
addendum describes, and the addendum's own contents bindable by hash so a run
can cite the exact frozen text it satisfied.
"""
import hashlib
from pathlib import Path

import pytest

from harness.trainer_diagnostics import (
    DiagnosticsError,
    FROZEN_ARMS,
    REQUIRED_FIELDS,
    RUNGS,
    cites_addendum_sha256,
    null_reasons_missing,
    validate_record,
)

ROOT = Path(__file__).resolve().parent.parent
ADDENDUM = ROOT / "project-docs" / "prereg" / "2026-07-27-trainer-diagnostics-addendum.md"

NON_NULLABLE = ("arm", "rung", "step", "n_eval")
NULLABLE = tuple(f for f in REQUIRED_FIELDS if f not in NON_NULLABLE)


def _valid_record(**overrides) -> dict:
    rec = {
        "arm": "single",
        "rung": "R1",
        "step": 100,
        "policy_entropy": 1.23,
        "answer_perplexity": 4.56,
        "pass_at_k": {1: 0.5, "4": 0.75},
        "reward_mean": 0.6,
        "reward_std": 0.1,
        "kl_to_ref": 0.02,
        "grad_norm": 0.9,
        "n_eval": 32,
    }
    rec.update(overrides)
    return rec


# ---- shape of the frozen vocabularies


def test_required_fields_are_the_eleven_from_section_2():
    assert REQUIRED_FIELDS == (
        "arm", "rung", "step", "policy_entropy", "answer_perplexity",
        "pass_at_k", "reward_mean", "reward_std", "kl_to_ref", "grad_norm",
        "n_eval",
    )


def test_frozen_arms_are_the_seven_from_section_2():
    assert FROZEN_ARMS == (
        "single", "best_of_k", "random_of_k", "placebo_of_k", "pass_at_k",
        "random_reward", "format_only_reward",
    )
    # pass_at_k is deliberately both an arm name and a field name.
    assert "pass_at_k" in FROZEN_ARMS
    assert "pass_at_k" in REQUIRED_FIELDS


def test_rungs_are_r1_through_r9():
    assert RUNGS == ("R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9")


# ---- validate_record: the happy path


def test_a_valid_full_record_passes():
    validate_record(_valid_record())  # no raise


# ---- validate_record: missing keys


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_each_missing_required_field_raises(field):
    rec = _valid_record()
    del rec[field]
    with pytest.raises(DiagnosticsError):
        validate_record(rec)


# ---- validate_record: the honest-null boundary


@pytest.mark.parametrize("field", NON_NULLABLE)
def test_null_in_a_non_nullable_field_raises(field):
    rec = _valid_record(**{field: None})
    with pytest.raises(DiagnosticsError):
        validate_record(rec)


def test_null_policy_entropy_passes():
    validate_record(_valid_record(policy_entropy=None))  # no raise


@pytest.mark.parametrize("field", NULLABLE)
def test_null_in_any_nullable_field_passes(field):
    validate_record(_valid_record(**{field: None}))  # no raise


# ---- validate_record: structural violations


def test_bad_arm_raises():
    with pytest.raises(DiagnosticsError):
        validate_record(_valid_record(arm="not_a_frozen_arm"))


def test_bad_rung_raises():
    with pytest.raises(DiagnosticsError):
        validate_record(_valid_record(rung="R10"))


def test_negative_step_raises():
    with pytest.raises(DiagnosticsError):
        validate_record(_valid_record(step=-1))


def test_non_int_step_raises():
    with pytest.raises(DiagnosticsError):
        validate_record(_valid_record(step=1.5))


def test_bool_step_raises():
    # bool is an int subclass in Python; a diagnostics step is not a flag.
    with pytest.raises(DiagnosticsError):
        validate_record(_valid_record(step=True))


@pytest.mark.parametrize("bad_pass_at_k", [
    "not-a-dict",
    ["not", "a", "dict"],
    {"not-an-int": 0.5},
    {1.5: 0.5},
    {1: "not-a-number"},
    {1: None},
])
def test_malformed_pass_at_k_raises(bad_pass_at_k):
    with pytest.raises(DiagnosticsError):
        validate_record(_valid_record(pass_at_k=bad_pass_at_k))


def test_pass_at_k_accepts_int_and_int_string_keys():
    validate_record(_valid_record(pass_at_k={1: 0.5, "4": 0.75, 8: 1}))  # no raise


def test_n_eval_zero_raises():
    with pytest.raises(DiagnosticsError):
        validate_record(_valid_record(n_eval=0))


def test_n_eval_negative_raises():
    with pytest.raises(DiagnosticsError):
        validate_record(_valid_record(n_eval=-5))


def test_n_eval_non_int_raises():
    with pytest.raises(DiagnosticsError):
        validate_record(_valid_record(n_eval=32.0))


def test_diagnostics_error_is_a_value_error():
    assert issubclass(DiagnosticsError, ValueError)


# ---- null_reasons_missing


def test_null_reasons_missing_flags_a_null_field_lacking_a_reason():
    rec = _valid_record(policy_entropy=None)
    assert null_reasons_missing(rec) == ["policy_entropy"]


def test_null_reasons_missing_empty_when_reason_present():
    rec = _valid_record(
        policy_entropy=None,
        null_reasons={"policy_entropy": "eval batch truncated before entropy readout"},
    )
    assert null_reasons_missing(rec) == []


def test_null_reasons_missing_empty_when_no_nulls_at_all():
    assert null_reasons_missing(_valid_record()) == []


def test_null_reasons_missing_flags_only_the_unexplained_ones():
    rec = _valid_record(
        policy_entropy=None,
        grad_norm=None,
        null_reasons={"grad_norm": "optimizer does not expose it"},
    )
    assert null_reasons_missing(rec) == ["policy_entropy"]


# ---- cites_addendum_sha256


def test_cites_addendum_sha256_returns_64_hex_chars():
    got = cites_addendum_sha256(ROOT)
    assert isinstance(got, str)
    assert len(got) == 64
    assert all(c in "0123456789abcdef" for c in got)


def test_cites_addendum_sha256_matches_lf_normalized_file_bytes():
    raw = ADDENDUM.read_bytes().replace(b"\r\n", b"\n")
    want = hashlib.sha256(raw).hexdigest()
    assert cites_addendum_sha256(ROOT) == want


def test_cites_addendum_sha256_accepts_str_or_path():
    assert cites_addendum_sha256(str(ROOT)) == cites_addendum_sha256(ROOT)
