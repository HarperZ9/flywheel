# secret-redact-io

This repository is a public, self-contained utility. Keep the package focused on
general IO guardrails, redaction, and receipts.

- Do not add credentials, secrets, or deployment-specific configuration.
- Do not commit `.env` files.
- Runtime dependencies should stay stdlib-only unless a dependency removes
  substantial complexity.
- Public release checks must include `python -m pytest`,
  `python scripts/check_public_surface.py`, and `python -m build`.
