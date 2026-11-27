# SPDX-License-Identifier: MIT
"""Pure-stdlib proof-replay and hypothesis mutator (CS-017).

Provides worker-count-invariant sharded proof certificate replay, a 6-class
hypothesis/proof mutant generator, and a fail-closed mutant kill-rate
scorecard with a planted weak-verifier control.
"""

from __future__ import annotations

from .kill_scorecard import (
    HONEST_SCOPE_LIMIT as SCORECARD_HONEST_SCOPE_LIMIT,
)
from .kill_scorecard import (
    KillScorecard,
    VerifierFn,
    evaluate_mutant_kill_scorecard,
    permissive_weak_verifier,
)
from .mutant_engine import (
    HONEST_SCOPE_LIMIT as MUTANT_HONEST_SCOPE_LIMIT,
)
from .mutant_engine import (
    MUTANT_CLASSES,
    ProofMutant,
    generate_mutants,
    mutate_artifact,
)
from .sharded_replay import (
    GPU_CERT_SCHEMA,
    SUPEROPT_CERT_SCHEMA,
    TARGET_SHADER_EXT,
    ProofArtifact,
    ReplayItemResult,
    ShardedReplayReport,
    load_gpu_proof_corpus,
    replay_corpus_sharded,
    verify_proof_artifact,
    verify_worker_count_invariance,
)
from .sharded_replay import (
    HONEST_SCOPE_LIMIT as REPLAY_HONEST_SCOPE_LIMIT,
)

HONEST_SCOPE_LIMIT = (
    "Pure-Python stdlib sharded proof-certificate replay verifier and 6-class "
    "mutant kill-rate harness. Validates serialized certificate invariants "
    "and verifier sensitivity; does not re-run e-graph/SMT provers or GPU "
    "shader compilers."
)

HONEST_SCOPE_LIMITS: dict[str, str] = {
    "sharded_replay": REPLAY_HONEST_SCOPE_LIMIT,
    "mutant_engine": MUTANT_HONEST_SCOPE_LIMIT,
    "kill_scorecard": SCORECARD_HONEST_SCOPE_LIMIT,
}

__all__ = [
    "GPU_CERT_SCHEMA",
    "HONEST_SCOPE_LIMIT",
    "HONEST_SCOPE_LIMITS",
    "KillScorecard",
    "MUTANT_CLASSES",
    "ProofArtifact",
    "ProofMutant",
    "ReplayItemResult",
    "SUPEROPT_CERT_SCHEMA",
    "ShardedReplayReport",
    "TARGET_SHADER_EXT",
    "VerifierFn",
    "evaluate_mutant_kill_scorecard",
    "generate_mutants",
    "load_gpu_proof_corpus",
    "mutate_artifact",
    "permissive_weak_verifier",
    "replay_corpus_sharded",
    "verify_proof_artifact",
    "verify_worker_count_invariance",
]
