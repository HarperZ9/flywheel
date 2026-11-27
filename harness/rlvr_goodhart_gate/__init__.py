# SPDX-License-Identifier: MIT
"""Pure-stdlib fail-closed Goodhart divergence and RLVR oracle verifier."""

from harness.rlvr_goodhart_gate.goodhart_guards import (
    DEFAULT_MAX_PARITY_ERR,
    DEFAULT_ORACLE_EPS,
    DEFAULT_PRM_THRESHOLD,
    check_goodhart_candidate,
    check_monotonic_solve_curve,
    check_unverified_weight_drift,
    is_finite_number,
    is_strict_int,
)
from harness.rlvr_goodhart_gate.goodhart_oracle import (
    GoodhartPolicy,
    GoodhartReport,
    verify_goodhart_bundle,
    verify_goodhart_file,
)
from harness.rlvr_goodhart_gate.rlvr_parser import (
    CandidateEval,
    GoodhartBundle,
    PolicyUpdateRecord,
    parse_goodhart_payload,
)

__all__ = [
    "CandidateEval",
    "DEFAULT_MAX_PARITY_ERR",
    "DEFAULT_ORACLE_EPS",
    "DEFAULT_PRM_THRESHOLD",
    "GoodhartBundle",
    "GoodhartPolicy",
    "GoodhartReport",
    "PolicyUpdateRecord",
    "check_goodhart_candidate",
    "check_monotonic_solve_curve",
    "check_unverified_weight_drift",
    "is_finite_number",
    "is_strict_int",
    "parse_goodhart_payload",
    "verify_goodhart_bundle",
    "verify_goodhart_file",
]
