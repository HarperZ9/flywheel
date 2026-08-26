# Route identity and local endpoint readiness

## Purpose

Repair the identity boundary that blocked the truth-first benchmark without
rewriting Attempt 6 or making a provider call. The benchmark must distinguish a
stable model identity from a display label, an executable provider selector,
and a provider-attested observed identity. Local roles must select one exact
trained release profile and prove its digest rather than matching every profile
with the same parameter class.

## Evidence behind the change

- OpenAI documents the executable Spark slug as `gpt-5.3-codex-spark` and the
  display name as `GPT-5.3-Codex-Spark`.
- Attempt 6 passed `5.3-Codex-Spark` directly to `codex --model`; those 40 rows
  remain immutable historical evidence and do not establish canonical-route
  availability.
- The active model catalog lists the canonical slug, but it was fetched for a
  newer client than the pinned benchmark binary. Catalog visibility therefore
  remains preflight evidence, not execution evidence.
- Both local roles currently match three endpoint profiles. The trained release
  GGUF files and their offline Ollama manifests have independently rechecked
  hashes, but no matching service is running.
- The native Ollama adapter currently sends the receipt-style
  `ollama:<name>` value where the API expects `<name>`.

## Design

### Model identity

Each executable provider role carries these separate fields:

- `model_id`: stable comparison identity.
- `model_display_name`: operator-facing label.
- `requested_model_reference`: exact selector sent to the provider.
- `model_observed`: provider-attested identity only.
- `model_observation_basis`: the structured field or event that attested the
  observed value; otherwise `unknown`.

For the two Spark roles, all stable and requested identities use
`gpt-5.3-codex-spark`; the display name is `GPT-5.3-Codex-Spark`. The Codex
argv uses only `requested_model_reference`. A successful request without a
provider identity attestation leaves `model_observed` empty and records the
bounded limitation `provider_request_accepted_not_model_attested`.

The contract schema advances to v2. Readers may reject v1 rather than silently
coerce its overloaded `target_model`. Attempt 6 and its v1 contract copy remain
unchanged.

### Local route selection

The local roles select exactly:

- `local_14b` -> `ollama-release-14b`, backend `ollama`, model reference
  `ollama:flywheel-local-coder-14b`.
- `local_32b` -> `ollama-release-32b`, backend `ollama`, model reference
  `ollama:flywheel-local-coder-32b`.

The checked-in contract binds the stable selector fields and the release asset
hashes. Runtime-generated endpoint profiles bind their own canonical profile
hash and the expected Ollama manifest digest. Selection requires exact equality
for profile id, backend, model reference, and profile hash. Admission requires
the expected and observed Ollama digests to match. A present but different
digest is a mismatch, not readiness.

The native Ollama API receives the model name without the `ollama:` namespace.
The response `model` field must equal that native selector. No Serve profile is
accepted as evidence for the trained release GGUF.

### Route-readiness probe

This design prepares, but does not execute, a separate route-readiness phase:

- direct `codex_harness` only;
- canonical task `agt-001-index-fallback-integrity` only;
- one repetition and one provider subprocess;
- zero retries or fallback;
- `benchmark_counted=false`;
- no admission authority and no Flywheel or cohort readiness propagation.

The future receipt must bind the exact executable path, version and hash,
catalog-cache hash and version, argv, task and prompt hashes, trace and output
hashes, call/retry counts, requested/observed identities and observation basis.
Making this call requires separate operator approval.

### Local activation boundary

This change never starts Ollama, loads weights, imports or pulls a model,
displaces the unrelated service on port 8765, kills a process, retries, or runs
generation. Later activation requires separate authorization. The 14B and 32B
decisions remain independent.

### Lane health

MCP responsiveness is not inference readiness. A future status/doctor surface
must report exact profile, reference and digest state plus a fresh fixed-
generation receipt. Until all match, the local-model lane remains declared or
stale. This slice does not add a generic tool that could accidentally make the
lane live.

## Error behavior

- Missing or duplicated exact profile: `endpoint_profile_selection_mismatch`.
- Profile hash mismatch: `endpoint_gate_profile_sha256_mismatch`.
- Expected digest absent: `endpoint_profile_ollama_digest_missing`.
- Observed digest absent: `endpoint_gate_ollama_digest_missing`.
- Expected/observed digest unequal: `endpoint_gate_ollama_digest_mismatch`.
- Response model unequal to native selector: typed malformed provider output.
- No provider identity attestation: empty observed identity plus explicit
  limitation, not a copied requested value.

## Test strategy

Tests are written and observed failing before production changes. They cover:

- canonical Spark fields and argv selector;
- requested identity never becoming observed identity without attestation;
- exact local selector uniqueness and profile-hash matching;
- missing and mismatched expected/observed Ollama digests;
- native Ollama selector stripping and response-model validation;
- v1/v2 schema boundary and Attempt 6 immutability by path/hash fixture;
- no provider subprocess or endpoint call in contract/profile tests;
- all existing executor, adapter, endpoint-gate and static repository gates.

## Scope

Expected production files:

- `benchmarks/cross-harness-adapter-contract-v1.json` (renamed or replaced by a
  v2 contract with every checked-in caller updated)
- `harness/cross_harness_manifest.py`
- `harness/cross_harness_executor.py`
- `harness/cross_harness_adapters.py`
- `harness/adapter_runtime_matrix.py`
- endpoint profile/gate producers only where required for expected digest and
  exact selector binding

Every frozen file remains net-zero or shrinks. No unrelated refactor, service
operation, model execution, publication, deployment, or outreach is in scope.

## Acceptance

- Attempt 6 index SHA remains
  `2715a074c52806cd5983daa48a0c0f429ac6161a96ad58f6ff3d1b12073206d3`.
- Static generation yields one exact local profile per role.
- Provider argv uses `gpt-5.3-codex-spark`.
- No scorecard fabricates observed identity.
- Digest equality is required rather than digest presence.
- Focused tests and full repository gates pass.
- Independent specification and quality reviews find no material blocker.

## Status

Approved by the operator's 2026-08-12 direction to continue all non-outreach
work after the recommended contract-first design was presented. Provider calls
and service activation remain unapproved.
