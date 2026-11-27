# Competitive Surpass Gate

## Overview

`harness/surpass_gate` verifies the 76-row Competitive Surpass Matrix against its source TSV signal registry in pure Python stdlib under the OSI MIT license. The gate checks a strict one-to-one partition between TSV rows and JSON signal entries, confirms sequential completeness across `CS-001` through `CS-076`, validates raw TSV SHA-256 digests, and cross-checks cited catalogue IDs against a live set.

## Verification Guarantees

Calling `verify_surpass_matrix` or `verify_surpass_matrix_files` returns an immutable `SurpassGateReport`. The report carries a boolean `passed` verdict, exact tier counts (`surpassed_with_receipt`, `parity_verified`, `open_next_wave_opportunity`), the unique catalogue ID count, the raw TSV SHA-256 digest, a deterministic `surpass_attestation_sha256`, and explicit violation messages. Any forged catalogue ID, missing signal, lane mismatch, tampered byte digest, or `NaN`/`Inf`/`bool` numeric entry triggers fail-closed rejection.

## Scope Limits

This oracle checks schema structure, count arithmetic, digest parity, and caller-provided catalogue membership in pure Python stdlib. It does not re-execute external compiler toolchains, GPU shaders, or third-party benchmarks.
