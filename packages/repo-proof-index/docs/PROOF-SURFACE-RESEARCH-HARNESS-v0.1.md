# Proof Surface Research Harness v0.1

Status: draft research harness.

Purpose: measure whether public AI-assisted release evidence is structured,
bounded, reviewable, and actionable.

This harness does not decide whether a claim is true, safe, compliant, trusted,
or complete. It measures the quality of the evidence surface around the claim.

## Scoring dimensions

`schema_valid`: the packet satisfies the proof-surface packet v0.1 contract.

`evidence_coverage`: every claim has a concrete evidence string, and the packet
contains at least one claim.

`actionability`: blocked or needs-polish packets contain at least one action
item. Ready packets may have an empty action list.

`non_authority_language`: the packet does not use authority or certification
language such as trusted, approved, safe, authorized, certified, or compliant.

`witness_or_provenance_presence`: at least one check references a witness,
provenance, receipt, or EMET-style verification source.

## Dataset

The v0.1 dataset lives at:

```text
research/proof-surface/v0.1/cases.json
```

The initial cases cover:

- valid release evidence;
- malformed packet shape;
- missing claim evidence;
- overclaiming authority language;
- missing witness or provenance support.

Contribution guidance lives at:

```text
docs/PROOF-SURFACE-CASE-CONTRIBUTING.md
```

## Runner

Run:

```bash
python scripts/score_proof_surface_research.py
```

The runner exits nonzero when any case result differs from the expected
dimension values in the dataset.

## Boundary

The harness is a measurement tool. It should make claims easier to inspect and
failure modes easier to reproduce. It must not become a trust oracle.
