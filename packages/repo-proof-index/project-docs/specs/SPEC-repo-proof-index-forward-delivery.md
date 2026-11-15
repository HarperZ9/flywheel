# Spec: Repo Proof Index Forward Delivery Contract

## Objective

Bring Repo Proof Index to the shared Project Telos public/developer delivery
floor while preserving its proof-artifact indexing behavior.

## Requirements

- [x] Keep README, USAGE, CHANGELOG, AGENTS, CI, funding metadata, examples,
  schemas, and conformance fixtures aligned.
- [x] Add an executable delivery regression test for public/developer packaging.
- [x] Update GitHub Actions workflows to current action majors.
- [x] Add package repository, issues, and homepage metadata.
- [x] Normalize forward-facing punctuation so the public-surface scanner reports
  a clean boundary.

## Technical Approach

Use a documentation, metadata, CI, and test-only patch. Existing indexer, CLI,
schema, and conformance tests remain the behavioral authority.

## Success Criteria

- [x] `python -m pytest` passes.
- [x] `python scripts/check_proof_surface_conformance.py` passes.
- [x] `python scripts/export_proof_surface_contract.py --out <temp>` passes.
- [x] `python scripts/score_proof_surface_research.py` passes.
- [x] `python -m public_surface_sweeper . --workspace --json` reports `MATCH`.
- [x] `git diff --check` exits 0.

## Status: IMPLEMENTED
