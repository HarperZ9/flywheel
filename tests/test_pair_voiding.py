"""B9: pair voiding (model drift, envelope malformation) + Holm-Bonferroni.

The acceptance fixtures from the design of record: a model_observed mismatch
voids BOTH attempts of the pair and lands in the model_drift_excluded count;
an envelope-malformed attempt voids the whole pair and the per-arm
envelope-compliance rates surface separately; a multi-comparison fixture
emits raw and adjusted p; the preregistered primary is exempt. Reference
values are hand-checked in comments.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.pair_voiding import (                                   # noqa: E402
    HOLM_SCHEMA, VOIDING_SCHEMA, holm_bonferroni, pair_voiding_check)

MODEL = "gpt-5.3-codex-spark"


def _arm(name, rows):
    return {"arm": name, "attempts": [
        {"task_id": t, "repetition": r, "model_observed": m,
         "execution_state": s} for t, r, m, s in rows]}


# --- void type 1: model drift ------------------------------------------------

def test_model_drift_voids_both_sides_of_the_pair():
    a = _arm("bare", [("t1", 0, MODEL, "returned"),
                      ("t2", 0, MODEL, "returned"),
                      ("t3", 0, MODEL, "returned")])
    b = _arm("governed", [("t1", 0, MODEL, "returned"),
                          ("t2", 0, "gpt-5.3-codex-mini", "returned"),
                          ("t3", 0, MODEL, "returned")])
    out = pair_voiding_check(a, b)
    assert out["schema"] == VOIDING_SCHEMA
    assert out["n_pairs"] == 3 and out["admissible_pairs"] == 2
    assert out["model_drift_excluded"] == 1
    assert out["envelope_malformed_excluded"] == 0
    (row,) = out["excluded_pairs"]
    assert (row["task_id"], row["repetition"]) == ("t2", 0)
    assert row["reason"] == "model_drift"
    # BOTH attempts void: the row names both arms and carries both values.
    assert row["voids"] == ["bare", "governed"]
    assert row["a_model_observed"] == MODEL
    assert row["b_model_observed"] == "gpt-5.3-codex-mini"
    # A clean run has full envelope compliance on both arms.
    assert [c["rate"] for c in out["envelope_compliance"]] == [1.0, 1.0]


def test_matching_models_admit_every_pair():
    a = _arm("bare", [(f"t{i}", 0, MODEL, "returned") for i in range(4)])
    b = _arm("governed", [(f"t{i}", 0, MODEL, "returned") for i in range(4)])
    out = pair_voiding_check(a, b)
    assert out["admissible_pairs"] == 4 and out["excluded_pairs"] == []
    assert out["model_drift_excluded"] == 0


# --- void type 2: envelope malformation --------------------------------------

def test_envelope_malformed_voids_the_whole_pair_and_rates_surface():
    a = _arm("bare", [("t1", 0, MODEL, "returned"),
                      ("t2", 0, MODEL, "returned"),
                      ("t3", 0, MODEL, "returned")])
    b = _arm("governed", [("t1", 0, MODEL, "returned"),
                          ("t2", 0, "", "malformed"),
                          ("t3", 0, MODEL, "returned")])
    out = pair_voiding_check(a, b)
    assert out["n_pairs"] == 3 and out["admissible_pairs"] == 2
    assert out["envelope_malformed_excluded"] == 1
    assert out["model_drift_excluded"] == 0
    (row,) = out["excluded_pairs"]
    assert row["reason"] == "envelope_malformed"
    assert "governed" in row["detail"] and row["voids"] == ["bare", "governed"]
    # Compliance rates are per-arm and separate: bare 3/3, governed 2/3.
    bare, governed = out["envelope_compliance"]
    assert bare == {"arm": "bare", "attempts": 3, "malformed": 0,
                    "compliant": 3, "rate": 1.0,
                    "definition": bare["definition"]}
    assert governed["attempts"] == 3 and governed["malformed"] == 1
    assert governed["compliant"] == 2
    assert governed["rate"] == pytest.approx(0.666667)


def test_malformed_takes_precedence_over_drift_one_reason_per_pair():
    a = _arm("bare", [("t1", 0, MODEL, "malformed")])
    b = _arm("governed", [("t1", 0, "other-model", "returned")])
    out = pair_voiding_check(a, b)
    (row,) = out["excluded_pairs"]
    assert row["reason"] == "envelope_malformed"
    assert out["envelope_malformed_excluded"] == 1
    assert out["model_drift_excluded"] == 0


def test_unobserved_model_voids_by_name_not_as_a_silent_match():
    # "" == "" would read as a model match; it must void by name instead.
    a = _arm("bare", [("t1", 0, "", "timeout")])
    b = _arm("governed", [("t1", 0, "", "returned")])
    out = pair_voiding_check(a, b)
    (row,) = out["excluded_pairs"]
    assert row["reason"] == "model_observed_unrecorded"
    assert out["model_unrecorded_excluded"] == 1
    assert out["admissible_pairs"] == 0


# --- refusals and malformation ----------------------------------------------

def test_unequal_pair_sets_refuse_pairing_but_compliance_stands():
    a = _arm("bare", [("t1", 0, MODEL, "returned"),
                      ("t2", 0, MODEL, "malformed")])
    b = _arm("governed", [("t1", 0, MODEL, "returned")])
    out = pair_voiding_check(a, b)
    assert out["refused"]["reason"] == "unequal_task_sets"
    assert "excluded_pairs" not in out
    bare = out["envelope_compliance"][0]
    assert bare["attempts"] == 2 and bare["compliant"] == 1
    reps = pair_voiding_check(
        _arm("bare", [("t1", 0, MODEL, "returned")]),
        _arm("governed", [("t1", 1, MODEL, "returned")]))
    assert reps["refused"]["reason"] == "unequal_repetition_sets"


def test_voiding_malformation_raises():
    good = _arm("governed", [("t1", 0, MODEL, "returned")])
    with pytest.raises(ValueError):
        pair_voiding_check(
            _arm("bare", [("t1", 0, MODEL, "exploded")]), good)
    with pytest.raises(ValueError):
        pair_voiding_check({"arm": "bare", "attempts": [
            {"task_id": "t1", "repetition": 0, "model_observed": None,
             "execution_state": "returned"}]}, good)
    with pytest.raises(ValueError):
        pair_voiding_check(
            _arm("bare", [("t1", 0, MODEL, "returned"),
                          ("t1", 0, MODEL, "returned")]), good)
    with pytest.raises(ValueError):
        pair_voiding_check(_arm("", [("t1", 0, MODEL, "returned")]), good)


# --- Holm-Bonferroni ---------------------------------------------------------

def test_holm_emits_raw_and_adjusted_p_with_primary_exempt():
    """Family p = {0.01, 0.03, 0.04}, m = 3. Sorted step-down:
    3*0.01 = 0.03; max(0.03, 2*0.03) = 0.06; max(0.06, 1*0.04) = 0.06."""
    out = holm_bonferroni([
        {"comparison_id": "pilot_primary", "p": 0.02},
        {"comparison_id": "c1", "p": 0.01},
        {"comparison_id": "c2", "p": 0.04},
        {"comparison_id": "c3", "p": 0.03},
    ], primary="pilot_primary")
    assert out["schema"] == HOLM_SCHEMA and out["family_size"] == 3
    rows = {r["comparison_id"]: r for r in out["rows"]}
    primary = rows["pilot_primary"]
    assert primary["role"] == "primary" and primary["p_raw"] == 0.02
    assert primary["p_adjusted"] is None
    assert primary["adjustment"] == "exempt_preregistered_primary"
    assert rows["c1"]["p_adjusted"] == pytest.approx(0.03)
    assert rows["c2"]["p_adjusted"] == pytest.approx(0.06)
    assert rows["c3"]["p_adjusted"] == pytest.approx(0.06)
    for cid in ("c1", "c2", "c3"):
        assert rows[cid]["role"] == "family"
        assert rows[cid]["p_raw"] is not None  # raw always beside adjusted


def test_holm_caps_at_one_and_stays_monotone():
    # m=2, sorted [0.5, 0.6]: 2*0.5 = 1.0; max(1.0, 1*0.6) = 1.0.
    out = holm_bonferroni([
        {"comparison_id": "primary", "p": 0.5},
        {"comparison_id": "c1", "p": 0.6},
        {"comparison_id": "c2", "p": 0.5},
    ], primary="primary")
    rows = {r["comparison_id"]: r for r in out["rows"]}
    assert rows["c1"]["p_adjusted"] == 1.0
    assert rows["c2"]["p_adjusted"] == 1.0


def test_holm_single_family_member_adjusts_to_its_raw_p():
    out = holm_bonferroni([
        {"comparison_id": "primary", "p": 0.2},
        {"comparison_id": "only", "p": 0.04},
    ], primary="primary")
    rows = {r["comparison_id"]: r for r in out["rows"]}
    assert rows["only"]["p_adjusted"] == pytest.approx(0.04)


def test_holm_primary_alone_is_a_zero_size_family():
    out = holm_bonferroni([{"comparison_id": "primary", "p": 0.03}],
                          primary="primary")
    assert out["family_size"] == 0
    (row,) = out["rows"]
    assert row["p_adjusted"] is None


def test_holm_malformation_raises():
    with pytest.raises(ValueError):  # primary must be in the list
        holm_bonferroni([{"comparison_id": "c1", "p": 0.01}],
                        primary="absent")
    with pytest.raises(ValueError):  # duplicate ids
        holm_bonferroni([{"comparison_id": "c1", "p": 0.01},
                         {"comparison_id": "c1", "p": 0.02}], primary="c1")
    with pytest.raises(ValueError):  # p out of range
        holm_bonferroni([{"comparison_id": "c1", "p": 1.5}], primary="c1")
    with pytest.raises(ValueError):  # p not a number
        holm_bonferroni([{"comparison_id": "c1", "p": True}], primary="c1")
    with pytest.raises(ValueError):  # empty list
        holm_bonferroni([], primary="c1")
