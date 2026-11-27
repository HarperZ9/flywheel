# Dataset Attestation Gate

## Overview

`harness/dataset_attest` verifies `BuildDB Parquet` and `JFC3P` RLVR dataset packs in pure Python stdlib under the OSI MIT license. Every row is checked for strict `MIT` licensing, unique record or task IDs, valid 64-hex SHA-256 content digests, and finite non-boolean numeric fields.

## Split Disjointness and Fail-Closed Rules

Calling `verify_dataset_pack` or `verify_dataset_pack_files` returns an immutable `DatasetAttestReport` sealing `dataset_attestation_sha256` over the verified counts and artifact digests. The gate confirms exact `train` and `eval` split disjointness, verifies manifest artifact byte sizes and SHA-256 digests against disk files, and enforces the `100%` oracle pass-rate floor. Any non-MIT license leak, duplicate ID, train/eval overlap, digest mismatch, or `NaN`/`Inf`/`bool` pass rate fails closed.

## Scope Limits

This oracle checks JSON manifests, JSONL row purity, split disjointness, artifact SHA-256 digests, and finite pass-rate floors in pure Python stdlib. It does not parse binary Parquet column pages or run model training.
