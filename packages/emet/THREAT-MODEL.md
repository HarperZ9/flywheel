# EMET Threat Model

This document models threats to EMET as an external integrity and accountability
witness, and states honestly where EMET does not protect. It complements SPEC.md
section 11 (honest limits) and COVERAGE.json (out of scope).

## Asset

The asset EMET protects is the trustworthiness of an operator judgement about
whether an artifact, a presented view, a read channel, or an accountability log
matches a re-derivable ground truth. EMET produces facts; the asset is that those
facts can be reproduced.

## Adversary

The adversary controls some part of the path between a model (or its operators)
and ground truth: the ability to alter artifacts, substitute a presented view for
the source, inject false authority into context, tamper one read channel, or edit
an accountability log. In the EMET model the adversary does NOT control the
operator, the external verifier of record, or the mathematics of SHA-256.

## STRIDE

- Spoofing -- a forged view presented as the source. Mitigated by coherence
  (source versus view hash compare) and by anchoring to raw source bytes.
- Tampering -- a changed artifact, a tampered read channel, or an edited log.
  Mitigated by verify (drift versus an anchor), corroborate (read-path divergence
  across disjoint reads), and audit (a hash-chained log). Residual: a threat that
  tampers ALL read paths identically defeats corroborate.
- Repudiation -- denial that a change happened. Mitigated by the append-only,
  hash-chained accountability log. Residual: the log proves integrity only
  relative to an uncompromised substrate; external anchoring (a transparency log
  or a timestamping authority) is required for non-repudiation against a
  compromised host, and is a LATER deliverable.
- Information disclosure -- not a primary EMET concern; EMET emits hashes and
  verdicts, never artifact contents (refuse reports marker offsets, never the
  surrounding bytes).
- Denial of service -- an adversary who removes the raw-byte channel forces
  UNVERIFIABLE. EMET fails safe: it reports inability, never substitutes trust.
- Elevation of privilege -- the load-bearing one. An adversary who could make
  EMET ASSERT authority, adjudicate a model decision, or run inside the audited
  system would convert the witness into an authority. The six boundaries
  (SPEC section 6) exist to make this structurally impossible: the verdict
  lattice cannot express TRUSTED, EMET holds no key, and EMET takes no action on
  the audited target of its own accord.

  CORRECTION (self-correcting register; SPEC governs): an earlier phrasing here
  read "EMET performs no action," which was overstated. EMET does write to its
  own implementation-private stores -- the anchor store (anchors.json), the
  hash-chained accountability log, the <file>.refused copy, and, on
  operator-authorized reanchor, the baseline manifest. The precise, scoped claim
  (SPEC section 6 boundary 6) is that EMET MUST NOT write to, edit, sign, back
  up, or revert the AUDITED TARGET -- the artifact under judgement -- of its own
  accord. None of the stores it does write is the target. "Zero actuation" means
  zero actuation ON THE AUDITED TARGET; the single actuator over the world is the
  operator.

## Residual attack surface (the honest part)

- Denylist incompleteness -- a novel injection with no known marker is not
  detected. The answer is corpus governance and continuous addition, never a
  completeness claim.
- Trust-root regress -- a compromised execution substrate re-derives a
  compromised self-hash consistently. selftest proves integrity only relative to
  an uncompromised substrate. An EXTERNAL verifier MUST be the check of record
  for EMET itself.
- Single-read-path collusion -- corroborate detects divergence; an adversary who
  tampers every disjoint read path identically is not caught at the byte layer.
- Semantic blindness -- EMET judges bytes and provenance, never meaning. A
  semantically harmful artifact with intact bytes passes verify by design.
- Coerced operator -- the single actuator is assumed uncoerced; coercion is out
  of model.

## Trust boundary

EMET sits OUTSIDE the system it audits and reports to the operator, never back
into the audited system. Wiring EMET inside the audited system, or making it its
own root of trust, is itself the primary threat and is forbidden by SPEC
section 6 boundary 3 and section 11.
