# Flywheel local flagship package

The flagship package is the local harness distribution for the Codex/Flywheel engine.
It packages the executable harness, local model endpoint contracts, tool integration receipts, release gates, and public-ready documentation scaffolds without bundling secrets, model weights, caches, or private corpora.

## What ships

- Executable harness wrappers for local command execution.
- Local 14B and 32B endpoint profiles.
- Tool integration, readiness, hardening, and operator-guide receipts.
- Runtime activation and Codex MCP launch contracts.
- Architecture, enterprise-readiness, package-doctor, and Hugging Face staging receipts.
- Model release docs, external documentation sync notes, demo scripts, walkthroughs, and package art.

## What does not ship

- Model weights.
- `.env` files, tokens, credentials, private keys, caches, or benchmark raw outputs.
- User-private corpora or authenticated browser/session state.

## Release posture

The package is shippable as a harness artifact when the package doctor is `SHIP_READY`.
The models are not publishable until release readiness, checksums, provenance, model cards, endpoint gates, benchmark evidence, and explicit operator upload approval are all present.
