# Flywheel 2.1.0

Released 2026-11-27.

## Highlights

- Graduated ten pure-stdlib MIT verification harnesses (`#588..#596`) covering BuildOS zero-C 5-ISA attestation, post-quantum enclave quote verification, QUIC-Lite capability firewall attestation, BFT consensus, Pedersen and Schnorr zero-knowledge proofs, 4-pillar MIR assurance, GPU shader verification suites, and SBOM integrity.
- Removed personal email metadata from `pyproject.toml` for zero-PII package publishing (`#591`).
- Aligned engine (`pyproject.toml`), desktop installer (`desktop/pubspec.yaml` `2.1.0+42`), and About surface (`desktop/lib/version.dart`) on `2.1.0`.

## Limits

- Pure-stdlib verification harnesses re-check declared digests, schemas, and planted controls offline; they do not execute remote GPU drivers or hosted model endpoints.
