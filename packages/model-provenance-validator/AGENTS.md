# AGENTS.md - Model Provenance Validator

## Scope

This repository is a public Python package and CLI for validating compact JSON
provenance envelopes around model/reference claims.

Use this file for work in this repo. Hygiene rules are stated here so they travel
with the repo when it is cloned on its own: never commit secrets, `.env` files,
tokens, or private corpus or operational material to this public repository.

## Product Boundary

`model-provenance-validator` may include:

- schema and envelope validation in `src/model_provenance_validator/`,
- CLI output for per-file, JSON, summary, and proof-packet modes,
- public examples under `examples/envelopes/`,
- tests, fixtures, README material, and packaging metadata.

It must not include:

- private model transcripts, customer data, target data, or proprietary corpus
  contents,
- credentials, tokens, `.env` values, browser profiles, or local vault data,
- claims that the tool certifies truth, safety, or legal provenance,
- network fetching or source-authentication behavior unless it is added as a
  separately tested public feature.

The tool validates envelope shape and batch reporting. It does not decide
whether the underlying claim is true.

## Repo Map

- `src/model_provenance_validator/validator.py` - schema and envelope loading
  plus lightweight validation.
- `src/model_provenance_validator/cli.py` - command-line interface and output
  modes.
- `src/model_provenance_validator/packet.py` - proof-surface packet validation.
- `src/model_provenance_validator/schema.json` - bundled envelope schema.
- `tests/test_validator.py` - regression tests for validator and module CLI.
- `examples/envelopes/` - public-safe provenance examples.

## Development

Install locally:

```bash
python -m pip install -e ".[test]"
```

Run the test slice:

```bash
python -m pytest -q
```

Run CLI smoke checks:

```powershell
$env:PYTHONPATH = "src"
python -m model_provenance_validator tests/fixtures/valid.json --json
python -m model_provenance_validator tests/fixtures/valid.json --summary
python -m model_provenance_validator tests/fixtures/valid.json --proof-packet
```

Run metadata checks before committing:

```bash
python -m json.tool src/model_provenance_validator/schema.json
python -m json.tool examples/envelopes/release.provenance.json
git diff --check
```

Before publishing, scan changed files for credential-like values. Do not commit
`.env` files or generated caches.

## Change Rules

- Keep runtime dependencies minimal.
- Keep validation behavior deterministic and covered by fixtures.
- Update tests when schema fields, CLI flags, exit codes, or proof-packet shape
  change.
- Keep examples public-safe and source-checkable from the repo.
- Be explicit in docs that validation is structural, not certification.
