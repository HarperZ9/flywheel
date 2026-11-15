# Contributing Proof Surface Research Cases

Proof-surface cases should help reviewers and implementers understand where
release evidence is strong, weak, malformed, overclaimed, or unverifiable.

## What a useful case contains

Each case in `research/proof-surface/v0.1/cases.json` needs:

- `case_id`: stable lowercase identifier.
- `description`: one sentence explaining the failure mode or strength.
- `packet`: the proof-surface packet under evaluation.
- `expected`: expected boolean values for every scoring dimension.

Required dimensions:

- `schema_valid`
- `evidence_coverage`
- `actionability`
- `non_authority_language`
- `witness_or_provenance_presence`

## Good case types

Add cases that expose a specific, reproducible surface:

- malformed packet shape;
- missing or vague evidence;
- non-actionable blocked states;
- authority or certification language;
- missing witness or provenance support;
- valid packets with clear evidence and bounded claims.

## What not to submit

Do not include:

- secrets, credentials, private URLs, or client data;
- claims that a model, release, or tool is trusted, safe, certified, compliant,
  authorized, or complete;
- private payloads as evidence;
- large generated artifacts;
- cases that require network access to score.

## Review principle

A good case teaches a failure mode. It should make the harness better at
measuring reviewability, not better at sounding authoritative.

## Local command

```bash
python scripts/score_proof_surface_research.py
```

The command must report the expected outcome for every case.
