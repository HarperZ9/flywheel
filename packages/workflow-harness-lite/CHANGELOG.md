# Changelog

## 2026-06-29 - Forward Delivery Contract

- Added `AGENTS.md` and
  `project-docs/specs/SPEC-workflow-harness-lite-forward-delivery.md`.
- Updated GitHub Actions workflows to current checkout/setup-node action majors.
- Normalized forward-facing punctuation for public-surface scanner
  compatibility.
- Kept workflow execution, redaction, reporting, Telos receipt shape, and CLI
  behavior unchanged.

## Unreleased

- Adds Project Telos bounded-run receipts with terminal status, command hashes,
  output hashes, timeout bounds, and explicit privacy gates.
- Exposes `--telos-receipt` in the CLI and `buildTelosReceipt()` in the API.
- Redacts credential-shaped stdout/stderr before writing task reports.
- Caps output previews and exposes `--output-limit` for CLI runs.

## 0.1.0 - 2026-06-13

- Initial public release candidate.
- Ships a dependency-free Node.js workflow runner with serial/parallel task
  execution and machine-readable reports.
- Adds npm package metadata, CI, license, authorship, and contribution boundary
  files.
