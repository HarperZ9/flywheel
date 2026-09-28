# Incident-sim process-audit review API

`POST /api/incident-sim/process-audit/review` is a private, authenticated review route for an already-built incident-sim process-audit packet. It is for desktop and local clients that need the same offline packet check exposed over the gateway without creating state.

The request body accepts the inner `flywheel.incident-sim-process-audit/v1` packet JSON itself, encoded as UTF-8 with `Content-Type: application/json`. If a CLI command wrote an outer command report, send the value at `audit_packet`, not the outer report. A separate review-request wrapper can supply expected gateway hashes, as described below. The route rejects bodies over 1 MiB, duplicate JSON keys, non-finite JSON values, wrong media types, and non-packet JSON.

Successful responses use `flywheel.incident-sim-process-audit-review/v1` and include:

- `source.format`, `source.sha256`, and `source.byte_length` over the exact uploaded request bytes.
- `verification`, the shared `verify_process_audit_packet` result.
- `gateway_effect_verification`, separating internal consistency, expected-hash correspondence, observed effect coverage, and semantic correctness. A packet without the optional gateway component remains supported.
- `assessment`, either `packet-local-match` or `packet-local-drift`.
- `semantic_verification: UNVERIFIABLE`.
- `declared_access`, including `NOT_ASSESSED` when the packet has no institutional-access component. `coverage_assessment` is checked coverage only; copied packet claims appear as `reported_coverage_assessment` when the access component drifts, with limit strings marking them untrusted.
- `source_pointers`, packet-local JSON pointers with the exact reviewer-facing values used for review, including the evaluation verdict, packet source values, independence data, and institutional-access assessment fields when present.
- `does_not_prove`, including the coherent-local-rewrite limitation.

The route does not persist packets, read local paths from the browser, fetch resources, mint keys, call external services, or turn a matching packet digest into a semantic pass. A tampered packet is a normal review result with a drift verdict, while malformed transport input returns `flywheel.evidence-transport-error/v1`.

Client error codes:

- `AUTH_REQUIRED` when the private gateway route has no valid owner token.
- `UNSUPPORTED_MEDIA_TYPE` for non-JSON content types.
- `PAYLOAD_TOO_LARGE` when the body is over 1 MiB.
- `INVALID_JSON` for invalid UTF-8, duplicate keys, non-finite values, or other strict JSON failures.
- `INVALID_PACKET` when strict JSON is valid but the packet schema is not `flywheel.incident-sim-process-audit/v1`.

## Separately supplied gateway reference

For a packet containing `gateway_effect`, clients may send a wrapper with schema
`flywheel.incident-sim-process-audit-review-request/v1`. Its `packet` field holds
the inner process-audit packet. Its optional `expected_hashes` object accepts
`terminal_result_sha256`, `lifecycle_history_sha256`, and `trace_records_sha256`.
These are SHA-256 digests of the canonical JSON values, not hashes of arbitrarily
formatted source files. Keep the reference and its provenance separate from the
producer's packet when assessing continuity.

The response's `source.sha256` covers the exact submitted wrapper bytes when a
wrapper is used. Existing `source_pointers` remain relative to the inner packet.
Preserve both locations when storing a response alongside its uploaded request.

An expected digest supplied separately is a comparison input. The verifier does
not authenticate its origin or establish that it was independently retained.
A coherent rewrite of the packet and every packet-local digest can remain
internally consistent. Independent retention must be established outside that
local consistency check; semantic correctness remains unverified.
