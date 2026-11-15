# Spec: EMET Forward Delivery Contract

## Objective
Bring EMET to the same forward-facing delivery floor as the other Project Telos
state/private-line repositories while preserving EMET's advisory-only witness
model.

## Requirements
- [x] Add `CHANGELOG.md` and a substantive README visual asset.
- [x] Make README public/developer delivery explicit with `Why it matters`,
  `Usage`, and `For developers` sections.
- [x] Keep EMET's closed verdict lattice and advisory-only boundary unchanged.
- [x] Rename credential-shaped documentation variables without changing the
  advisory examples.
- [x] Normalize forward-facing delivery text so the public-surface scanner can
  produce a `MATCH` verdict.
- [x] Add an executable delivery regression test using stdlib `unittest`.

## Technical Approach
Use a documentation and test-only patch. Add a targeted delivery contract test,
then add the missing changelog, README visual/sections, documentation variable
renames, and mechanical punctuation normalization. Do not change verifier behavior,
conformance vectors, or implementations.

## Files to Modify
- `test_forward_delivery_contract.py` - executable delivery contract.
- `README.md` - visual asset plus public/developer delivery headings.
- `CHANGELOG.md` - current status and delivery history.
- `assets/emet-hero.svg` - repository visual asset.
- Flagged documentation files - punctuation normalization only.
- Three scope-discipline docs - credential-shaped illustrative variables renamed.

## Success Criteria
- [x] `python test_forward_delivery_contract.py` passes.
- [x] `python test_membrane.py`, `python test_corpus.py`,
  `python test_monitor.py`, `python test_organs.py`,
  `python test_proof_surface_receipt.py`, and `python test_walkthrough.py`
  pass.
- [x] `python conformance/run.py membrane.py` passes.
- [x] `python conformance/run.py impl/js/emet.js` passes.
- [x] Rust implementation builds with `rustc` and passes conformance.
- [x] `python membrane.py selftest` exits 0.
- [x] `python -m public_surface_sweeper . --workspace --json` reports EMET as
  `MATCH`.
- [x] `git diff --check` exits with status 0.

## Blockers
None identified.

## Status: IMPLEMENTED
