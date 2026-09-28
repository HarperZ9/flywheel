#!/usr/bin/env python3
"""dataset_provenance.py -- the Dataset-Provenance Probe (DPP).

A training or evaluation dataset is a claim: these shards, from these sources,
with these hashes. "Distilled frontier data of unknown origin" is that claim left
unverifiable. DPP checks it. Given a dataset manifest that declares each shard's
hash and source, and the shards an evaluation actually saw, it verifies the
declared hashes, flags shards whose origin is unattributed, shards present but
undeclared, and duplicate content. Declared shards that match and are attributed
are MATCH; a hash mismatch, an undeclared shard, or an unknown-origin shard is
DRIFT; missing shards that leave the set incompletely covered are UNVERIFIABLE.

Hashes attest bytes, not content. A MATCH means the observed shards match the
manifest and carry a stated origin, not that the data is clean, unbiased, or
lawfully sourced; contamination and semantic quality beyond structure are out of
scope. Producing the observed shard list is a separate, upstream step. Standard
library only.
"""
from __future__ import annotations

import re

from .transitive_witness import DRIFT, MATCH, UNVERIFIABLE

_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")
_UNKNOWN = {"", "unknown", "unattributed", "n/a", "none"}
DEFAULT_COVERAGE = 1.0
DPP_DOES_NOT_PROVE = (
    "A MATCH means the observed shards match the declared manifest by hash and "
    "each carries a stated origin, not that the data is clean, unbiased, or "
    "lawfully sourced. Hashes attest bytes, not content, so contamination and "
    "semantic quality beyond structure (duplicate content, unattributed origin, "
    "undeclared shards) are out of scope. A DRIFT marks a hash mismatch, an "
    "undeclared shard, or an unknown-origin shard; UNVERIFIABLE marks incomplete "
    "coverage. A verdict covers the declared and observed shards, nothing beyond.")


class DatasetProvenanceError(ValueError):
    """A malformed dataset manifest or observed shard list."""


def _shards(entries, name, *, require_source):
    if not isinstance(entries, list) or not entries:
        raise DatasetProvenanceError(f"{name}: non-empty array")
    out = {}
    for i, s in enumerate(entries):
        if not isinstance(s, dict):
            raise DatasetProvenanceError(f"{name}[{i}]: object")
        sid = s.get("shard_id")
        if not isinstance(sid, str) or not sid:
            raise DatasetProvenanceError(f"{name}[{i}].shard_id: non-empty string")
        if sid in out:
            raise DatasetProvenanceError(f"{name}[{i}].shard_id: duplicate {sid!r}")
        h = s.get("sha256")
        if not isinstance(h, str) or not _HEX64.match(h):
            raise DatasetProvenanceError(f"{name}[{i}].sha256: 64 lowercase hex chars")
        if require_source and not isinstance(s.get("source"), str):
            raise DatasetProvenanceError(f"{name}[{i}].source: string")
        out[sid] = s
    return out


def analyze(manifest, observed, *, min_coverage=DEFAULT_COVERAGE) -> dict:
    """Verify a dataset's declared provenance against the shards observed.

    `manifest` declares dataset_id and shards (shard_id, sha256, source).
    `observed` is the shards an evaluation actually saw (shard_id, sha256). The
    verdict is re-derivable from these inputs.
    """
    if not isinstance(manifest, dict):
        raise DatasetProvenanceError("manifest: object")
    dsid = manifest.get("dataset_id")
    if not isinstance(dsid, str) or not dsid:
        raise DatasetProvenanceError("manifest.dataset_id: non-empty string")
    if not (0.0 <= min_coverage <= 1.0):
        raise DatasetProvenanceError("min_coverage: between 0 and 1")
    declared = _shards(manifest.get("shards"), "manifest.shards", require_source=True)
    obs = _shards(observed, "observed", require_source=False)

    present = [sid for sid in declared if sid in obs]
    missing = [sid for sid in declared if sid not in obs]
    undeclared = [sid for sid in obs if sid not in declared]
    hash_mismatch = [sid for sid in present if obs[sid]["sha256"] != declared[sid]["sha256"]]
    unknown_origin = [sid for sid in declared
                      if declared[sid].get("source", "").strip().lower() in _UNKNOWN]
    seen, duplicate_hashes = set(), set()
    for sid in declared:
        h = declared[sid]["sha256"]
        if h in seen:
            duplicate_hashes.add(h)
        seen.add(h)
    coverage = round(len(present) / len(declared), 4)

    if hash_mismatch or undeclared or unknown_origin:
        verdict = DRIFT
    elif coverage < min_coverage:
        verdict = UNVERIFIABLE
    else:
        verdict = MATCH
    return {
        "verdict": verdict,
        "dataset_id": dsid,
        "declared_count": len(declared),
        "observed_count": len(obs),
        "coverage": coverage,
        "hash_mismatch": hash_mismatch,
        "undeclared": undeclared,
        "missing": missing,
        "unknown_origin": unknown_origin,
        "duplicate_hash_count": len(duplicate_hashes),
        "does_not_prove": DPP_DOES_NOT_PROVE,
    }
