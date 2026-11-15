# Changelog

## 2026-06-29 - Public And Developer Delivery Contract

- Added `AGENTS.md`, `USAGE.md`, `CHANGELOG.md`, and a forward-delivery spec.
- Added GitHub Actions CI for the PowerShell critic.
- Updated README copy so public readers and developers can quickly understand
  the tool, run it, and verify the repository.
- Normalized punctuation in public templates for scanner compatibility.

## Current Status

- Runtime: Windows PowerShell reference script.
- Surfaces: README, usage guide, state template, critic script, funding metadata,
  brand asset, and CI workflow.
- Verification: `powershell -NoProfile -ExecutionPolicy Bypass -File .\critic.ps1`
  plus public surface sweep.
