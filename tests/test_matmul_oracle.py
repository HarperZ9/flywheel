"""Falsifier for the matmul bilinear-scheme oracle (harness/matmul_oracle.py).

The AlphaTensor thesis, verified locally: a bilinear decomposition is accepted
ONLY if it reproduces the exact matmul tensor. Strassen-7 passes, the naive
scheme passes, and any perturbed or rank-dropped scheme is rejected. The oracle
is then run through the existing calibration machinery to prove it discriminates
known-good from known-bad with ZERO false accepts -- the precondition for trust.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.matmul_oracle import (
    MatMulSchemeOracle, verify_scheme, matmul_tensor,
    naive_scheme, strassen_scheme, perturb_scheme, drop_triple, dumps,
)
from harness.calibration import calibrate, require_calibrated, CalibrationCase


def test_naive_scheme_is_exact():
    for (n, m, p) in [(2, 2, 2), (2, 3, 2), (3, 3, 3), (1, 4, 2)]:
        ok, reason = verify_scheme(naive_scheme(n, m, p))
        assert ok, f"naive {n}x{m}x{p} should be exact: {reason}"


def test_strassen_is_exact_rank_7():
    ok, reason = verify_scheme(strassen_scheme())
    assert ok, f"Strassen must reproduce the tensor: {reason}"
    assert "rank 7" in reason


def test_perturbed_strassen_rejected():
    for pos in range(4):
        bad = perturb_scheme(strassen_scheme(), triple=1, field="w", pos=pos)
        ok, _ = verify_scheme(bad)
        assert not ok, f"perturbed w[{pos}] must break the identity"


def test_dropped_triple_rejected():
    ok, _ = verify_scheme(drop_triple(strassen_scheme(), triple=3))
    assert not ok      # rank-6 cannot compute 2x2x2 matmul (Strassen is optimal-ish)


def test_oracle_passes_good_rejects_bad():
    oracle = MatMulSchemeOracle()
    assert oracle.verify(dumps(strassen_scheme())).passed
    assert oracle.verify(dumps(naive_scheme(2, 2, 2))).passed
    assert not oracle.verify(dumps(perturb_scheme(strassen_scheme()))).passed


def test_malformed_scheme_rejected_not_crash():
    oracle = MatMulSchemeOracle()
    assert not oracle.verify("{not json").passed
    assert not oracle.verify('{"n":2,"m":2,"p":2,"triples":[]}').passed
    assert not oracle.verify('{"n":2}').passed          # missing keys


def test_oracle_calibrates_trustworthy():
    # the discrimination proof: over a labelled ladder, ZERO false accepts
    oracle = MatMulSchemeOracle()
    cases = [
        CalibrationCase(dumps(strassen_scheme()), True, "Strassen-7"),
        CalibrationCase(dumps(naive_scheme(2, 2, 2)), True, "naive-8"),
        CalibrationCase(dumps(naive_scheme(3, 3, 3)), True, "naive-27"),
        CalibrationCase(dumps(perturb_scheme(strassen_scheme())), False, "perturbed"),
        CalibrationCase(dumps(drop_triple(strassen_scheme())), False, "rank-6"),
        CalibrationCase("{garbage", False, "malformed"),
    ]
    receipt = calibrate(oracle, None, cases)
    assert receipt.false_pos == 0            # never accepts a known-bad -> trustworthy
    assert receipt.trustworthy is True
    assert receipt.true_pos == 3 and receipt.true_neg == 3
    # the gate returns the receipt only because there are zero false accepts
    require_calibrated(oracle, None, cases)


def test_exact_beats_single_point_probe():
    # a perturbed scheme is wrong on the TENSOR, but a naive "check one product"
    # probe (multiply two specific matrices) can miss it. The symbolic oracle
    # never does -- that exactness is what it earns over a point check.
    bad = perturb_scheme(strassen_scheme(), triple=0, field="w", pos=1)  # corrupts C12 path
    ok, _ = verify_scheme(bad)
    assert not ok
    # a zero-matrix "probe" would produce C=0 for both correct and this broken
    # scheme, i.e. a single trivial input cannot discriminate; the tensor can.
    T = matmul_tensor(2, 2, 2)
    assert len(T) == 8       # 2*2*2 nonzero structure entries
