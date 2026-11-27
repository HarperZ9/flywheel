# Accountability Floor Package (`harness/accountability_floor`)

License: MIT (SPDX-License-Identifier: MIT)
Dependencies: Python standard library only (zero third-party runtime packages)

## Overview

This package implements four fail-closed accountability primitives for evaluating autonomous coding and research loops without self-grading:

1. `honest_exit_valve.py` (N25): Zero-penalty honest-exit reseating valve and hard budget cap comparing unguarded, penalized-abstain, and zero-penalty valve arms across solvable and unsolvable probes.
2. `planted_negatives.py` (N28 + Moat 8): Universal three-control negative validator (false-pass, false-fail, permutation null) paired with the Moat 8 three-plate structural consensus gate (surface/schema, invariant/conservation, and independent mutant-kill).
3. `anti_self_audit.py` (N49): Append-only FIPS 180-4 SHA-256 audit chain that rejects self-attestation (`proposer_id == verifier_id`), broken links, and tampered records offline, plus bit-exact 32-step binary chain parity.
4. `rsi_closed_loop.py` (STA-070): Closed-loop recursive self-improvement auditor contrasting Arm A (unguarded Goodhart collapse to -4.0 true capability across 180 accepted hacks) against Arm B (strictly monotone 8.953x compounding across 80 SHA-256 chained Step-5 tools, 0 accepted hacks, and 20 of 20 honest abstentions).

## Explicit Honest Scope Limits

1. `rsi_closed_loop.py` and `honest_exit_valve.py` model controlled synthetic benchmark regimes to verify gate invariants and bit-exact parity with native BuildLang kernels; they do not replace domain-specific hardware or production security audits.
2. `anti_self_audit.py` enforces cryptographic link integrity and proposer/verifier identity separation in software; hardware-rooted key custody remains outside this module and is handled separately by TPM or HSM layers.
3. `planted_negatives.py` validates supplied negative-control outcomes; callers remain responsible for keeping test fixtures isolated from training or proposing loops.
