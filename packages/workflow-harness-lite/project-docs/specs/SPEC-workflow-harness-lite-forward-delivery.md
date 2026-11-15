# Spec: Workflow Harness Lite Forward Delivery Contract

## Objective

Bring Workflow Harness Lite to the shared Project Telos public/developer
delivery floor while preserving bounded local workflow and receipt behavior.

## Requirements

- [x] Add root `AGENTS.md` and implementation receipt.
- [x] Keep README, USAGE, CHANGELOG, examples, tests, package metadata, and CI
  aligned.
- [x] Update GitHub Actions workflows to current action majors.
- [x] Normalize forward-facing punctuation so the public-surface scanner reports
  a clean boundary.

## Technical Approach

Use a documentation, metadata, and CI-only patch. Existing Node tests remain the
behavioral authority.

## Success Criteria

- [x] `npm test` passes.
- [x] `npm pack --dry-run` passes.
- [x] `python -m public_surface_sweeper . --workspace --json` reports `MATCH`.
- [x] `git diff --check` exits 0.

## Status: IMPLEMENTED
