# SPDX-License-Identifier: MIT
"""Pure-stdlib cross-runtime benchmark parity and regression gate.

Validates canonical cross-runtime output digest parity, statistical timing
invariants, honest subprocess spawn-floor disclosures, and baseline latency
regression ceilings across serialized benchmark suites.
"""

from __future__ import annotations

from .parity_check import (
    HONEST_SCOPE_LIMIT as PARITY_HONEST_SCOPE_LIMIT,
)
from .parity_check import (
    KNOWN_RUNTIMES,
    ParityCheckReport,
    is_hex64,
    verify_kernel_parity,
    verify_runtime_digests,
)
from .regression_gate import (
    HONEST_SCOPE_LIMIT as REGRESSION_HONEST_SCOPE_LIMIT,
)
from .regression_gate import (
    PROCESS_LAUNCHED_RUNTIMES,
    SPAWN_FLOOR_THRESHOLD_MS,
    CellTimingReport,
    has_honest_spawn_disclosure,
    verify_cell_timings,
)
from .suite_verifier import (
    HONEST_SCOPE_LIMIT as SUITE_HONEST_SCOPE_LIMIT,
)
from .suite_verifier import (
    SuiteVerificationReport,
    verify_benchmark_suite,
    verify_benchmark_suite_file,
)

HONEST_SCOPE_LIMIT = (
    "Pure-Python stdlib verifier for cross-runtime benchmark output parity, "
    "statistical timing invariants, subprocess spawn disclosures, and latency "
    "regression bounds. Does not compile or execute benchmarked workloads."
)

HONEST_SCOPE_LIMITS: dict[str, str] = {
    "parity_check": PARITY_HONEST_SCOPE_LIMIT,
    "regression_gate": REGRESSION_HONEST_SCOPE_LIMIT,
    "suite_verifier": SUITE_HONEST_SCOPE_LIMIT,
}

__all__ = [
    "CellTimingReport",
    "HONEST_SCOPE_LIMIT",
    "HONEST_SCOPE_LIMITS",
    "KNOWN_RUNTIMES",
    "PROCESS_LAUNCHED_RUNTIMES",
    "ParityCheckReport",
    "SPAWN_FLOOR_THRESHOLD_MS",
    "SuiteVerificationReport",
    "has_honest_spawn_disclosure",
    "is_hex64",
    "verify_benchmark_suite",
    "verify_benchmark_suite_file",
    "verify_cell_timings",
    "verify_kernel_parity",
    "verify_runtime_digests",
]
