# Flywheel 2.1.0

Released 2026-11-27.

## Highlights

- Graduated ten pure-stdlib MIT verification harnesses (`#588..#596`) covering BuildOS zero-C 5-ISA attestation, post-quantum enclave quote verification, QUIC-Lite capability firewall attestation, BFT consensus, Pedersen and Schnorr zero-knowledge proofs, 4-pillar MIR assurance, GPU shader verification suites, and SBOM integrity.
- Removed personal email metadata from `pyproject.toml` for zero-PII package publishing (`#591`).
- Aligned engine (`pyproject.toml`), desktop installer (`desktop/pubspec.yaml` `2.1.0+42`), and About surface (`desktop/lib/version.dart`) on `2.1.0`.

## Integrity and Licensing

- Shipped rule-pack SHA-256 digest: `a76b7e8995c91861e92ce2198cd62d722deede9fb8307463c68b8aa5d5cdf8c4`.
- Licensing terms for the engine, desktop app, and bundled harnesses live in [docs/LICENSING.md](docs/LICENSING.md).

## Limits

- Pure-stdlib verification harnesses re-check declared digests, schemas, and planted controls offline; they do not execute remote GPU drivers or hosted model endpoints.
