# Changelog

## 0.3.2 - 2026-10-22

- Licence: future releases are AGPL-3.0-only. Published releases up to 0.3.1
  keep their FSL-1.1-MIT terms and still convert to MIT two years after each
  release.
- Rewrites the README opening: what Chorus reports, install and first run from
  PyPI, a comparison with similar tools, and its limits. The PyPI summary
  changes to match.

## 0.3.1 - 2026-09-22

- Fixes the gather-to-chorus wiring gap. `normalize()` mapped only `feed_item`,
  so feed entries from a real gather corpus were dropped without a diagnostic and
  only YouTube comments reached the discourse surface. `feed-entry` now maps to
  the `feed` source, and `feed_item` is kept for back-compat.
- Adds an OIDC trusted-publishing release workflow with tag/version, artifact
  digest, clean-venv entry-point resolution, and sdist-rebuild gates.
- Publishes to PyPI as `chorus-discourse`. The console script stays `chorus`.

## 0.3.0 - 2026-09-07

- Adds `chorus decision` and MCP `chorus.decision`, a source-change review gate
  that compares current and reference gather-style source packs, reports
  added/removed/changed/unchanged item ids, verifies both deterministic Chorus
  digests, and returns typed `UNVERIFIABLE` failure states for missing, malformed,
  empty, or ambiguous source inputs.
- Adds a safe public projection for the review-gate result. It keeps counts,
  hashes, receipts, and limitations by default; human-readable public ids, source
  names, refs, and URLs require an operator-authored projection policy rather
  than source-row metadata. It excludes raw source text, author names, local paths,
  private sessions, and bulk comments.
- Hardens false-success controls for source packs: missing or malformed text,
  invalid, missing, mismatched, or non-UTF-8 Gather objects, duplicate ids, and
  absent, null, blank, or non-string ids return typed `UNVERIFIABLE` instead of
  being compared as unchanged.

This release does not decide whether a source claim is true, complete, or ready
for publication. `MATCH` means the compared source observations and fingerprints
are unchanged; `DRIFT` means a reviewer should inspect the changed source rows;
`UNVERIFIABLE` means source capture or identity must be repaired before reuse.

## 0.2.0 - 2026-09-07

- Adds deterministic corpus-salience theme labels with `label_quality` support metadata so weak and singleton labels are visible in the digest.
- Writes new receipts as `chorus-lens/3`, binding label terms and `label_quality` into the re-checkable digest body.
- Preserves historical `chorus-lens/2` verification through an explicit legacy verifier. v2 receipts verify against the v2 body shape and do not bind the current v3-only `terms` and `label_quality` fields.
- Fixes receipt verification so the submitted digest body must match its receipt before the verifier accepts a re-derived body.

This release does not claim better semantic insight from comment corpora. It reduces generic-label false success on the included controls and labels weak support, while lexical clustering remains a known limitation.

## 0.1.0

- Initial discourse synthesis package with CLI, MCP stdio surface, daemon, deterministic sentiment, lexical clustering, contested aspects, and re-checkable receipts.
