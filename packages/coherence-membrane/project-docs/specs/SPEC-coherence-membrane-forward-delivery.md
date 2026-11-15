# Spec: Coherence Membrane Forward Delivery Contract

## Objective

Bring Coherence Membrane to the shared Project Telos public/developer delivery
floor while preserving inert perception, drift, receipt, and conformance
behavior.

## Requirements

- [x] Add root `AGENTS.md`, `USAGE.md`, `CHANGELOG.md`, and implementation
  receipt.
- [x] Keep README, schemas, conformance vectors, Python package, JavaScript
  parity implementation, tests, and CI aligned.
- [x] Update GitHub Actions workflows to current action majors.
- [x] Add package repository, issues, and homepage metadata.
- [x] Normalize forward-facing punctuation so the public-surface scanner reports
  a clean boundary.

## Technical Approach

Use a documentation, metadata, and CI patch. Existing tests and conformance
vectors remain the behavioral authority.

## Success Criteria

- [x] `python -m pytest` passes.
- [x] `python conformance/run.py` passes.
- [x] `node impl/js/run.js` passes.
- [x] `python -m coherence_membrane selftest` passes.
- [x] `python -m public_surface_sweeper . --workspace --json` reports `MATCH`.
- [x] `git diff --check` exits 0.

## Status: IMPLEMENTED
