# Changelog

## Unreleased

- Nothing yet.

## v0.2.0 - 2026-09-13

- Keeps producer-reported proof status separate from Repo Proof Index's own
  verification state with `producer_status`, `verification_state`, and summary
  `verification_states` output.
- Keeps producer-declared green proof-surface and research-claim packets visible
  as action items while they remain `not_verified` by Repo Proof Index.
- Rejects ambiguous or unsafe JSON before indexing or proof-surface validation:
  duplicate keys, `NaN`, `Infinity`, overflowing floats, oversized files, and
  excessive nesting.
- Recognizes research-claim proof packets without executing packet-supplied
  verifier commands or treating claimed hashes as semantic proof.
- Adds organ-row provenance indexing.
- Adds `project-docs/specs/SPEC-repo-proof-index-forward-delivery.md` and a
  delivery regression test for public/developer packaging.
- Updates GitHub Actions workflows to current action majors.
- Normalizes forward-facing punctuation for public-surface scanner
  compatibility.
- Hardens proof-surface v0.1 validation so `claims` and `checks` must each
  contain at least one item.
- Adds an invalid conformance fixture for empty proof-surface evidence carriers.
- Adds public usage documentation, examples, and repo art for the current index
  and review lanes.

## 2026-06-29 - Forward Delivery Contract

- Public surface scanner status: `MATCH`.
- Behavioral scope unchanged: indexer, CLI, schema validation, conformance
  export, and research harness behavior remain covered by existing tests.

## v0.1.1 - 2026-06-14

- Adds strict proof-surface v0.1 packet validation.
- Adds proof-surface conformance fixtures, contract export, and research scoring
  harness.
- Adds release-artifact packaging workflow and release checklist.

## v0.1.0 - 2026-06-12

- Initial public release of proof artifact indexing and summary output.
