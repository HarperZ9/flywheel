# AGENTS.md -- Proof Surface Report

## Project Boundary

Proof Surface Report renders proof-surface packets and compatible receipts into
reviewer-facing Markdown. It validates input shape and rejects authority-shaped
language; it does not approve releases, certify compliance, or decide claim
truth.

## Public Delivery Rules

- Keep `README.md`, `USAGE.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `AUTHORS.md`,
  `LICENSE`, `.github/FUNDING.yml`, `.github/workflows/ci.yml`, examples, and
  brand assets present.
- Examples must stay synthetic and public-safe.
- Do not commit private reports, client data, credentials, `.env` files, or
  generated release artifacts.
- Public claims must remain evidence-handoff claims, not certification or
  approval claims.

## Developer Verification

Run the local package gate before publishing:

```sh
python -m pip install -e ".[test]"
python -m pytest
```

For wording changes, include a negative test when new authority-shaped phrasing
must be rejected.
