# Changelog

## 0.2.0 (unreleased)

- From v0.2.0, code is licensed FSL-1.1-MIT. Earlier releases remain under MIT.
- `LICENSE` is the FSL-1.1-MIT text from fsl.software, with licensor Zain Dana Harper and copyright 2026.
- Release 0.1.0, published on PyPI, stays MIT.
- `LICENSE.md` was a second copy of the MIT text and is removed; `LICENSE` is the one licence file.
- `pyproject.toml` declares `license = "FSL-1.1-MIT"` (PEP 639, hatchling 1.27 or later) and drops the MIT classifier; PyPI has no FSL classifier. Version 0.2.0 in `pyproject.toml` and `__version__`.
- No code behaviour changed.

## 2026-06-29 - Forward Delivery Contract

- Added `AGENTS.md`, `USAGE.md`, `CHANGELOG.md`, and
  `project-docs/specs/SPEC-coherence-membrane-forward-delivery.md`.
- Updated CI to current checkout/setup-python/setup-node action majors and added
  Python conformance, JavaScript conformance, and selftest commands.
- Added package repository, issues, and homepage metadata.
- Normalized forward-facing punctuation for public-surface scanner
  compatibility.
- Kept perception organs, schemas, conformance vectors, drift lattice behavior,
  receipts, native capture, and parity logic unchanged.

## Current Status

- Runtime: Python 3.10+ with stdlib-first perception and conformance paths.
- Surfaces: Python package, CLI, schemas, conformance vectors, JavaScript parity
  implementation, native capture, and usage guide.
- Verification: pytest suite, Python conformance, JavaScript conformance, and
  selftest.
