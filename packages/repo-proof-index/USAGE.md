# Usage Guide

`repo-proof-index` indexes scattered JSON proof artifacts (proof contracts,
proof-surface packets, witness receipts, organ bundles, backend descriptors)
into a reviewer-readable table, JSON rows, or a release-readiness summary. It
indexes the evidence; it does not decide whether the evidence is enough. A
reported status from a producer is kept separate from Repo Proof Index's own
verification state.

This guide covers the real command-line interface and the importable Python
API. Every command, flag, and function shown here exists in the current
source. Output blocks were produced by running the commands against the
bundled `examples/contracts/` files; they are shown verbatim. Where noted as
illustrative, the values are representative rather than captured.

## Install

```bash
python -m pip install repo-proof-index
```

For local development (editable install with test extras):

```bash
python -m pip install -e ".[test]"
python -m pytest
```

The package installs a console script named `repo-proof-index`. You can also
run it as a module with `python -m repo_proof_index`.

## Command-line interface

```
repo-proof-index [paths ...] [--root ROOT] [--contracts-dir DIR]
                 [--json] [--summary] [--validate]
```

| Argument / flag | Meaning |
| --- | --- |
| `paths` | Zero or more contract JSON files to index. |
| `--root ROOT` | Workspace root used when `paths` are omitted. Defaults to `.`. |
| `--contracts-dir DIR` | Directory to scan when `paths` are omitted. |
| `--json` | Print JSON rows instead of a table. |
| `--summary` | Print a release-readiness summary instead of per-row detail. |
| `--validate` | Validate proof-surface packet JSON files instead of indexing. |

When no explicit paths are given and no `--contracts-dir` is set, discovery
falls back to `<root>/project-docs/roadmaps/contracts/*.json`.

Exit codes: `0` on success; `1` when a contract cannot be read/parsed, when
`--validate` finds an invalid packet, or when `--validate` is given no paths.
Parsing is strict for both indexing and `--validate`: duplicate JSON keys and
non-finite values such as `NaN`, `Infinity`, and overflowing floats are rejected
before any contract or packet fields are interpreted. Files over 1,048,576
bytes and JSON nesting deeper than 200 levels are rejected with explicit
messages.

## Worked examples

### 1. Index explicit files as a table

```bash
repo-proof-index examples/contracts/sample-product-usecase.json \
                 examples/contracts/sample-witness-receipt.json \
                 examples/contracts/sample-backend-capability.json
```

Expected output (rows are sorted by source path):

```text
kind                   | surface                | status             | evidence                                                                
---------------------- | ---------------------- | ------------------ | ------------------------------------------------------------------------
backend-capability     | rust                   | backend-matrix     | pass=1, planned=1                                                       
product-use-case       | sample-tool            | release-candidate  | pass: example tests passed                                              
witness-receipt        | sample-witness         | MATCH              | sample receipt available
```

### 2. Emit JSON rows

```bash
repo-proof-index examples/contracts/sample-product-usecase.json --json
```

Expected output:

```json
[
  {
    "contract": "sample-product-usecase",
    "kind": "product-use-case",
    "surface": "sample-tool",
    "status": "release-candidate",
    "evidence": "pass: example tests passed",
    "path": "examples/contracts/sample-product-usecase.json",
    "producer_status": "release-candidate",
    "verification_state": "not_assessed"
  }
]
```

### 3. Release-readiness summary

```bash
repo-proof-index examples/contracts/*.json --summary
```

Expected output:

```text
total: 4
kinds: backend-capability=1, product-use-case=1, proof-surface-packet=1, witness-receipt=1
statuses: MATCH=1, backend-matrix=1, needs-polish=1, release-candidate=1
verification_states: not_assessed=3, not_verified=1
evidence_gaps: 0
action_items:
- proof-surface-public-release-demo: resolve needs-polish (examples/contracts/proof-surface-packet.json)
```

Add `--json` (`--summary --json`) to get the same summary as a JSON object
with `total`, `kinds`, `statuses`, `verification_states`, `evidence_gaps`, and
`action_items` keys.

### Verification-state boundary

`status` is the artifact producer's reported state, preserved for backward
compatibility. `producer_status` makes that source explicit.
`verification_state` describes what Repo Proof Index did. For proof-surface
v0.1 packets and research-claim packets it is `not_verified`, because the
indexer validates shape and summarizes reported fields but does not execute
packet-supplied verifier commands, open referenced evidence, or treat a claimed
hash as semantic truth.

The summary action list treats a producer-declared green status such as
`ready`, `MATCH`, `pass`, or `verified` as actionable while its
`verification_state` is `not_verified`. A self-declared green packet must stay
visible as a verification task until another tool records an actual verifier
result.

### 4. Validate a proof-surface packet

```bash
repo-proof-index --validate examples/contracts/proof-surface-packet.json
```

Expected output (exit code `0`):

```text
examples/contracts/proof-surface-packet.json: valid
```

A malformed contract exits non-zero with an `error:` line:

```bash
repo-proof-index examples/malformed/not-object.json
```

Expected output (exit code `1`):

```text
error: .../examples/malformed/not-object.json did not contain a JSON object
```

### Scan a directory instead of explicit files

```bash
# Default discovery path: <root>/project-docs/roadmaps/contracts/*.json
repo-proof-index --root .

# Or point at any directory of *.json contracts
repo-proof-index --contracts-dir examples/contracts
```

## Importable Python API

The package exposes a small, schema-tolerant API. The package root
re-exports the row type and core indexing helpers:

```python
from repo_proof_index import ProofRow, load_rows, format_table, summarize_contract
```

Summary helpers live in `repo_proof_index.indexer`:

```python
from repo_proof_index.indexer import summarize_rows, format_summary, ProofSummary
```

Worked example:

```python
from pathlib import Path
from repo_proof_index import load_rows, format_table
from repo_proof_index.indexer import summarize_rows, format_summary

# Index a list of explicit contract files into ProofRow objects.
rows = load_rows(
    [Path("examples/contracts/sample-product-usecase.json")],
    root=Path("."),
)
print(rows[0])
# ProofRow(contract='sample-product-usecase', kind='product-use-case',
#          surface='sample-tool', status='release-candidate',
#          evidence='pass: example tests passed',
#          path='examples/contracts/sample-product-usecase.json',
#          producer_status='release-candidate',
#          verification_state='not_assessed')

# Render a table or a release-readiness summary.
print(format_table(rows))
print(format_summary(summarize_rows(rows)))
```

Key functions and types:

| Name | Signature (abbreviated) | Returns |
| --- | --- | --- |
| `load_rows` | `load_rows(paths=(), *, root=Path("."), contracts_dir=None)` | `list[ProofRow]` |
| `summarize_contract` | `summarize_contract(path, base=None)` | `ProofRow` |
| `format_table` | `format_table(rows)` | `str` |
| `summarize_rows` | `summarize_rows(rows, action_limit=8)` | `ProofSummary` |
| `format_summary` | `format_summary(summary)` | `str` |
| `ProofRow` | frozen dataclass | fields: `contract, kind, surface, status, evidence, path, producer_status, verification_state` |
| `ProofSummary` | frozen dataclass | fields: `total, kinds, statuses, verification_states, evidence_gaps, action_items` |

`load_rows` raises `FileNotFoundError` when a fallback contracts directory does
not exist, and `summarize_contract` raises `ValueError` when a file does not
contain a top-level JSON object.

## See also

- [README.md](README.md) -- overview, indexed shapes, and output fields.
- `examples/demo.py` -- runnable end-to-end demo of the API and CLI.
- `docs/PROOF-SURFACE-INTEROP.md` -- proof-surface packet interop notes.
