# Spec: Secret Redact IO Forward Delivery Contract

## Objective

Bring Secret Redact IO to the shared Project Telos public/developer delivery
floor while preserving guarded IO, redaction, and receipt behavior.

## Requirements

- [x] Keep README, USAGE, AGENTS, examples, tests, public-boundary docs, and CI
  aligned.
- [x] Add a current changelog and implementation receipt.
- [x] Update GitHub Actions workflows to current action majors.
- [x] Add package repository, issues, and homepage metadata.
- [x] Normalize forward-facing punctuation so the public-surface scanner reports
  a clean boundary.

## Technical Approach

Use a documentation, metadata, and CI-only patch. Existing tests and the public
surface checker remain the behavioral authority.

## Success Criteria

- [x] `python -m pytest` passes.
- [x] `python scripts/check_public_surface.py` passes.
- [x] `python -m build` passes.
- [x] `python -m public_surface_sweeper . --workspace --json` reports `MATCH`.
- [x] `git diff --check` exits 0.

## Status: IMPLEMENTED
