# Meta-Verifier Package (`harness/meta_verifier`)

License: MIT (SPDX-License-Identifier: MIT)
Dependencies: Python standard library only (zero third-party runtime packages)

## Overview

This package implements three fail-closed verification primitives for mapping fidelity, epistemic calibration, and honest-reporting mechanism design:

1. `isomorphism_entropy.py` (D6): Computes Shannon entropy `H(X)`, `H(Y)`, and conditional entropy `H(X | Y)` across schema or format projections, proving lossless bijection (`H(X | Y) == 0.0` bits and exact `decode(encode(x)) == x` round-trips) while catching many-to-one lossy projections, collisions, and inverse mismatches fail-closed.
2. `confidence_calibration.py` (N30): Maps linguistic certainty terms (`high`, `moderate`, `hedged`) against empirical accuracy, sample size, and expected calibration error (`ece`), rejecting overclaimed certainty on weak, under-sampled, or uncalibrated evidence fail-closed.
3. `disclosure_game.py` (N71): Evaluates expected payoffs of honest defect disclosure versus concealment under audit probability, fine, and reward clawback parameters, computing the exact minimum deterrence audit threshold `p*` and rejecting profitable concealment regimes fail-closed.

## Explicit Honest Scope Limits

1. `isomorphism_entropy.py` measures empirical conditional entropy over the caller-supplied sample set; formal equivalence across infinite domains still requires structural or symbolic proofs.
2. `confidence_calibration.py` inspects deterministic regex certainty bands against supplied metrics; nuanced discourse implicatures outside the registered lexeme bands are not parsed.
3. `disclosure_game.py` models risk-neutral expected-utility agents under known audit probabilities; behavioral risk aversion and collusive auditor capture are outside this single-stage model.
