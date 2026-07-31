# local-model

Agent and contributor instructions for the epistemic verification engine. This
file is self-contained: it names no local path and assumes no parent directory,
because this repository is published and cloned on its own.

## What this repo is
The verification harness and its evidence layer: the certificate families
(Zarankiewicz, rectilinear crossing, matmul), the pool-and-arms measurement
apparatus, the receipt / ledger / bundle stack, and the lane surface in
`harness/lanes.py`. Zero runtime dependencies is a load-bearing invariant, and
the verifier path is stdlib-only with a gate that proves it.

## Gates that must stay green (run before a commit that touches them)
- `python scripts/check_file_gate.py` — no file over 300 lines; the burn-down only shrinks.
- `python scripts/check_verifier_stdlib.py` — the accept path imports no third party.
- `python scripts/check_claim_language.py` — no optimality claim on a public surface.
- `python scripts/check_public_instructions.py` — published instruction files stand alone.
- `python -m harness.cli_entry gate` — the disproof gate reaches PASS / rewitness MATCH.
- `python -m pytest tests/ -q` — the full suite. CI runs a curated slice plus the
  whole suite; a slice cannot catch a regression in a file it does not name, so
  the whole-suite job is the real gate.

## Invariants
- No learned model on the accept path. A checker decides; a model never does.
- No receipt, no accept. Every result carries its denominator, coverage, and
  `does_not_prove`. Nulls are published, not edited out.
- Every checker verifies a SUBMITTED object; none decides optimality.
  `NOT_PROVES_OPTIMALITY` travels on every certificate result, and the claim gate
  enforces it on public surfaces.
- A new certificate family needs a second, independently written checker before
  any selection comparison on it is two-sided.
- Truth over approval. Verify a specific claim or label it high / moderate / low /
  unknown. "Unknown" beats a plausible fabrication.

## Hygiene
Never commit secrets, `.env` files, tokens, or private material to this public
repository. Verify before every commit. Branch before committing to a default
branch.
