# Chorus source-change review gate

- Date: 2026-09-07
- Status: implemented on a feature branch
- Scope: Chorus CLI and MCP only. No new server, no publication path, no
  Flywheel gateway edits.

## Problem

A release or research operator often has two source packs: a reference pack that
previously supported a synthesis or release note, and a current pack that may
have changed. A plain digest says what the current discourse looks like, but it
does not answer whether the evidence set itself changed enough to review before
publishing or shipping.

The workflow should turn an ordinary source comparison into a useful review-gate
artifact: task, source packs, deterministic checks, digest outline, change
counts, and a bounded public projection.

## Existing seams used

- Input contract: gather-style JSON row lists or gather corpus directories with
  `catalog.jsonl`.
- Normalization: `chorus.item.normalize`.
- Deterministic check: `chorus.sentiment.score`, `chorus.synthesize.synthesize`,
  and `chorus.receipt.verify`.
- Surfaces: existing `chorus` CLI and stdio MCP server.

## Contract

`chorus decision <current> --reference <reference> --task "<task>"` returns
`chorus.source-decision/v1`.

The result reports:

- `MATCH`, `DRIFT`, or `UNVERIFIABLE`.
- Added, removed, changed, and unchanged item ids.
- Text and item hashes for changed source rows, not raw source text.
- Verification status and input hashes for both current and reference digests.
- A local digest outline derived from the same deterministic Chorus path.
- Typed source failures such as missing path, malformed JSON, empty discourse,
  missing ids, or duplicate ids.

`--public` and MCP argument `public: true` return
`chorus.public-source-decision/v1`, a safe default projection with counts,
hashes, receipt, checks, and limitations only. Human-readable public ids, source
names, refs, and source URLs require a separate operator-authored projection
policy. Raw source rows and Gather-derived metadata cannot self-authorize public
output.

## Non-goals and boundaries

- Does not fetch sources; gather owns capture and provenance.
- Does not publish to Bulletin, social surfaces, or a hosted app.
- Does not expose raw source text, author names, local paths, private sessions,
  or bulk comments in the public projection.
- Does not treat `http(s)` URLs as automatically public. Public projection of a
  source URL requires an operator-owned policy, not source-controlled row
  metadata.
- Does not claim completeness. `MATCH` means compared item ids and fingerprints
  matched; it does not prove no relevant source exists elsewhere.
- Does not decide product readiness by itself. `DRIFT` means review the changed
  evidence before reusing the old synthesis or release note.

## Acceptance controls

- Ordinary control: current and reference source packs with one added row, one
  removed row, one changed row, and one unchanged row return `DRIFT` with exact
  counts and verified current/reference digest receipts.
- Falsification control: same item id with altered text returns `DRIFT` even when
  both individual Chorus digests verify.
- Missing-source control: absent current or reference path returns typed
  `UNVERIFIABLE`, not a traceback or protocol failure.
- Public-projection control: raw source text from both current and reference rows
  is absent from the public JSON result.
- Malformed-row controls: inline discourse rows with missing, non-string, or empty
  text return typed `UNVERIFIABLE`; corpus-dir rows with invalid content hashes
  or missing content objects return typed `UNVERIFIABLE`.
- Projection-policy control: raw source row metadata cannot publish ids, source
  names, refs, or URLs. Public human fields require an operator-authored policy
  and safe-value validation.
