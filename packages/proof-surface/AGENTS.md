# AGENTS.md -- Proof Surface

## Project Boundary

Proof Surface is a stdlib-first contract and validator library for evidence
packets, receipts, gates, ledgers, delegation chains, and witness records. It
validates structure and closed verdicts; it does not grant authority or execute
actions.

## Public Delivery Rules

- Keep `README.md`, `USAGE.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `AUTHORS.md`,
  `LICENSE`, `.github/FUNDING.yml`, `.github/workflows/ci.yml`, and the brand
  asset present.
- Public claims must be backed by schemas, conformance vectors, tests, or
  examples.
- Do not commit private payloads, credentials, local receipts, generated build
  output, or sensitive corpus material.
- Use ASCII punctuation in forward-facing docs unless a schema or fixture
  requires exact bytes.

## Developer Verification

Run the local package gate before publishing:

```sh
python -m pip install -e ".[test]"
python scripts/check_public_surface.py
python -m pytest
```

For contract changes, update the schema, validator, conformance vectors, and
tests together.
