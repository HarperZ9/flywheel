# SPDX-License-Identifier: MIT
"""Pure-stdlib Crucible tail-risk distributional fuzzer and gate (CS-024).

Provides deterministic seed-pinned boundary and heavy-tail input generation,
extreme-value tail metrics (p99, CVaR_99, max excursion ratio), and a
fail-closed fuzzing gate sealing tail_fuzz_attestation_sha256.
"""

from __future__ import annotations

from .boundary_fuzzer import (
    ADVERSARIAL_STRINGS,
    BOUNDARY_INTS,
    BOUNDARY_LENGTHS,
    EXTREME_FLOATS,
    BoundaryCase,
    fingerprint_cases,
    generate_float_tail_cases,
    generate_mixed_boundary_cases,
    is_seed_reproducible,
)
from .boundary_fuzzer import (
    HONEST_SCOPE_LIMIT as FUZZER_HONEST_SCOPE_LIMIT,
)
from .fuzz_gate import (
    FuzzGatePolicy,
    GeneratorFn,
    InvariantFn,
    TailFuzzReport,
    TargetFn,
    run_tail_fuzz_gate,
)
from .fuzz_gate import (
    HONEST_SCOPE_LIMIT as GATE_HONEST_SCOPE_LIMIT,
)
from .tail_metrics import (
    HONEST_SCOPE_LIMIT as METRICS_HONEST_SCOPE_LIMIT,
)
from .tail_metrics import (
    TailRiskMetrics,
    compute_tail_metrics,
    quantile_sorted,
)

HONEST_SCOPE_LIMIT = (
    "Pure-Python stdlib deterministic boundary fuzzer and empirical tail-risk "
    "gate (p99, CVaR_99, max excursion ratio, NaN/Inf absence, and seed "
    "reproducibility). Does not perform coverage-guided binary fuzzing or "
    "prove correctness outside the sampled input distribution."
)

HONEST_SCOPE_LIMITS: dict[str, str] = {
    "boundary_fuzzer": FUZZER_HONEST_SCOPE_LIMIT,
    "tail_metrics": METRICS_HONEST_SCOPE_LIMIT,
    "fuzz_gate": GATE_HONEST_SCOPE_LIMIT,
}

__all__ = [
    "ADVERSARIAL_STRINGS",
    "BOUNDARY_INTS",
    "BOUNDARY_LENGTHS",
    "BoundaryCase",
    "EXTREME_FLOATS",
    "FuzzGatePolicy",
    "GeneratorFn",
    "HONEST_SCOPE_LIMIT",
    "HONEST_SCOPE_LIMITS",
    "InvariantFn",
    "TailFuzzReport",
    "TailRiskMetrics",
    "TargetFn",
    "compute_tail_metrics",
    "fingerprint_cases",
    "generate_float_tail_cases",
    "generate_mixed_boundary_cases",
    "is_seed_reproducible",
    "quantile_sorted",
    "run_tail_fuzz_gate",
]
