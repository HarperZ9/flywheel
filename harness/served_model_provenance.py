#!/usr/bin/env python3
"""served_model_provenance.py -- the Served-Model Provenance probe (SMP).

A provider's claim that a request was served by a named model at a named
precision is, from the outside, unverifiable on trust alone. SMP turns it into a
re-derivable check. Against a fixed battery of deterministic probes (greedy, zero
temperature, so a model's answer is a stable fingerprint), the claimed model
produces a reference set. SMP compares the outputs an endpoint actually returned
to that reference, and, where reference fingerprints for known alternative models
are supplied, to those too. Outputs that match the claim are MATCH; outputs that
match an alternative better than the claim, or fail the claim, are DRIFT; too few
shared probes are UNVERIFIABLE.

The check is behavioral, not cryptographic. A fingerprint identifies a model by
what it emits on the battery, so two models that agree on the battery are
indistinguishable to it, and sampling, batching, or quantization can move an
output; a MATCH is consistent-with-the-claim on the battery, not proof of the
served weights or precision. Collecting the observed battery from a live endpoint
is a separate, upstream step. Standard library only.
"""
from __future__ import annotations

from .transitive_witness import DRIFT, MATCH, UNVERIFIABLE

MIN_PROBES = 8
DEFAULT_MATCH_THRESHOLD = 0.9
DEFAULT_DRIFT_MARGIN = 0.1
LOW_MATCH_FLOOR = 0.5
SMP_DOES_NOT_PROVE = (
    "A MATCH means the endpoint's outputs matched the claimed model's reference "
    "fingerprint on the shared probes, which is consistent with the claim, not "
    "proof of the served weights or precision. The check is behavioral: two "
    "models that agree on the battery are indistinguishable to it, and sampling, "
    "batching, or quantization can move an output, so a battery of deterministic "
    "probes and a trusted reference are both required. A DRIFT means the outputs "
    "matched a known alternative better than the claim, or fell below the claim "
    "on the shared probes. UNVERIFIABLE means the shared probes were too few to "
    "call. A verdict covers the probed battery, nothing beyond it.")


class ProvenanceError(ValueError):
    """A malformed provenance claim or observed battery."""


def _index(battery, name) -> dict:
    if not isinstance(battery, list) or not battery:
        raise ProvenanceError(f"{name}: non-empty array")
    out = {}
    for i, probe in enumerate(battery):
        if not isinstance(probe, dict):
            raise ProvenanceError(f"{name}[{i}]: object")
        pid = probe.get("probe_id")
        if not isinstance(pid, str) or not pid:
            raise ProvenanceError(f"{name}[{i}].probe_id: non-empty string")
        if pid in out:
            raise ProvenanceError(f"{name}[{i}].probe_id: duplicate {pid!r}")
        if not isinstance(probe.get("output"), str):
            raise ProvenanceError(f"{name}[{i}].output: string")
        out[pid] = probe["output"]
    return out


def _rate(shared, observed, reference) -> float:
    return sum(observed[p] == reference[p] for p in shared) / len(shared)


def analyze(claim, observed, *, match_threshold=DEFAULT_MATCH_THRESHOLD,
            drift_margin=DEFAULT_DRIFT_MARGIN) -> dict:
    """Verify an endpoint's observed outputs against a claimed model's reference.

    `claim` carries the claimed_model, its reference battery, and optional
    reference batteries for known alternatives. `observed` is the battery the
    endpoint actually returned. The verdict is re-derivable from these inputs.
    """
    if not isinstance(claim, dict):
        raise ProvenanceError("claim: object")
    model = claim.get("claimed_model")
    if not isinstance(model, str) or not model:
        raise ProvenanceError("claim.claimed_model: non-empty string")
    if not (0.0 <= match_threshold <= 1.0) or not (0.0 <= drift_margin <= 1.0):
        raise ProvenanceError("thresholds: between 0 and 1")
    reference = _index(claim.get("reference"), "claim.reference")
    if len(reference) < MIN_PROBES:
        raise ProvenanceError(f"claim.reference: needs at least {MIN_PROBES} probes")
    obs = _index(observed, "observed")
    alternatives = claim.get("alternatives") or {}
    if not isinstance(alternatives, dict):
        raise ProvenanceError("claim.alternatives: object of model -> battery")

    shared = [p for p in reference if p in obs]
    if len(shared) < MIN_PROBES:
        return {
            "verdict": UNVERIFIABLE, "claimed_model": model,
            "probes_compared": len(shared), "claimed_match_rate": None,
            "best_alternative": None, "best_alternative_match_rate": None,
            "mismatched_probes": [], "does_not_prove": SMP_DOES_NOT_PROVE,
        }
    claimed_rate = round(_rate(shared, obs, reference), 4)

    best = None  # (name, alt_rate, claim_rate_on_same_subset)
    for name, battery in alternatives.items():
        alt = _index(battery, f"claim.alternatives[{name!r}]")
        subset = [p for p in shared if p in alt]
        if len(subset) < MIN_PROBES:
            continue
        a_rate = _rate(subset, obs, alt)
        c_rate = _rate(subset, obs, reference)
        if best is None or (a_rate - c_rate) > (best[1] - best[2]):
            best = (name, round(a_rate, 4), round(c_rate, 4))

    if best is not None and best[1] - best[2] >= drift_margin and best[1] >= match_threshold:
        verdict = DRIFT
    elif claimed_rate >= match_threshold:
        verdict = MATCH
    elif claimed_rate < LOW_MATCH_FLOOR:
        verdict = DRIFT
    else:
        verdict = UNVERIFIABLE
    return {
        "verdict": verdict, "claimed_model": model,
        "probes_compared": len(shared), "claimed_match_rate": claimed_rate,
        "best_alternative": best[0] if best else None,
        "best_alternative_match_rate": best[1] if best else None,
        "mismatched_probes": [p for p in shared if obs[p] != reference[p]][:20],
        "does_not_prove": SMP_DOES_NOT_PROVE,
    }
