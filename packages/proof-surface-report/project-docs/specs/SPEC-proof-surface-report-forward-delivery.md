# Spec: Proof Surface Report Forward Delivery Contract

## Objective

Bring Proof Surface Report to the shared Project Telos public/developer delivery
floor while preserving report rendering and guarded-language behavior.

## Requirements

- [x] Add root `AGENTS.md`, current changelog, and implementation receipt.
- [x] Keep README, USAGE, examples, tests, and CI aligned.
- [x] Update GitHub Actions workflows to current action majors.
- [x] Add package repository and issues metadata.
- [x] Normalize forward-facing punctuation so the public-surface scanner reports
  a clean boundary.

## Technical Approach

Use a documentation, metadata, and CI-only patch. Existing tests remain the
behavioral authority for report rendering and language checks.

## Success Criteria

- [x] `python -m pytest` passes.
- [x] `python -m public_surface_sweeper . --workspace --json` reports `MATCH`.
- [x] `git diff --check` exits 0.

## Status: IMPLEMENTED
