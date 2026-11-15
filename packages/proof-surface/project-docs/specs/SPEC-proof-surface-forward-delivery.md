# Spec: Proof Surface Forward Delivery Contract

## Objective

Bring Proof Surface to the shared Project Telos public/developer delivery floor
while preserving validator, schema, and conformance behavior.

## Requirements

- [x] Add root `AGENTS.md`, `CHANGELOG.md`, and a delivery regression test.
- [x] Keep README, usage guide, schemas, conformance vectors, examples, and
  developer verification path aligned.
- [x] Update CI to current GitHub Actions majors.
- [x] Add package repository, issues, and homepage metadata.
- [x] Normalize forward-facing punctuation so the public-surface scanner reports
  a clean public/developer boundary.

## Technical Approach

Use a documentation, metadata, CI, and test-only patch. Existing unit tests and
conformance vectors remain the behavioral authority; the new delivery test only
checks public/developer packaging.

## Files Modified

- `AGENTS.md` - repo-specific operating boundary.
- `CHANGELOG.md` - current status and delivery history.
- `tests/test_forward_delivery_contract.py` - executable delivery contract.
- `.github/workflows/ci.yml` - current checkout/setup-python actions.
- `README.md`, `USAGE.md`, `pyproject.toml` - public/developer links and
  metadata.
- Existing docs/source text - punctuation normalization only.

## Success Criteria

- [x] `python -m pytest` passes.
- [x] `python -m public_surface_sweeper . --workspace --json` reports `MATCH`.
- [x] `git diff --check` exits 0.

## Blockers

None identified.

## Status: IMPLEMENTED
