# SPDX-License-Identifier: MIT
"""Mutant kill-rate scorecard and weak-verifier fail-closed control.

Evaluates a proof verifier callable against generated hypothesis/proof
mutants, computes overall and per-class kill rates, fails closed whenever
kill_rate < min_kill_rate (default 1.0), and seals a deterministic
scorecard_attestation_sha256.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from .mutant_engine import MUTANT_CLASSES, generate_mutants
from .sharded_replay import (
    GPU_CERT_SCHEMA,
    SUPEROPT_CERT_SCHEMA,
    ProofArtifact,
    ReplayItemResult,
    verify_proof_artifact,
)

HONEST_SCOPE_LIMIT = (
    "Measures a proof verifier callable's mutant kill rate over the six "
    "defined structural and cryptographic mutant classes and fails closed "
    "below min_kill_rate. High kill rate proves sensitivity to these six "
    "classes and does not prove absence of unknown soundness bugs."
)

VerifierFn = Callable[[ProofArtifact], ReplayItemResult]


@dataclass(frozen=True)
class KillScorecard:
    """Fail-closed mutation-testing scorecard for a proof verifier."""

    passed: bool
    total_mutants: int
    killed_mutants: int
    survived_mutants: int
    kill_rate: float
    per_class_kill_rate: dict[str, float]
    survivor_ids: tuple[str, ...]
    scorecard_attestation_sha256: str

    def to_dict(self) -> dict[str, object]:
        """Serialize scorecard into a deterministic JSON-compatible dict."""
        return {
            "passed": self.passed,
            "total_mutants": self.total_mutants,
            "killed_mutants": self.killed_mutants,
            "survived_mutants": self.survived_mutants,
            "kill_rate": self.kill_rate,
            "per_class_kill_rate": dict(self.per_class_kill_rate),
            "survivor_ids": list(self.survivor_ids),
            "scorecard_attestation_sha256": self.scorecard_attestation_sha256,
        }


def permissive_weak_verifier(artifact: ProofArtifact) -> ReplayItemResult:
    """Planted weak-verifier negative control that ignores proof invariants."""
    cert = artifact.cert
    ok = (
        isinstance(cert, Mapping)
        and cert.get("schema") in (GPU_CERT_SCHEMA, SUPEROPT_CERT_SCHEMA)
        and cert.get("verified") is True
    )
    return ReplayItemResult(
        artifact.artifact_id,
        ok,
        () if ok else ("WEAK_SCHEMA_OR_VERIFIED_CHECK_FAILED",),
    )


def _seal_scorecard(
    passed: bool,
    total: int,
    killed: int,
    kill_rate: float,
    per_class: dict[str, float],
    survivors: list[str],
) -> str:
    payload = {
        "passed": passed, "total_mutants": total, "killed_mutants": killed,
        "kill_rate": kill_rate, "per_class_kill_rate": per_class, "survivor_ids": survivors,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def evaluate_mutant_kill_scorecard(
    artifacts: Sequence[ProofArtifact],
    verifier: VerifierFn = verify_proof_artifact,
    *,
    classes: Sequence[str] = MUTANT_CLASSES,
    min_kill_rate: float = 1.0,
) -> KillScorecard:
    """Run verifier on all mutants and fail closed if kill_rate < min_kill_rate."""
    mutants = generate_mutants(artifacts, classes=classes)
    per_class_total: dict[str, int] = {cls: 0 for cls in classes}
    per_class_killed: dict[str, int] = {cls: 0 for cls in classes}
    survivors: list[str] = []
    killed = 0
    for mut in mutants:
        per_class_total[mut.mutant_class] += 1
        if not verifier(mut.artifact).passed:
            killed += 1
            per_class_killed[mut.mutant_class] += 1
        else:
            survivors.append(mut.mutant_id)
    total = len(mutants)
    kill_rate = round(killed / total, 6) if total > 0 else 0.0
    per_class_rate = {
        cls: (round(per_class_killed[cls] / per_class_total[cls], 6) if per_class_total[cls] else 0.0)
        for cls in classes
    }
    passed = total > 0 and kill_rate >= min_kill_rate and (min_kill_rate < 1.0 or not survivors)
    seal = _seal_scorecard(passed, total, killed, kill_rate, per_class_rate, survivors)
    return KillScorecard(passed, total, killed, len(survivors), kill_rate, per_class_rate, tuple(survivors), seal)
