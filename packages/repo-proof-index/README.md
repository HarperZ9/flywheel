<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/HarperZ9/repo-proof-index/main/docs/art/hero-dark.svg">
  <img src="https://raw.githubusercontent.com/HarperZ9/repo-proof-index/main/docs/art/hero-light.svg" alt="repo-proof-index: Index proof packets, receipts, and contracts into reviewer summaries. A chain of small linked squares, each holding a few ruled lines, winds inward to a bright core." width="100%">
</picture>

# repo-proof-index

Index proof packets, receipts, and contracts into reviewer summaries.

```
python -m pip install -e ".[test]"
```

[![version: 0.2.0](https://img.shields.io/badge/version-0.2.0-e6e1d6?style=flat-square&labelColor=1a1712)](https://pypi.org/project/repo-proof-index/)
[![CI](https://github.com/HarperZ9/repo-proof-index/actions/workflows/ci.yml/badge.svg)](https://github.com/HarperZ9/repo-proof-index/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-MIT-e6e1d6?style=flat-square&labelColor=1a1712)](https://github.com/HarperZ9/repo-proof-index/blob/main/LICENSE)
![python 3.11+](https://img.shields.io/badge/python-3.11%2B-e6e1d6?style=flat-square&labelColor=1a1712)

Repo Proof Index scans proof artifacts and returns the compact view a maintainer
needs before release review: kind, surface, status, evidence summary, and source
path. It indexes evidence; it does not decide whether the evidence is enough.

## See it work, step by step

The [animated explainer](https://harperz9.github.io/repo-explainers/repo-proof-index.html)
walks through the four bundled proof artifacts indexed into one table, the difference between a declared and a verified status, the summary's action items, packet validation, and the strict JSON reader's rejections. Every value on it is output from this repository. Its
source is [docs/explainer/index.html](docs/explainer/index.html).

## Walkthrough

Install it, run it once, then use the main feature. Each command below is real, and so is its output.

1. **Install.** Install from PyPI and clone for the examples. Python 3.10 or newer.

   ```text
   $ python -m pip install repo-proof-index
   $ git clone https://github.com/HarperZ9/repo-proof-index && cd repo-proof-index
   ```

2. **First run: index one record.** Read one proof record and report its kind and verification state.

   ```text
   $ repo-proof-index examples/contracts/sample-witness-receipt.json --json
   "kind": "witness-receipt"
   "status": "MATCH"
   "producer_status": "MATCH"
   "verification_state": "not_assessed"
   ```

3. **Summarize a folder.** Count records by verification state.

   ```text
   $ repo-proof-index examples/contracts/*.json --summary
   total: 4
   kinds: backend-capability=1, product-use-case=1, proof-surface-packet=1, witness-receipt=1
   statuses: MATCH=1, backend-matrix=1, needs-polish=1, release-candidate=1
   verification_states: not_assessed=3, not_verified=1
   evidence_gaps: 0
   action_items:
   - proof-surface-public-release-demo: resolve needs-polish
   ```

4. **A malformed record is rejected.** A file with a duplicate key is refused.

   ```text
   $ repo-proof-index dup.json
   error: duplicate JSON key: status
   ```

## Why it matters

As a repo gains receipts and proof packets, reviewers need a fast way to find
what each artifact claims and where the evidence lives. This tool makes that
proof layer navigable.

## Try it

```bash
python -m pip install -e ".[test]"
repo-proof-index examples/contracts/*.json --summary
python -m pytest
```

## What to test first

- Index the bundled example contracts.
- Run `repo-proof-index --root .` in a repo with proof artifacts.
- Use `--validate` on a proof-surface packet.

## Current status

Python package and CLI with tolerant JSON parsing and proof-surface integration.
It produces review indexes and summaries, not compliance findings.

## Existing technical notes

> Reviewer-ready index over proof packets and receipts -- indexes the evidence; does not decide if it is enough.

[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![python](https://img.shields.io/badge/python-3.11%2B-blue.svg)
![version](https://img.shields.io/badge/version-0.2.0-informational.svg)
[![CI](https://github.com/HarperZ9/repo-proof-index/actions/workflows/ci.yml/badge.svg)](https://github.com/HarperZ9/repo-proof-index/actions/workflows/ci.yml)
[![part of: AI-accountability toolkit](https://img.shields.io/badge/part_of-AI--accountability_toolkit-7a5cff.svg)](https://harperz9.github.io)

`repo-proof-index` turns scattered proof artifacts into a reviewer-readable
index. Feed it JSON proof contracts, proof-surface packets, witness receipts,
and backend descriptors; it returns the compact view a maintainer needs before
a release-readiness or diligence handoff.

The parser is intentionally schema-tolerant. Unknown contract shapes still get
best-effort identifiers, status, surface, evidence, and source path fields.
The JSON reader is strict before that shape-tolerant layer runs: duplicate keys,
non-finite values such as `NaN`, `Infinity`, and overflowing floats, files over
1,048,576 bytes, and JSON nesting deeper than 200 levels are rejected for both
indexing and proof-surface validation.

Use it when a repo or workspace has proof artifacts but no quick way to see
what they claim, what surface they describe, what status they report, whether
Repo Proof Index verified that status, and where the evidence lives.

![Eight stages of indexing one proof artifact: paths, read, match, row, evidence, relative, table, and exit. Paths are either the files you name on the command line, sorted, or every JSON file in a directory that is scanned when you name none. Each file must hold one JSON object; a list or a string raises before any shape is tried. Known shapes are recognized in a fixed order and the first match wins, with a fallback that catches everything else, so an unrecognized shape still gets a row. Every row carries contract, kind, surface, status, evidence, path, producer status, and verification state. The evidence line prefers checks that passed, falling back to the first claim, then to a free note, then to a line saying there is no summary. Paths are shown relative to the base you chose, and stay absolute when they sit outside it. The table prints four fields, clipped to fixed widths with a trailing ellipsis, and the contract identifier, path, producer status, and verification state reach JSON output. The exit code is zero once the rows print. Three outcomes: indexed, refused, and not found.](docs/art/index-lane.svg)

## Install

```bash
python -m pip install repo-proof-index
```

For local development:

```bash
python -m pip install -e ".[test]"
python -m pytest
```

## Usage

See [USAGE.md](USAGE.md) for a full usage guide with worked examples and
expected output. A quick tour follows.

Index explicit JSON files:

```bash
repo-proof-index contracts/*.json
repo-proof-index contracts/*.json --json
repo-proof-index contracts/*.json --summary
repo-proof-index contracts/*.json --summary --json
repo-proof-index --validate examples/contracts/proof-surface-packet.json
repo-proof-index --validate examples/contracts/proof-surface-packet.json --json
```

Index the common workspace location:

```bash
repo-proof-index --root .
```

Use a custom contracts directory:

```bash
repo-proof-index --contracts-dir project-docs/contracts
```

Run the bundled quick demo:

```bash
repo-proof-index examples/contracts/*.json
```

Malformed input example:

```bash
repo-proof-index examples/malformed/not-object.json
```

Expected behavior: the command prints an `error:` line and exits with status
`1` instead of producing a proof row.

## What it indexes

Known shapes:

- proof-surface interop packets with `proof_surface_version` and `packet_id`
- proof-surface research-claim packets with
  `version: research-claim-proof-packet/v0`
- ORCA organ exchange artifacts from `orca.module.organ_exchange.bundle`
- proof-surface organ receipt bundles with `organ_bundle_version` and `bundle_id`
- product use-case manifests with `manifest_id` and `product`
- backend capability descriptors with `descriptor_id` and `backends`
- witness receipts with `receipt_id` and `verdict`
- generic JSON contracts with common fields such as `id`, `report_id`,
  `manifest_id`, `descriptor_id`, `status`, `maturity`, `verdict`, `claims`,
  `verification`, and `notes`

Default discovery path when explicit files are omitted:

```text
project-docs/roadmaps/contracts/*.json
```

## Output fields

| Field | Meaning |
| --- | --- |
| `kind` | Best-effort contract type. |
| `surface` | Product, language, witness implementation, root, or contract name. |
| `status` | Backward-compatible reported status, maturity, or verdict. |
| `evidence` | Short evidence summary from verification, claims, notes, or backend counts. |
| `path` | Source JSON path in JSON mode. |
| `producer_status` | The status reported by the artifact producer. For legacy shapes this mirrors `status`. |
| `verification_state` | What Repo Proof Index verified. `not_verified` means the row reports producer data and did not execute a verifier. |

## Verification boundary

Repo Proof Index never executes packet-supplied verifier commands and never
treats a claimed command, source hash, or passing check as semantic proof. The
`status` field stays backward-compatible and producer-reported. The
`verification_state` field records the indexer's own role.

For proof-surface v0.1 packets and research-claim packets,
`verification_state` is `not_verified`: the indexer can validate shape, read
reported verdicts, and summarize pointers, but it has not re-run Crucible,
opened referenced evidence, or decided claim truth. A packet that says
`ready`, `MATCH`, `pass`, or `verified` while remaining `not_verified` is placed
on the summary action list as a producer-declared green row that needs an
external verifier. A regression would be a self-declared ready/MATCH packet
disappearing from `action_items` without an independently recorded verification
state.

## Release summary mode

Use `--summary` when a reviewer needs the portfolio-level signal instead of
row-by-row detail. The summary reports total artifacts, kind counts, status
counts, evidence-gap count, and the first actionable rows that need stronger
proof.

Running it over the bundled example contracts:

```bash
repo-proof-index examples/contracts/*.json --summary
```

```text
total: 4
kinds: backend-capability=1, product-use-case=1, proof-surface-packet=1, witness-receipt=1
statuses: MATCH=1, backend-matrix=1, needs-polish=1, release-candidate=1
verification_states: not_assessed=3, not_verified=1
evidence_gaps: 0
action_items:
- proof-surface-public-release-demo: resolve needs-polish (examples/contracts/proof-surface-packet.json)
```

![Twelve shapes a proof file can arrive in, one to a row, with what the index reports and why it lands there. A manifest with a product is read as a product use case, taking maturity as the status. A descriptor with backends is read as a backend capability, carrying a constant status and an evidence line that counts backends by status. A receipt with a verdict is read as a witness receipt, taking the verdict as the status and naming the witness implementation as the surface. A packet version and identifier is read as a proof-surface packet, whose evidence counts claims, checks and action items while marking the producer report not verified. A research-claim packet is read as a research-claim packet, taking its reported overall verdict as status without running a verifier. An exact module identifier with a summary object is read as an organ exchange. A bundle version with entries is read as an organ receipt bundle, whose status is the worst entry status in a fixed order of block, warn, needs-human and unverified. Anything matching none of the known shapes falls back to a plain contract, with identifier, surface and status each taken from the first candidate field present. Recognition stops at the first match, so a file carrying two shapes is read as the earlier one and the later fields are never seen. A file with no identifier borrows the stem of its own path. The accented row is the evidence gap: the test is a string test, so a note reading no regressions found is counted as a missing summary. A root that is not a JSON object is refused before any shape is tried, and the command exits one.](docs/art/shape-table.svg)

## Example table output

```text
kind                   | surface                | status             | evidence
---------------------- | ---------------------- | ------------------ | ------------------------------------------------------------------------
product-use-case       | sample-tool            | release-candidate  | pass: example tests passed
witness-receipt        | sample-witness         | MATCH              | sample receipt available
backend-capability     | rust                   | backend-matrix     | pass=1, planned=1
```

## Example JSON output

```json
[
  {
    "contract": "product-usecase-build-ui",
    "kind": "product-use-case",
    "surface": "build-ui",
    "status": "private-gated",
    "evidence": "pass: 17 tests passed",
    "path": "contracts/build-ui.json",
    "producer_status": "private-gated",
    "verification_state": "not_assessed"
  }
]
```

## What it does not do

- It does not validate a JSON Schema.
- It does not certify that evidence is sufficient.
- It does not read private payloads referenced by a contract.
- It does not execute packet-supplied verifier commands.
- It does not decide whether a claim is true.
- It does not replace tests, audits, or release review.

![Eight stages of a review summary: rows, kinds, statuses, verification states, gaps, green-report guard, reason, eight, and summary. The rows are every artifact already indexed, in path order. Kinds, statuses, and verification states are counted and sorted by name. An evidence gap is decided by a string test on the evidence line: empty, the word unknown, or any text beginning with the word no. Rows also land on the action list when their status is blocked, draft, drift, fail, planned, unknown, unverifiable, unverified, or when a producer-declared green status remains not verified. Each item names a reason, either to add evidence, resolve the status it carries, or verify a producer-declared green row, alongside the path that holds it. The list stops at eight items and does not say how many were left out. The summary carries six fields and prints as text or as JSON. Three outcomes: clear, action, and truncated.](docs/art/review-lane.svg)

## Release-readiness use

`repo-proof-index` is the evidence assembly point in a proof-surface pipeline:

```text
contracts and receipts -> proof index -> report -> reviewer handoff
```

Its job is to make proof artifacts visible enough for a maintainer, reviewer,
client, or employer to see what exists and what still needs a stronger gate.

## Proof-surface interop packet

The `schemas/proof-surface-packet.schema.json` file defines a small shared
packet for release-readiness evidence. It is intentionally neutral: independent
tools can publish claims, checks, and action items without asking any one tool to
become the authority.

```text
surface claim -> evidence pointer -> check result -> action item
```

`repo-proof-index` recognizes these packets as `proof-surface-packet` rows,
sets `verification_state` to `not_verified`, and summarizes their claim, check,
and action counts. See
`examples/contracts/proof-surface-packet.json` and
`docs/PROOF-SURFACE-INTEROP.md`.
The current version and known producer/consumer registry lives at
`docs/PROOF-SURFACE-REGISTRY.json`.

Validate packet shape locally:

```bash
repo-proof-index --validate examples/contracts/proof-surface-packet.json
```

The validator is intentionally strict for the v0.1 contract: unexpected root,
claim, or check fields are reported as errors instead of silently drifting the
interop shape.

Export the portable contract bundle:

```bash
python scripts/export_proof_surface_contract.py --out dist/proof-surface-contract-v0.1
```

## Research harness

The draft research harness scores proof-surface cases across schema validity,
evidence coverage, actionability, non-authority language, and witness/provenance
presence.

```bash
python scripts/score_proof_surface_research.py
```

See `docs/PROOF-SURFACE-RESEARCH-HARNESS-v0.1.md`.
Case contribution guidance lives at
`docs/PROOF-SURFACE-CASE-CONTRIBUTING.md`.

---
**Zain Dana Harper** -- small tools with explicit edges.
[Portfolio](https://harperz9.github.io) · [HarperZ9](https://github.com/HarperZ9)
<sub>Built with Claude Code; reviewed, tested, and owned by me.</sub>

## For developers

Keep the public README, package metadata, and examples aligned with current behavior. Before opening a PR or pushing a release, run the local package verification path.

```bash
python -m pip install -e ".[test]"
python -m pytest
```

---

Built by **[Zain Dana Harper](https://harperz9.github.io)** in Seattle: evidence-first tools that leave a re-checkable artifact behind. The full workbench is at [Project Telos](https://harperz9.github.io).
