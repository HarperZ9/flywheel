# AGENTS.md

This repository is a public-safe Python package for building compact,
receipt-friendly context bundles from local text files.

Rules:
- Do not commit `.env`, private transcripts, customer data, or local artifact
  bundles.
- Keep generated examples relative-path based; public docs must not expose
  absolute workstation paths.
- Keep README, USAGE, package metadata, CI, and changelog aligned with current
  CLI behavior.
- Run `python -m pytest` before release.
- Treat redaction as a review aid, not a security boundary.
