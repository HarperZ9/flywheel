"""Spec-derived tests for the clean-room checker (written before core.py was read)."""
import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from second_checker import FAIL, MALFORMED, PASS, parse_row, verify_obj  # noqa: E402

P = 7
# R0 = I1 - 3 I2 ; R1 = I2 - 2 I3  =>  I1 = 6 I3, witness lam = {0: 1, 1: 3}
ROWS = [parse_row({"1": 1, "2": -3}, P), parse_row({"2": 1, "3": -2}, P)]
GOOD = {"receipt_version": "1.0", "p": P, "target": {"col": 1},
        "c": {"3": 6}, "lam": {"n_rows": 2, "idx": [0, 1], "val": [1, 3]}}


def w(**changes):
    out = copy.deepcopy(GOOD)
    for k, v in changes.items():
        out[k] = v
    return out


def test_good_passes():
    assert verify_obj(ROWS, GOOD).verdict == PASS


def test_coefficient_flip_fails():
    assert verify_obj(ROWS, w(c={"3": 5})).verdict == FAIL


def test_lambda_flip_fails():
    assert verify_obj(ROWS, w(lam={"n_rows": 2, "idx": [0, 1], "val": [1, 4]})).verdict == FAIL


def test_extra_residual_column_fails():
    rows = [ROWS[0], {**ROWS[1], 9: 1}]
    assert verify_obj(rows, GOOD).verdict == FAIL


def test_nrows_mismatch_is_fail_not_malformed():
    v = verify_obj(ROWS + [{}], GOOD)
    assert v.verdict == FAIL and v.reason == "lam n_rows mismatch"


def test_values_normalized_mod_p():
    assert verify_obj(ROWS, w(c={"3": 6 + 7 * 100})).verdict == PASS
    assert verify_obj(ROWS, w(c={"3": -1})).verdict == PASS


def test_zero_c_entries_dropped():
    assert verify_obj(ROWS, w(c={"3": 6, "4": 0})).verdict == PASS


def test_table_mode():
    assert verify_obj(ROWS, GOOD, claimed={"3": 6}).verdict == PASS
    v = verify_obj(ROWS, GOOD, claimed={"3": 5})
    assert v.verdict == FAIL and v.reason == "claimed table row != certified row"


def test_malformed_cases():
    bad = [
        w(receipt_version="2.0"),
        {k: v for k, v in GOOD.items() if k != "p"},
        w(p=1),
        w(lam={"n_rows": 2, "idx": [0, 0], "val": [1, 3]}),
        w(lam={"n_rows": 2, "idx": [0, 2], "val": [1, 3]}),
        w(lam={"n_rows": 2, "idx": [-1, 1], "val": [1, 3]}),
        w(lam={"n_rows": 2, "idx": [0], "val": [1, 3]}),
        w(target={"label": [1]}),
        w(c={"x": 1}),
        w(p=True),
    ]
    for obj in bad:
        assert verify_obj(ROWS, obj).verdict == MALFORMED, obj


def test_wrong_prime_fails():
    # Same integers read at p = 11: R0 + 3 R1 = e1 - 6 e3 still holds over Z,
    # so a prime change alone need not break this tiny identity. Use a witness
    # whose lambda only works mod 7.
    rows11 = [parse_row({"1": 1, "2": -3}, 11), parse_row({"2": 1, "3": -2}, 11)]
    good_mod7 = w(c={"3": 6}, lam={"n_rows": 2, "idx": [0, 1], "val": [8, 10]})
    assert verify_obj(ROWS, good_mod7).verdict == PASS
    assert verify_obj(rows11, dict(good_mod7, p=11)).verdict == FAIL
