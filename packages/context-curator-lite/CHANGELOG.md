# Changelog

## Unreleased

No changes yet.

## 0.2.0 - 2026-09-18

- Refreshes public/developer delivery with repo-local agent instructions,
  current GitHub Actions majors, and ASCII-safe public documentation.
- Adds optional Project Telos context-envelope export with source refs,
  content hashes, expansion commands, and explicit privacy gates.
- Exposes `--telos-envelope` in the CLI and `telos_envelope=True` in the
  Python API for receipt-chained large-context workflows.
- Omits absolute local root paths from generated bundles by default.
- Uses relative source references plus root/source hash prefixes.
- Uses the current run date in context output filenames.

## 0.1.0 - 2026-06-13

- Initial public release candidate.
- Ships context extraction, planning-fragment collection, and heuristic
  redaction helpers for local assistant workflows.
- Adds Python package metadata, CI, license, authorship, and contribution
  boundary files.
