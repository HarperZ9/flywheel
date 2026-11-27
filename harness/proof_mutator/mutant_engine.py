# SPDX-License-Identifier: MIT
"""Hypothesis and proof-certificate mutant generator (6 mutant classes).

Generates deterministic adversarial proof mutants across six failure modes:
sign_flip, cost_inversion, sha256_1bit_flip, step_drop, rule_id_swap, and
ulp_bound_inflation, without mutating source proof artifacts.
"""

from __future__ import annotations

import copy
from collections.abc import Sequence
from dataclasses import dataclass

from .sharded_replay import GPU_CERT_SCHEMA, ProofArtifact

HONEST_SCOPE_LIMIT = (
    "Synthesizes six deterministic structural and cryptographic proof mutant "
    "classes (sign_flip, cost_inversion, sha256_1bit_flip, step_drop, "
    "rule_id_swap, ulp_bound_inflation) for verifier mutation testing. Does "
    "not exhaustively fuzz arbitrary MIR expressions or compiler binaries."
)

MUTANT_CLASSES: tuple[str, ...] = (
    "sign_flip",
    "cost_inversion",
    "sha256_1bit_flip",
    "step_drop",
    "rule_id_swap",
    "ulp_bound_inflation",
)


@dataclass(frozen=True)
class ProofMutant:
    """One labeled adversarial mutant derived from a valid ProofArtifact."""

    mutant_id: str
    source_artifact_id: str
    mutant_class: str
    artifact: ProofArtifact


def _flip_hex_lsb(digest: str) -> str:
    if not digest:
        return "0" * 64
    flipped = f"{int(digest[-1], 16) ^ 1:x}"
    return digest[:-1] + flipped


def _target_superopt(cert: dict[str, object]) -> dict[str, object]:
    if cert.get("schema") == GPU_CERT_SCHEMA and isinstance(cert.get("superopt_cert"), dict):
        return cert["superopt_cert"]
    return cert


def _synthetic_step(rule: str, max_ulps: int = 0) -> dict[str, object]:
    return {
        "function": "mutated_fn",
        "rule": rule,
        "cost_before": 0,
        "cost_after": 0,
        "error_witness": {"kind": "bounded_ulp", "max_ulps": max_ulps},
    }


def _apply_cost_or_hash_mutation(
    cert_copy: dict[str, object],
    so: dict[str, object],
    steps_list: list[dict[str, object]],
    mutant_class: str,
) -> None:
    if mutant_class == "sign_flip":
        after_val = int(so.get("total_cost_after", 0)) if isinstance(so.get("total_cost_after"), int) else 0
        so["total_cost_after"] = -abs(after_val) - 1
        if steps_list and isinstance(steps_list[0], dict):
            s_after = int(steps_list[0].get("cost_after", 0)) if isinstance(steps_list[0].get("cost_after"), int) else 0
            steps_list[0]["cost_after"] = -abs(s_after) - 1
    elif mutant_class == "cost_inversion":
        before_val = int(so.get("total_cost_before", 0)) if isinstance(so.get("total_cost_before"), int) else 0
        so["total_cost_after"] = before_val + 2
        if steps_list and isinstance(steps_list[0], dict):
            s_before = int(steps_list[0].get("cost_before", 0)) if isinstance(steps_list[0].get("cost_before"), int) else 0
            steps_list[0]["cost_after"] = s_before + 2
    elif mutant_class == "sha256_1bit_flip":
        if cert_copy.get("schema") == GPU_CERT_SCHEMA and isinstance(cert_copy.get("shader_sha256"), str):
            cert_copy["shader_sha256"] = _flip_hex_lsb(str(cert_copy["shader_sha256"]))
        elif isinstance(cert_copy.get("cert_sha256"), str):
            cert_copy["cert_sha256"] = _flip_hex_lsb(str(cert_copy["cert_sha256"]))


def _apply_step_mutation(
    so: dict[str, object],
    steps_list: list[dict[str, object]],
    mutant_class: str,
) -> None:
    if mutant_class == "step_drop":
        if steps_list:
            steps_list.pop()
        else:
            so["rewrites_applied"] = 1
    elif mutant_class == "rule_id_swap":
        if steps_list and isinstance(steps_list[0], dict):
            steps_list[0]["rule"] = "UNVERIFIED_MUTATED_RULE"
        else:
            steps_list.append(_synthetic_step("UNVERIFIED_MUTATED_RULE"))
            so["rewrites_applied"] = len(steps_list)
    elif mutant_class == "ulp_bound_inflation":
        if steps_list and isinstance(steps_list[0], dict):
            steps_list[0]["error_witness"] = {"kind": "bounded_ulp", "max_ulps": 64}
        else:
            steps_list.append(_synthetic_step("R18_FMA_CONTRACT", max_ulps=64))
            so["rewrites_applied"] = len(steps_list)


def mutate_artifact(artifact: ProofArtifact, mutant_class: str) -> ProofMutant:
    """Create one deep-copied adversarial mutant of artifact for mutant_class."""
    if mutant_class not in MUTANT_CLASSES:
        raise ValueError(f"unknown mutant class: {mutant_class}")
    cert_copy: dict[str, object] = copy.deepcopy(dict(artifact.cert))
    so = _target_superopt(cert_copy)
    steps = so.get("steps")
    steps_list: list[dict[str, object]] = steps if isinstance(steps, list) else []
    so["steps"] = steps_list
    if mutant_class in ("sign_flip", "cost_inversion", "sha256_1bit_flip"):
        _apply_cost_or_hash_mutation(cert_copy, so, steps_list, mutant_class)
    else:
        _apply_step_mutation(so, steps_list, mutant_class)
    mutant_id = f"{artifact.artifact_id}::{mutant_class}"
    mutated = ProofArtifact(mutant_id, cert_copy, artifact.shader_bytes, artifact.expected_cert_sha256)
    return ProofMutant(mutant_id, artifact.artifact_id, mutant_class, mutated)


def generate_mutants(
    artifacts: Sequence[ProofArtifact],
    *,
    classes: Sequence[str] = MUTANT_CLASSES,
) -> list[ProofMutant]:
    """Generate all requested mutant classes deterministically across artifacts."""
    ordered = sorted(artifacts, key=lambda a: a.artifact_id)
    mutants: list[ProofMutant] = []
    for artifact in ordered:
        for cls in classes:
            mutants.append(mutate_artifact(artifact, cls))
    return mutants
