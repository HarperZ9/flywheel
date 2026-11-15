# Spec: behavior-transform.io Forward Delivery Contract

## Objective
Bring behavior-transform.io to the same private-line delivery floor as Seed,
Sofer, and Kun while preserving its IO-boundary runtime behavior.

## Requirements
- [x] Add missing root delivery files: `AUTHORS.md`, `CONTRIBUTING.md`,
  `LICENSE`, and `CHANGELOG.md`.
- [x] Make README public/developer delivery explicit with `Why it matters`,
  `Usage`, and `For developers` sections.
- [x] Extend the existing flagship doctor so root delivery files are part of
  the checked contract.
- [x] Normalize forward-facing delivery text so the public-surface scanner can
  produce a `MATCH` verdict.
- [x] Keep runtime behavior unchanged: no new live credential handling, no raw
  secret export, and no external writes from status/doctor/demo.

## Technical Approach
Use a docs and doctor-gate patch only. Add a targeted delivery contract test
first, then update required doctor files and root docs. The public-surface
sweeper remains the workspace-level delivery check.

## Files to Modify
- `tests/test_behavior_delivery_contract.py` - executable root delivery
  contract.
- `tools/behavior_flagship.py` - include delivery files in the doctor required
  file list.
- `README.md` - public value, usage, and developer workflow headings.
- `AUTHORS.md`, `CONTRIBUTING.md`, `LICENSE`, `CHANGELOG.md` - delivery files.
- Flagged forward-facing text files - punctuation normalization only.

## Success Criteria
- [x] `python -B -m pytest tests/test_behavior_delivery_contract.py -q`
  passes.
- [x] `python -B -m pytest tests/test_behavior_flagship.py tests/test_behavior_delivery_contract.py -q`
  passes.
- [x] `python -B tools/behavior_flagship.py doctor --json` exits 0.
- [x] `python -m public_surface_sweeper . --workspace --json` reports
  `behavior-transform.io` as `MATCH`.
- [x] `git diff --check` exits with status 0.

## Blockers
None identified.

## Status: IMPLEMENTED
