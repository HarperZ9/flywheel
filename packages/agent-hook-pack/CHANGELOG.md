# Changelog

## Unreleased

- Adds `AGENTS.md` for repeatable public/developer handoffs.
- Updates GitHub Actions workflows to current checkout/setup-python majors.
- Hardens hook audits with required-hook, empty-file, shebang, and
  credential-pattern checks.
- Removes broad staged-secret scan skips for test, honeypot, and canary files.
- Cleans hook comments and output to plain ASCII text.

## 0.1.0 - 2026-06-13

- Initial public release candidate.
- Ships local hook templates for secret checks, branch guardrails, environment
  sync checks, and lint-on-save workflows.
- Adds Python package metadata, CI, license, authorship, and contribution
  boundary files.
