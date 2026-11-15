# AGENTS.md - Repo Proof Index

## Scope

This repository is a public Python package and CLI for indexing proof contracts,
receipts, backend descriptors, and proof-surface interop packets.

Use this file for work in this repo. Hygiene rules are stated here so they travel
with the repo when it is cloned on its own: never commit secrets, `.env` files,
tokens, or private payloads or operational material to this public repository.

## Product Boundary

`repo-proof-index` may include:

- schema-tolerant JSON contract indexing in `src/repo_proof_index/`,
- strict proof-surface packet validation for the v0.1 interop contract,
- public examples under `examples/contracts/`,
- conformance fixtures under `conformance/proof-surface/v0.1/`,
- tests, schema docs, README material, release notes, and packaging metadata.

It must not include:

- private contract payloads, customer data, target data, or proprietary corpus
  material,
- credentials, tokens, `.env` values, browser profiles, or local vault data,
- claims that the tool certifies evidence sufficiency or claim truth,
- live fetching of private evidence references unless added as a separately
  tested public feature.

The tool indexes and validates proof surfaces. It does not replace the tests,
audits, or reviews those surfaces point to.

## Repo Map

- `src/repo_proof_index/indexer.py` - JSON artifact summarization and table,
  JSON, and summary output helpers.
- `src/repo_proof_index/cli.py` - command-line interface and exit-code
  behavior.
- `src/repo_proof_index/packet.py` - proof-surface v0.1 packet validator.
- `schemas/proof-surface-packet.schema.json` - public packet schema reference.
- `conformance/proof-surface/v0.1/` - valid and invalid packet fixtures.
- `scripts/check_proof_surface_conformance.py` - fixture conformance runner.
- `tests/` - regression tests for indexing, malformed input, and validation.

## Development

Install locally:

```bash
python -m pip install -e ".[test]"
```

Run the test slice:

```bash
python -m pytest -q
```

Run CLI and conformance smoke checks:

```powershell
$env:PYTHONPATH = "src"
$files = Get-ChildItem examples/contracts/*.json | ForEach-Object { $_.FullName }
python -m repo_proof_index @files --summary
python -m repo_proof_index --validate examples/contracts/proof-surface-packet.json
python scripts/check_proof_surface_conformance.py
```

Run metadata checks before committing:

```bash
python -m json.tool schemas/proof-surface-packet.schema.json
git diff --check
```

Before publishing, scan changed files for credential-like values. Do not commit
`.env` files or generated caches.

## Change Rules

- Keep generic indexing schema-tolerant, but keep proof-surface v0.1 validation
  strict.
- Update tests and conformance fixtures when packet shape, status enums, or
  validation diagnostics change.
- Keep examples and fixtures public-safe, compact, and reproducible.
- Keep validation claims structural: this package indexes and validates shape;
  it does not certify truth or sufficiency of the referenced evidence.
