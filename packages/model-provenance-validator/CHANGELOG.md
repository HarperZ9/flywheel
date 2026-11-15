# Changelog

## Unreleased

- Refreshes GitHub Actions workflows to current first-party action majors and
  removes the temporary Node runtime forcing workaround.
- Adds schema `pattern` support and requires `references[].retrieved_at` to use
  `YYYY-MM-DD` date shape.
- Requires `references[].retrieved_at` to be a valid calendar date.
- Redacts credential-shaped strings and local absolute paths from validation
  messages.
- Emits result paths relative to the current directory when possible.
- Aligns proof-surface packet validation with required claim/check rows.

## v0.1.1 - 2026-06-14

- Adds proof-surface packet output for provenance validation handoffs.
- Adds release-artifact packaging workflow and release checklist.
- Keeps validation structural: the tool checks envelope shape, not claim truth.

## v0.1.0 - 2026-06-12

- Initial public release of dependency-light provenance envelope validation.
