# AGENTS.md -- Coherence Membrane

## Project Boundary

Coherence Membrane is an inert perception layer for agent workflows. It observes
owned or authorized local artifacts, emits re-derivable observations and
receipts, and never grants authority or performs consequential actions.

## Public Delivery Rules

- Keep `README.md`, `USAGE.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `AUTHORS.md`,
  `LICENSE`, `.github/FUNDING.yml`, `.github/workflows/ci.yml`, schemas,
  conformance vectors, examples, and brand assets present.
- Public claims must be backed by tests, conformance vectors, schemas, or
  reproducible commands.
- Do not commit captures from private screens, private media, credentials,
  `.env` files, local baselines, generated receipts, or private corpus material.
- Keep observation language factual and advisory: no `TRUSTED`, `APPROVED`, or
  authority-granting statuses.

## Developer Verification

Run the local package gate before publishing:

```sh
python -m pip install -e ".[test]"
python -m pytest
python conformance/run.py
node impl/js/run.js
python -m coherence_membrane selftest
```

For wire-shape changes, update schemas, conformance vectors, Python behavior,
JavaScript parity, and tests together.
