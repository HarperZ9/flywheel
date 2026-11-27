# Search-Forge Provenance Package (`harness/search_forge`)

License: MIT (SPDX-License-Identifier: MIT)
Dependencies: Python standard library only (zero third-party runtime packages)

## Overview

This package implements three fail-closed provenance primitives for grounded retrieval, independent corroboration, and lineage verification:

1. `citation_verifier.py` (N43): Out-of-band FIPS 180-4 SHA-256 byte-offset span verifier that validates every cited substring against raw source bytes and rejects hallucinated quotes, shifted offsets, out-of-bounds slices, and source digest mismatches fail-closed.
2. `second_channel.py` (N27): Mandatory typed orthogonal `second_channel` envelope enforcer requiring a distinct corroboration modality observed at or after the primary timestamp, rejecting empty channels, same-channel self-corroboration, unknown channel types, causal reversals, and tampered envelope digests fail-closed.
3. `refit_dag.py` (N32): Deterministic provenance DAG (`source_sha256 -> crop_bbox -> quote_hash -> claim_hash`) with normalized bounding-box checks, strict stage monotonicity, Kahn topological-sort cycle detection, dangling-parent orphan rejection, and canonical SHA-256 DAG root sealing.

## Explicit Honest Scope Limits

1. `citation_verifier.py` proves byte-exact membership inside the caller-supplied corpus store; acquiring and timestamping authoritative source snapshots remains the caller's responsibility.
2. `second_channel.py` checks structural channel orthogonality, timestamp ordering, and SHA-256 envelope integrity in software; physical isolation of the underlying sensor or build host is enforced outside this module.
3. `refit_dag.py` validates lineage structure, bounding-box normalization, and cryptographic node linkage; OCR or visual transcription fidelity within a crop region is checked by separate extractors.
