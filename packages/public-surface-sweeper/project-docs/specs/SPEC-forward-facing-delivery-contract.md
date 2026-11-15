# Spec: Forward-Facing Repository Delivery Contract

## Objective

Make every GitHub-facing repository auditable for two audiences:

- public readers who need to understand what the project is, why it exists,
  whether it is current, and how to evaluate trust boundaries;
- developers and agents who need install, usage, test, automation, and
  handoff instructions without guessing.

The contract must stay deterministic, offline, dependency-light, and safe for
workspace-scale sweeps.

## Requirements

- [x] Keep the existing required-file, secret-shape, README delivery, proof
  packet, and workspace matrix behavior.
- [x] Add public-delivery warnings for missing release/status surfaces such as
  changelog or release notes and GitHub sponsor/funding metadata.
- [x] Add developer-delivery warnings for missing agent instructions, usage
  documentation, and CI/workflow evidence.
- [x] Preserve privacy boundaries in workspace mode: no absolute local paths,
  no raw secret values, no network calls, and no filesystem writes.
- [x] Keep findings actionable with normalized rule names that can feed
  Project Telos receipt chains.
- [x] Update README, USAGE, and changelog so public and developer users know
  what the stronger contract checks.

## Technical Approach

Introduce a focused delivery-contract module and call it from the existing
scanner. This avoids growing the current scanner file further and lets the
workspace matrix classify the new rules into public and developer verdicts.

## Files to Modify

- `src/public_surface_sweeper/sweeper.py` - call delivery-contract checks.
- `src/public_surface_sweeper/delivery_contract.py` - new contract checks.
- `src/public_surface_sweeper/workspace.py` - classify new rules by audience.
- `tests/test_sweeper.py` - red/green coverage for contract checks.
- `tests/test_workspace.py` - workspace verdict coverage for new rules.
- `README.md` - explain the two-audience contract.
- `USAGE.md` - document workspace and rule behavior.
- `CHANGELOG.md` - record the contract addition.

## Success Criteria

- [x] `python -m pytest tests/test_sweeper.py tests/test_workspace.py -q`
  passes.
- [x] `public-surface-sweeper examples/clean-repo --summary` reports ready.
- [x] `public-surface-sweeper path/to/workspace/public-surface-sweeper --workspace --json`
  returns a privacy-preserving matrix.
- [x] `python -m compileall -q src` passes.
- [x] `git diff --check` passes.

## Blockers

None identified.

## Status: IMPLEMENTED

Approved by the operator's current forward-facing repository delivery request
and standing approval to proceed without additional gating.
