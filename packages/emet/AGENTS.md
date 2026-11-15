# AGENTS.md - EMET

## Scope

This file applies to the EMET repository. Root workspace instructions still
apply; this file narrows local work around EMET's release-candidate surface and
integrity-verifier invariants.

## Product Boundary

EMET is a small, advisory integrity verifier. It checks raw bytes and emits
closed verdicts; it is not an authorization system, policy engine, deployment
gate, or enforcement tool.

Treat these as releasable product surfaces:

- `membrane.py`, `organs.py`, `monitor.py`, `corpus.py`, `verdict.py`, and
  `report.py` - Python reference implementation and related local verifier tools.
- `impl/rust/`, `impl/js/`, and `impl/go/` - second, third, and fourth
  implementations for cross-language re-derivation.
- `conformance/` - language-agnostic vectors and marker corpus.
- `SPEC.md`, `RATIONALE.md`, `THREAT-MODEL.md`, `SECURITY.md`,
  `CONTRIBUTING.md`, and `COVERAGE.json` - public specification and assurance
  surface.
- `adapters/` - optional attest/provenance adapters that must preserve EMET's
  advisory-only posture.

Treat these as local-only runtime state:

- `anchors.json`, `*_log.jsonl`, `*.refused`, `perception*.json`, `*.tmp`, and
  `.warden-safe-cache/`.
- `.env`, `.env.*`, secrets, local credentials, private corpora, and generated
  operator records.

## Invariants

- Verdicts stay inside the closed lattice: `MATCH`, `DRIFT`, `UNVERIFIABLE`.
- EMET reports facts only; it must not emit `TRUSTED`, `APPROVED`, `SAFE`, or
  any value that grants authority or permission.
- EMET reads target artifacts as raw bytes and does not normalize input before
  hashing.
- EMET does not edit, sign, enforce, deploy, or otherwise actuate on audited
  targets.
- Spec changes and conformance-vector changes move together when behavior
  changes.
- Marker-corpus additions are data changes and need a rationale plus a vector
  or focused regression.

## Release-Candidate Shape

A release-candidate slice should be independently reproducible from the public
surface:

- README and SPEC state the current version/status honestly.
- `conformance/vectors.json` covers every normative command behavior that moved.
- Python, Rust, JavaScript, and Go implementations all pass the same vectors, or
  a gap is documented explicitly.
- Security reporting instructions remain present.
- Runtime state and private material are excluded from commits.

## Verification

Run the checks that match the change:

```powershell
python -m pytest -q
python conformance/run.py membrane.py
python conformance/run.py impl/js/emet.js
rustc -O impl/rust/emet.rs -o "$env:TEMP\emet-rust.exe"
python conformance/run.py "$env:TEMP\emet-rust.exe"
go build -o "$env:TEMP\emet-go.exe" impl/go/emet.go
python conformance/run.py "$env:TEMP\emet-go.exe"
python membrane.py selftest
git diff --check
```

Before committing or pushing, scan changed files for credential-shaped content
and confirm `.env` remains ignored.
