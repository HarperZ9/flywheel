# Security Policy

## Supported

EMET 1.x is supported at the latest release on the default branch. The frozen
1.0 contract governs all 1.x releases.

## Reporting a vulnerability

Report suspected vulnerabilities privately via GitHub Security Advisories -- the
"Security" tab of this repository, then "Report a vulnerability". Do NOT open a
public issue for an unfixed vulnerability.

Please include: the affected file and version (the selftest self-hash), a
reproduction (ideally a conformance vector that fails), and the impact.

Coordinated disclosure: the maintainer will acknowledge within a stated window
and agree a disclosure date. A CVE or CNA path is a LATER deliverable and is not
yet staffed; do not assume a CVE will be issued before that is in place.

## What counts as a vulnerability

- A way to make EMET emit a verdict outside the closed lattice (SPEC section 2),
  in particular anything that reads as TRUSTED.
- A way to make `adapters/proof_surface_receipt.py` carry an authority-shaped
  core stdout token into a proof-surface receipt.
- A way to make verify, coherence, corroborate, or audit report a false MATCH,
  COHERENT, CORROBORATED, or INTACT on tampered input.
- A way to make EMET act on a target (write, sign, enforce) -- a boundary 6
  violation.
- A marker bypass that evades refuse on a signature already in the corpus.

## What does not count

- Denylist incompleteness (a novel, unknown-marker injection). This is a
  documented limitation, not a vulnerability (SPEC section 11, THREAT-MODEL.md).
  Submit it as a corpus addition.
- A compromised execution substrate producing a consistent compromised
  self-hash. This is the documented trust-root regress; the fix is an external
  verifier, not an EMET change.

## Scope of the marker corpus

The marker corpus is data, distributed WITHOUT WARRANTY and without any
completeness guarantee. It is a known-signature denylist, not a proof of
cleanliness.
