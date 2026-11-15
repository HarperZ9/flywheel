# Spec: Accountable Engine Forward Delivery Contract

## Objective

Bring Accountable Engine to the shared Project Telos public/developer delivery
floor while preserving its role as a small, local accountability framework.

## Requirements

- [x] Add root `AGENTS.md`, `USAGE.md`, `CHANGELOG.md`, and implementation
  receipt.
- [x] Add CI that runs the documented PowerShell critic command.
- [x] Keep README language direct for public readers and developers.
- [x] Keep `STATE.template.md` and `.gitignore` scanner-compatible.
- [x] Preserve the local-only boundary: no secrets, private state, deployments,
  or external service calls.

## Technical Approach

Use documentation, CI, and text-normalization changes only. The existing
`critic.ps1` command remains the behavioral surface.

## Success Criteria

- [x] `powershell -NoProfile -ExecutionPolicy Bypass -File .\critic.ps1` exits 0.
- [x] `python -m public_surface_sweeper . --workspace --json` reports `MATCH`.
- [x] `git diff --check` exits 0.

## Status: IMPLEMENTED
