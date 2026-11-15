# Changelog

## 2026-06-29 - Forward Delivery Contract

- Documented GitHub tag and source-checkout install paths while PyPI has no
  `secret-redact-io` project.
- Added `project-docs/specs/SPEC-secret-redact-io-forward-delivery.md` as the
  implementation receipt for the delivery pass.
- Updated GitHub Actions to current checkout/setup-python action majors.
- Added package repository, issues, and homepage metadata.
- Normalized forward-facing punctuation for public-surface scanner
  compatibility.
- Kept redaction, guarded IO, receipt generation, CLI behavior, and public
  boundary checks unchanged.

## Current Status

- Runtime: Python 3.10+ with stdlib-only guarded file, fetch, and subprocess IO.
- Surfaces: Python package, CLI, examples, usage guide, redaction receipts, and
  public boundary checker.
- Verification: pytest suite, public-surface checker, and package build.
