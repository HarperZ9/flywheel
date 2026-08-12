# Route Identity and Local Endpoint Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Spark and local endpoint identities exact and re-checkable before any new provider or endpoint execution.

**Architecture:** Advance the checked-in adapter contract to v2 with separate stable, display, requested, and observed identity fields. Migrate manifest/executor consumers without coercing v1, then make runtime selection and Ollama admission bind exact profile hashes and expected digests. Provider calls and service activation remain outside this plan.

**Tech Stack:** Python 3.12 stdlib, JSON contracts, pytest, Flywheel receipt and file gates.

## Global Constraints

- Preserve Attempt 6 and artifact-index SHA `2715a074c52806cd5983daa48a0c0f429ac6161a96ad58f6ff3d1b12073206d3` unchanged.
- Make zero provider calls, zero endpoint calls, zero service starts and zero weight loads.
- Do not infer observed model identity from the requested identity.
- Use canonical Spark slug `gpt-5.3-codex-spark` and display `GPT-5.3-Codex-Spark`.
- Keep every new file at or below 300 lines and every frozen file net-zero or smaller.
- Do not publish, deploy, contact anyone, or alter unrelated worktrees.

---

### Task 1: Versioned Contract Identity

**Files:**
- Create: `benchmarks/cross-harness-adapter-contract-v2.json`
- Modify: checked-in command/deck/default files located by `rg "cross-harness-adapter-contract-v1"`
- Modify: `harness/adapter_runtime_matrix.py`, `harness/cross_harness_executor.py`, `harness/cross_harness_cli.py`, `harness/cross_harness_types.py`, and `harness/cross_harness_adapters.py` only for the v2 projection required to keep migrated defaults usable
- Test: `tests/test_cross_harness_manifest.py`

**Interfaces:**
- Produces provider-role fields `model_id`, `model_display_name`, and `requested_model_reference`.
- Produces exact local `endpoint_selector` fields `profile_id`, `backend`, `model_reference`, and release asset SHA.
- Consumers reject the v1 overloaded model contract rather than coercing it.
- Runtime rows and planned execution rows preserve v2 `model_id`; local runtime selection uses the contract's exact profile id, backend, and model reference.

**Review remediation:** This narrow consumer projection moved into Task 1 after independent specification review found v2 defaults still read `target_model`. It includes transporting `requested_model_reference` in `AttemptRequest`, using that value only for provider/profile selection, and keeping stable `model_id` as the comparison identity. Task 2 retains observed-identity semantics; Task 4 retains profile-hash and digest admission.

- [ ] **Step 1: Write failing contract tests**

Add assertions that the v2 Spark roles use the canonical slug in both stable and requested identity, the exact display name, and no `target_model`. Add assertions that each local role has one exact release selector and release asset SHA. Add a v1 fixture assertion that execution-ready manifest generation rejects the old schema with a typed schema mismatch.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_cross_harness_manifest.py -q`

Expected: failures because the v2 contract is absent and v1 is still accepted as the execution contract.

- [ ] **Step 3: Add the minimal v2 contract and update checked-in references**

Use these exact Spark values:

```json
"model_id": "gpt-5.3-codex-spark",
"model_display_name": "GPT-5.3-Codex-Spark",
"requested_model_reference": "gpt-5.3-codex-spark"
```

Use these exact local profile/ref pairs:

```text
local_14b -> ollama-release-14b / ollama / ollama:flywheel-local-coder-14b
local_32b -> ollama-release-32b / ollama / ollama:flywheel-local-coder-32b
```

Keep historical copied v1 contracts under external evidence roots untouched.

- [ ] **Step 4: Run GREEN and gates**

Run the focused manifest test and `python scripts/check_file_gate.py`.

- [ ] **Step 5: Commit Task 1**

Commit only the v2 contract, its direct checked-in references, and the focused test.

### Task 2: Manifest and Executor Identity Projection

**Files:**
- Modify: `harness/cross_harness_manifest.py`
- Modify: `harness/cross_harness_executor.py`
- Modify: `harness/cross_harness_types.py` only if a typed request field is required
- Test: `tests/test_cross_harness_manifest.py`
- Test: `tests/test_cross_harness_executor.py`

**Interfaces:**
- `AttemptRequest` request projection is complete in Task 1; Task 2 owns only the remaining observation fields.
- Scorecards carry `model_observed` and `model_observation_basis` separately.

- [ ] **Step 1: Write failing projection tests**

Assert that a returned adapter result with no observed attestation leaves `model_observed == ""` and `model_observation_basis == "unknown"`.

- [ ] **Step 2: Run RED**

Run the exact new manifest and executor tests. Expected failures should show the old `target_model`/`model_id` projection and copied observed identity.

- [ ] **Step 3: Implement minimal projection**

Add the limitation `provider_request_accepted_not_model_attested` when a request returned but no structured event attested the model.

- [ ] **Step 4: Run GREEN and adjacent executor tests**

Run `tests/test_cross_harness_manifest.py`, `tests/test_cross_harness_executor.py`, and `tests/test_cross_harness_artifacts.py`.

- [ ] **Step 5: Commit Task 2**

Commit only the manifest/executor/type changes and their tests.

### Task 3: Direct and Flywheel Adapter Observation Truth

**Files:**
- Modify: `harness/cross_harness_adapters.py`
- Modify: `harness/cross_harness_process.py` only if the existing bounded event parser needs an identity accessor
- Test: `tests/test_cross_harness_adapters.py`
- Test: `tests/test_cross_harness_process.py`

**Interfaces:**
- Codex argv request-reference projection moved to Task 1.
- Structured provider events may yield `(observed_model, basis)`; absence yields `("", "unknown")`.

- [ ] **Step 1: Write failing direct and inner-adapter tests**

Cover canonical argv, no-attestation empty observation, a bounded structured attestation, and spoofed prose/self-report that must not attest identity.

- [ ] **Step 2: Run RED**

Run the exact new adapter/process tests. Expected failures should show argv/model use of the overloaded field and request-derived observation.

- [ ] **Step 3: Implement the smallest trusted-event extraction**

Only accept an already bounded structured event field explicitly designated by the provider protocol. Do not parse final prose for model identity. Direct and Flywheel paths must produce identical semantics.

- [ ] **Step 4: Run GREEN plus provider-boundary regression**

Run the two focused files plus executor tests. Verify no real process runner or network seam is used.

- [ ] **Step 5: Commit Task 3**

Commit exact adapter/process/test scope.

### Task 4: Exact Local Profile and Digest Admission

**Files:**
- Modify: `harness/adapter_runtime_matrix.py`
- Modify: `scripts/run_model_endpoint_profiles.py`
- Modify: `scripts/run_model_endpoint_gate.py`
- Test: `tests/test_adapter_runtime_matrix.py`
- Test: `tests/test_model_endpoint_profiles.py`
- Test: `tests/test_model_endpoint_gate.py`

**Interfaces:**
- Profile rows expose an expected Ollama manifest digest for exact release profiles.
- `_profile_matches` consumes the contract `endpoint_selector` and requires exact profile id/backend/model ref/profile hash.
- Gate admission compares expected and observed digest equality.

- [ ] **Step 1: Write failing selector and digest tests**

Prove that model-size-only selection currently returns three candidates, a nonempty wrong digest currently passes the digest-presence gate, and missing expected digest lacks a typed profile failure.

- [ ] **Step 2: Run RED**

Run the three focused test files. Expected failures must correspond to ambiguity and digest-presence behavior.

- [ ] **Step 3: Implement exact selection and digest equality**

Use failure codes from the design. Never read or call a live endpoint. Expected release manifest digests must come from bounded checked-in/profile inputs, not a provider call.

- [ ] **Step 4: Run GREEN and runtime consumers**

Run the three focused tests, `tests/test_cross_harness_seed_steps.py`, and runtime-matrix CLI tests.

- [ ] **Step 5: Commit Task 4**

Commit the exact profile/gate/runtime files and tests.

### Task 5: Native Ollama Request Identity

**Files:**
- Modify: `harness/cross_harness_adapters.py`
- Test: `tests/test_cross_harness_adapters.py`

**Interfaces:**
- Receipt reference `ollama:<native>` maps to API selector `<native>`.
- A successful `/api/chat` response must carry exactly that native selector in `model`.

- [ ] **Step 1: Write failing adapter tests**

Test prefix removal, already-native idempotence, response-model equality, missing response model, and mismatched response model. Use injected HTTP responses only.

- [ ] **Step 2: Run RED**

Expected: the request body contains `ollama:` and mismatched response identity is accepted or misclassified.

- [ ] **Step 3: Implement minimal selector normalization and validation**

Remove one leading `ollama:` only. Do not rewrite other namespaces. Map missing/mismatched structured identity to typed malformed provider output.

- [ ] **Step 4: Run GREEN and full adapter suite**

Run adapter, executor, and process tests.

- [ ] **Step 5: Commit Task 5**

Commit the adapter and its tests only.

### Task 6: Static Verification and Independent Review

**Files:**
- Modify: `project-docs/specs/SPEC-2026-08-12-route-identity-readiness.md`
- Review: all commits in this branch

**Interfaces:**
- Produces a code-complete, provider-call-free route contract ready for a separately approved probe.

- [ ] **Step 1: Run focused integration suites**

Run manifest, executor, artifacts, adapters, process, endpoint profiles, endpoint gate, runtime matrix, seed steps, comparison and outcome tests.

- [ ] **Step 2: Run repository gates**

Run file, stdlib, claim-language, public-instructions, compile and diff gates.

- [ ] **Step 3: Run the full suite**

Run `python -m pytest tests/ -q` under the existing 900-second bound. Record exact exit, duration and warnings without inferring hidden counts.

- [ ] **Step 4: Verify no operational side effects**

Confirm no new provider receipts, endpoint requests, listener changes, model processes, service starts, or Attempt 6 mutations. Re-hash the Attempt 6 artifact index.

- [ ] **Step 5: Request independent spec and quality reviews**

Reviewers must test identity spoofing, schema downgrade, profile ambiguity, digest mismatch, namespace normalization, secret hygiene and frozen-file ceilings.

- [ ] **Step 6: Update spec status and commit**

Mark implemented requirements only after evidence exists. Preserve separately gated next actions for the Spark call and local activation.
