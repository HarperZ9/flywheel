# Zero-Egress Enclave Package (`harness/zero_egress_enclave`)

License: MIT (SPDX-License-Identifier: MIT)
Dependencies: Python standard library only (zero third-party runtime packages)

## Overview

This package implements three offline verification primitives with zero third-party runtime dependencies:

1. `enclave_policy.py` (N46): Sovereign zero-egress policy enforcer that blocks outbound network URLs, raw IPv4 endpoints, socket attempts, PII/secret/local-path leakage, and memory or CPU budget overflows while sealing input and output FIPS 180-4 SHA-256 receipts verifiable offline.
2. `schedule_epigenetics.py` (N33 / J13): Weights-only optimizer-schedule and reward-history classifier separating AdamW cosine, SGD constant-LR, and reward-hacked shortcut trajectories at matched final loss with 0 inference calls (95.8333% held-out 3-class accuracy vs 34.6528% 60-trial permutation null), matching native BuildLang kernel `epigenetics_schedule_study.bld` (STA-059).
3. `reasons_ood_gate.py` (N39): Two-arm causal-reason versus label-only OOD spurious-flip gate contrasting Arm A shortcut collapse against Arm B causal invariance (>= 90% OOD accuracy) and failing closed when spurious cues leak into the reason mask, matching native BuildLang kernel `reasons_generalization.bld` (STA-060).

## Explicit Honest Scope Limits

1. `enclave_policy.py` enforces policy checks, regex egress/PII scanning, resource ceilings, and cryptographic receipt sealing in software; OS-level network namespaces, seccomp filters, and hardware TPM enclaves remain outside this pure-Python module.
2. `schedule_epigenetics.py` and `reasons_ood_gate.py` evaluate deterministic controlled synthetic benchmarks to verify mathematical parity with compiled BuildLang kernels; large-scale neural checkpoint audits require domain-specific spectral extractors.
