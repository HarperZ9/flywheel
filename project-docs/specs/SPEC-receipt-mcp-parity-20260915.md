# Receipt MCP Parity Spec

Date: 2026-09-15

## Problem

Flywheel already exposes receipt inclusion proof over the configured gateway
HTTP policy at `GET /api/receipts/proof?leaf=<sha256>`. Provider-native agent
tools can also verify a receipt leaf against the receipts ledger. The local MCP
server does not yet expose the same bounded receipt proof operation, so an MCP
client cannot independently re-derive whether a receipt hash is a member of the
ordered receipts Merkle log.

The user goal is independent, re-derivable evaluation across API and MCP. The
MCP surface must therefore offer the same proof object and verification result
without expanding authority.

## Current Evidence

- `harness/gateway.py` serves `/api/receipts/proof` by reading
  `receipts_ledger(...)`, extracting ordered envelope `sha256` leaves, and
  delegating to `harness.receipt_proof.route_payload`.
- `harness/gateway.py::_authorized` applies the configured gateway policy before
  dispatch. Public auth-off compatibility remains available when no gateway
  token is configured and the route is not private; when a token is configured,
  `harness.gateway_auth.check(...)` enforces bearer token and Host allowlist.
  `/api/receipts/proof` is not a private-custody route itself.
- `harness/receipt_proof.py` owns `flywheel.receipts-proof/v2` and returns the
  replayable proof object `{schema, leaf, index, tree_size, merkle_root,
  audit_path}`.
- `harness.agent_tools.dispatch("verify_receipt_inclusion", ...)` already
  reuses `build_receipt_proof(...)` and verifies with
  `harness.transparency_log.verify_inclusion(...)`.
- `harness/local_mcp.py` advertises `local_agent_*` and `local-model.*` tools,
  but no receipt proof tool.

## Operation Contract

Add one MCP tool:

`receipt.verify_inclusion`

Input:

- `leaf`: required string, exactly a lowercase 64-hex sha256 envelope digest.

Successful included output:

- `included`: `true`
- `status`: `included`
- `proof`: the exact `flywheel.receipts-proof/v2` proof object returned by the
  existing proof builder
- `verification`: replay data derived by calling
  `harness.transparency_log.verify_inclusion(requested_leaf, audit_path,
  merkle_root)`
- `does_not_prove`: non-empty list stating that membership/hash proof does not
  prove semantic correctness or evidence completeness

Missing well-formed leaf output:

- `included`: `false`
- `status`: `missing`
- `proof`: replay context containing the requested `leaf` and current
  `merkle_root` when available
- `reason`: `leaf not in the receipts log`
- `does_not_prove`: same limitation list

Corrupted or mismatched proof output:

- `included`: `false`
- `status`: `proof_corrupt` when the returned proof is not exactly the existing
  v2 proof contract or the requested leaf does not replay to the returned root
- `status`: `proof_leaf_mismatch` when the returned proof is otherwise a valid
  v2 proof for a different ledger leaf
- `proof`: the returned proof for replay/debugging
- `reason`: fixed text, not internal exception detail
- `does_not_prove`: same limitation list

Full v2 validation:

- `schema` must be `flywheel.receipts-proof/v2`.
- `leaf` must equal the requested leaf.
- `index` must be an integer in `[0, tree_size)`.
- `tree_size` must be a positive integer.
- `audit_path` must be a list of exact `{hash, side}` steps.
- The proof must match the proof re-derived from the same ordered ledger leaves
  via the existing `build_receipt_proof(...)`/`route_payload(...)` semantics
  before MCP reports `included: true`.
- A provider-native `included:false` result is `missing` only when it has the
  exact missing shape `{leaf, merkle_root}`. Proof-shaped failed results are
  corrupt, not absent.

Malformed input output:

- typed error, distinct from missing leaf
- no traceback or candidate-controlled internal detail

MCP response shape:

- Successful operation responses include both text JSON and `structuredContent`
  carrying the same object.
- `tools/list` exposes an accurate `outputSchema` for non-error operation
  responses.

Ledger context:

- MCP receipt verification uses the server startup repository root and run root,
  not tool-call arguments.
- `python -m harness.local_agent_cli --mcp --root <repo> --run-root <run-root>`
  must route the same ledger substrate as a gateway started with matching
  `--root` and `--run-root`.
- The tool input remains only `leaf`; it must not admit arbitrary paths,
  filesystem reads, or secret-bearing references.

The operation must be read-only. It must not approve proposals, mint grants,
write receipts, mutate the ledger, or loosen HTTP custody.

## Implementation Constraints

- Reuse the existing receipt inclusion operation and proof builder.
- Do not touch `harness/gateway.py` or `harness/receipt_proof.py` for this
  scoped parity change.
- Preserve the missing-versus-malformed distinction.
- Keep the MCP tool discoverable through `tools/list` and callable through
  real JSON-RPC `tools/call`.
- Descriptor metadata must describe HTTP custody as gateway-configured, not
  private bearer custody. This change documents the existing route policy and
  does not loosen gateway authentication.
- Validate the complete `flywheel.receipts-proof/v2` proof object before
  returning `included: true`; Merkle root replay alone is insufficient.
- Preserve absence, corrupt proof, malformed input, and unavailable ledger as
  distinct outcomes.
- Configure ledger root/run-root only at MCP server startup or direct test
  injection. Do not add root/path fields to the MCP tool call.
- Do not infer a broad safety verdict. The result is only a receipt-log
  membership/hash proof.
- Do not introduce non-stdlib dependencies.

## Tests

The focused test set must prove:

- `tools/list` advertises `receipt.verify_inclusion` with a strict input schema.
- `tools/list` advertises gateway-configured HTTP custody and an accurate MCP
  output schema.
- `tools/call` returns an included proof for an existing leaf and the proof
  exactly matches `route_payload(...)` for the same fixture.
- Receipt MCP responses include `structuredContent` while retaining text JSON.
- A well-formed absent leaf returns `included: false` with a current root and
  does not collapse into malformed-input handling.
- A malformed leaf returns a typed MCP error result.
- A corrupted proof false-success case is caught before the operation reports
  inclusion.
- Corrupt `schema`, `index`, and `tree_size` metadata cannot be echoed with
  `included: true`.
- Provider-native `included:false` with proof-shaped material is classified as
  `proof_corrupt`, not `missing`.
- A valid proof for a different leaf cannot satisfy the requested leaf.
- An actual stdio serve loop started with explicit root/run-root returns the
  same included proof as `route_payload(...)` over that configured run root.
- Unexpected operation failures return a typed unavailable error without raw
  exception detail.
- Existing local MCP tests and receipt proof tests still pass.

## Non-Goals

- No gateway route changes.
- No receipt proof schema changes.
- No release, deployment, publication, or installed-acceptance claim.
- No claim that a receipt's payload is true, complete, semantically correct, or
  sufficient for release.
