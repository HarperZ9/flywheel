# Flywheel Engine Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a fail-closed, receipt-backed Flywheel engine; make its flagship and infrastructure modules interoperable; produce current executable, endpoint, and benchmark evidence; and regenerate every affected public document, demo, deck, portfolio surface, and profile from that verified state.

**Architecture:** Proof Surface owns closed receipt and inner authorization contracts. `public/flywheel` is the single platform and package source; `local-model` is a lane consumed through versioned endpoint and manifest contracts. Flywheel composes trusted authorization, atomic usage state, governance, boot, gateway, lanes, and desktop views. Mneme, Relay, and Plexus adopt those contracts only after the governance spine lands. The benchmark executor consumes the existing cross-harness manifest and preserves one commit-pinned artifact tree. Public derivatives are allowlisted and generated only after engine and evidence gates pass. Exact pre-dispatch decisions live in `docs/superpowers/specs/2026-08-02-execution-contracts.md`.

**Tech Stack:** Python 3.11+, standard-library verifier path, optional `cryptography` for Ed25519, JSON Schema, Node.js ESM, Rust/Cargo, Flutter/Dart, PyInstaller, Inno Setup, GitHub Actions, static HTML/CSS/JavaScript.

## Global Constraints

- Never commit secrets, `.env` data, tokens, private keys, browser profiles, protected corpus material, private state-domain artifacts, prospect material, or client data.
- Never force-push. Work on non-default branches, require terminal-green CI, merge with expected-head protection, and verify live default SHAs.
- No learned model decides an accept verdict. Independent checkers and explicit policy gates decide.
- No receipt, no accept. Missing, malformed, stale, unsigned, untrusted, expired, revoked, wrong-scope, or exhausted authority fails closed.
- TADR consequence tier, verifier strength, and operational severity remain distinct.
- Preserve v1 bytes and hashes when optional governance fields are absent, or introduce an explicit v2 reader/writer pair with migration fixtures.
- Keep the verifier path zero-runtime-dependency. Optional crypto and provider SDKs may not weaken the stdlib fallback.
- Public prose uses two type families, verdict-only color, feature-first wording, ASCII punctuation, no em dashes, no local paths, no unsupported exclusivity, and explicit honest nulls.
- Model weights remain unpublished until the generated release manifest passes every gate and the operator separately authorizes model publication.
- Preserve unrelated dirty work, including the existing project-docs session file and private Telos runtime material.

---

## Repository and branch map

| Repository | Implementation base | Branch policy |
| --- | --- | --- |
| `public/flywheel` | existing `feat/governance-integration` at `9c7d86c` | continue the branch; never raise frozen file ceilings |
| `public/proof-surface` | current `origin/main` | fresh `feat/tadr-governance-contracts` worktree |
| `public/mneme` | current `origin/main` | fresh `feat/governed-replay` worktree |
| `public/relay` | current `origin/main` | fresh `feat/governed-relay`; port the useful probe intent, not the stale branch wholesale |
| `public/plexus` | current `origin/main` | fresh `feat/owner-manifest-probe` worktree |
| Gather, Crucible, Index, Forum, Learn, Telos | current `origin/main` | fresh narrow branches; port only owner manifests or required fixes |
| `local-model` | current `origin/main` | lane-only worktree if model-serving code needs a proven fix; no Flywheel platform duplication |
| `buildlang` | current `origin/main` | fresh `feat/flywheel-receipt-release-gate`; preserve the unrelated docs branch untouched |
| portfolio, profile, project-docs, flywheel-desktop | current workflow branches after provenance check | update only after upstream product SHAs are live |

## Shared interfaces

These names are fixed for every task:

```python
def verify_trusted_authorization(
    receipt: dict,
    *,
    trusted_fingerprints: frozenset[str],
    expected_agent_id: str,
    expected_action: str,
    expected_target: str,
    now: str,
    actions_used: int,
) -> dict:
    """Return a typed MATCH or UNVERIFIABLE authorization decision."""

def build_control_receipt(
    *,
    system_id: str,
    classification_ref: str,
    tier: str,
    observations: list[dict],
    checked_at: str,
    checker_id: str,
) -> dict:
    """Return flywheel.tadr-control/v1 with a canonical SHA-256 seal."""

def execute_cross_harness_manifest(
    manifest: dict,
    *,
    artifact_root: str,
    selected_task_ids: tuple[str, ...],
    selected_roles: tuple[str, ...],
    repetitions: int,
) -> dict:
    """Emit one run index and one typed attempt receipt per selected row."""
```

Owner manifests use `flywheel.interop-manifest/v1` and must declare `schema`, `manifest_version`, `component`, `component_version`, `owner_repo`, `source_commit`, `capabilities`, `receipt_kinds`, `governance_envelope`, and `health`.

---

### Task 0: Bootstrap durable acceptance recording and freeze the execution contract

**Files:**
- Create: `scripts/run_acceptance_command.py`
- Create: `tests/test_run_acceptance_command.py`
- Add: the design, execution-contract, and implementation-plan documents in `docs/superpowers/`

**Interfaces:**
- Consumes: the evidence-root and command-receipt contract in the execution-contract spec.
- Produces: one shell-free command runner that records every later implementation and acceptance command under the durable closeout root.

- [ ] **Step 1: Write recorder failures first**

Cover argv preservation, repository-relative cwd identity, source repository and HEAD, exit code, start/end/duration, stdout/stderr files and hashes, environment names without values, secret-value redaction, output size limits, `does_not_prove`, and refusal to write outside the configured evidence root.

- [ ] **Step 2: Implement the minimal recorder**

Accept argv as a JSON array or repeated argument and launch without a shell. Record a typed `flywheel.acceptance-command/v1` receipt even when the child fails. Never serialize environment values, authorization material, tokens, or private keys.

- [ ] **Step 3: Prove the recorder and freeze inputs**

Run its full test file once directly because the recorder cannot receipt its own bootstrap. Then run a passing and failing fixture through it and validate both receipt trees. After this point every command block in every later task is passed as inner argv to the recorder.

- [ ] **Step 4: Commit and push the bootstrap**

Commit message: `chore: freeze engine closeout contracts`

---

### Task 1: Close Proof Surface TADR and trusted-authorization contracts

**Files:**
- Modify: `public/proof-surface/src/proof_surface/organ_receipt_bundle.py`
- Modify: `public/proof-surface/schemas/organ-receipt-bundle.schema.json`
- Modify: `public/proof-surface/src/proof_surface/authorization_receipt.py`
- Create: `public/proof-surface/conformance/organ-receipt-bundle/v0.1/valid/tadr-kinds.bundle.json`
- Create: `public/proof-surface/conformance/organ-receipt-bundle/v0.1/invalid/tadr-zero-digest.bundle.json`
- Modify: `public/proof-surface/conformance/organ-receipt-bundle/v0.1/manifest.json`
- Create: `public/proof-surface/tests/test_organ_receipt_bundle_tadr_kinds.py`
- Modify: `public/proof-surface/tests/test_authorization_receipt.py`
- Modify: `public/proof-surface/USAGE.md`
- Modify: `public/proof-surface/CHANGELOG.md`

**Interfaces:**
- Consumes: existing `validate_organ_receipt_bundle()` and `check_action()` contracts.
- Produces: accepted kinds `tadr-classification` and `tadr-control`; authorization decisions that enforce exact action, target, expiry, revocation, agent identity, and `max_actions`.

- [ ] **Step 1: Write failing TADR bundle tests**

```python
def test_mixed_tadr_bundle_validates():
    result = validate_organ_receipt_bundle(load_vector("valid/tadr-kinds.bundle.json"))
    assert result["verdict"] == "MATCH"

def test_zero_control_digest_is_rejected():
    result = validate_organ_receipt_bundle(load_vector("invalid/tadr-zero-digest.bundle.json"))
    assert result["verdict"] == "UNVERIFIABLE"
```

- [ ] **Step 2: Run focused tests and confirm rejection under the current closed enum**

Run: `python -m pytest -q tests/test_organ_receipt_bundle_tadr_kinds.py`

Expected: the valid vector fails because both receipt kinds are unknown.

- [ ] **Step 3: Add the two sorted kinds, schema entries, and conformance vectors**

Reject missing, malformed, and all-zero payload SHA-256 values. Preserve every legacy kind and vector unchanged.

- [ ] **Step 4: Write failing authorization budget and exact-scope tests**

```python
def test_action_budget_is_consumed():
    decision = check_action(receipt, "lane.call", "forum/forum_route", actions_used=1)
    assert receipt["max_actions"] == 1
    assert decision["verdict"] == "UNVERIFIABLE"

def test_target_scope_is_exact():
    decision = check_action(receipt, "lane.call", "forum/forum_verify", actions_used=0)
    assert decision["reason"] == "target_mismatch"
```

- [ ] **Step 5: Implement strict action-count and exact-target enforcement**

Do not add crypto here. Proof Surface validates the inner authorization structure; Flywheel Task 3 verifies the external trusted signature.

- [ ] **Step 6: Run full contract gates**

Run:

```powershell
python -m pytest -q
python -m proof_surface.cli validate conformance/organ-receipt-bundle/v0.1/valid/tadr-kinds.bundle.json
python scripts/check_public_surface.py
```

- [ ] **Step 7: Commit**

Commit message: `feat: close TADR and authorization receipt contracts`

---

### Task 2: Make Flywheel governance primitives fail closed and preserve compatibility

**Files:**
- Modify: `harness/governance/tadr_tier.py`
- Modify: `harness/governance/control_baseline.py`
- Modify: `harness/governance/tadr_receipt.py`
- Modify: `harness/governance/tadr_interop.py`
- Modify: `harness/governance_envelope.py`
- Modify: `harness/infra/run_bom.py`
- Modify: `harness/infra/incident_sheet.py`
- Modify: `harness/infra/correlator.py`
- Modify: `harness/infra/trust_model.py`
- Create: `tests/fixtures/governance/legacy-v1.json`
- Modify: `tests/test_governance_tadr.py`
- Modify: `tests/test_governance_envelope.py`
- Create: `tests/test_governance_interop.py`
- Modify: `tests/test_infra_correlator_bom.py`
- Modify: `tests/test_infra_trust_acquisition.py`

**Interfaces:**
- Consumes: Proof Surface's closed receipt kinds from Task 1.
- Produces: validated TADR classifications, explicit `present | absent | unknown` control observations, sealed `flywheel.tadr-control/v1`, fail-closed envelopes, and verified bundle entries.

- [ ] **Step 1: Add negative tests for unknown and missing governance state**

```python
def test_missing_compliance_pauses():
    env = build_envelope(classification=valid_classification, compliance=None)
    assert env.governance_verdict == "pause"

def test_unknown_action_tier_never_authorizes():
    assert allows_action(valid_envelope, "T9") is False

def test_fingerprint_binds_every_decision_field():
    assert replace(valid_envelope, risk_signals=["new"]).fingerprint != valid_envelope.fingerprint
```

- [ ] **Step 2: Confirm the current tests fail because missing evidence allows and unknown tiers rank as zero**

Run: `python -m pytest -q tests/test_governance_envelope.py tests/test_governance_tadr.py`

- [ ] **Step 3: Implement closed validation and full canonical fingerprints**

Reject unknown tiers, modifiers, override names, assessment keys, assessment values, indicator classes, uncertainty values, and command-role names. Compute the envelope fingerprint from the canonical JSON of every decision-relevant field.

- [ ] **Step 4: Replace boolean control facts with evidence observations**

```python
@dataclass(frozen=True)
class ControlObservation:
    control_id: str
    state: Literal["present", "absent", "unknown"]
    source_ref: str
    observed_at: str
    checker_id: str
```

Unobserved controls become `unknown`; no control defaults to present. The report must publish measured, required, present, absent, and unknown counts.

- [ ] **Step 5: Build and verify a real control receipt**

`build_control_receipt()` must seal the complete observation list and return a nonzero digest. `control_entry()` rejects missing seals. `classification_entry()` calls the structural verifier and cannot emit `pass` without a separate trusted-authority decision.

- [ ] **Step 6: Propagate validated governance references without changing legacy bytes**

Add classification reference, tier, modifiers, governance verdict, pause triggers, and control digest only when present. Keep severity and verifier strength separate. Load `legacy-v1.json` and assert byte-identical serialization and seals.

- [ ] **Step 7: Run focused and cross-repository tests**

Run:

```powershell
python -m pytest -q tests/test_governance_tadr.py tests/test_governance_envelope.py tests/test_governance_interop.py tests/test_infra_correlator_bom.py tests/test_infra_trust_acquisition.py
python -m pip wheel --no-deps <proof-surface-source> --wheel-dir <temporary-wheelhouse>
python -m pip install --no-index --find-links <temporary-wheelhouse> proof-surface
python -m pytest -q tests/test_governance_interop.py
```

The conformance process uses a clean temporary environment and the exact Proof
Surface wheel produced from Task 1. A sibling-source `PYTHONPATH` is never an
acceptance gate.

- [ ] **Step 8: Commit**

Commit message: `fix: make governance evidence fail closed`

---

### Task 3: Establish trusted signatures, governed boot, and exact-scope gateway calls

**Files:**
- Modify: `harness/crypto/signatures.py`
- Modify: `harness/receipt_sign.py`
- Create: `harness/governance_authorization.py`
- Create: `harness/authorization_store.py`
- Create: `harness/governance_state.py`
- Create: `harness/governance_gateway.py`
- Modify: `harness/boot.py`
- Modify: `harness/gateway.py`
- Modify: `harness/gateway_auth.py`
- Modify: `tests/test_crypto_signatures.py`
- Create: `tests/test_authorization_store.py`
- Create: `tests/test_governance_state.py`
- Modify: `tests/test_boot.py`
- Create: `tests/test_gateway_governance.py`
- Modify: `scripts/check_file_gate.py`
- Restore: `project-docs/records/2026-07-25-file-gate-burndown.md`

**Interfaces:**
- Consumes: validated inner authorization receipts from Task 1, governance primitives from Task 2, and the exact keyring/state/SQLite contract in `docs/superpowers/specs/2026-08-02-execution-contracts.md`.
- Produces: `verify_trusted_authorization()`, atomic nonce/action-budget consumption, authenticated append-only revocation ingestion, externally signed governance state, typed governance state loading, boot prompt hydration, and POST classify/compliance/lane-call services.

- [ ] **Step 1: Write signature substitution and malformed-input tests**

```python
def test_embedded_attacker_key_is_not_trusted():
    wrapped = wrap_signed(inner, attacker_private_key)
    decision = verify_signed(wrapped, trusted_fingerprints={trusted_fingerprint})
    assert decision["verdict"] == "UNVERIFIABLE"

def test_malformed_base64_returns_typed_result():
    wrapped["signature"]["value"] = "***"
    assert verify_signed(wrapped, trusted_fingerprints={trusted_fingerprint})["reason"] == "malformed_signature"
```

- [ ] **Step 2: Consolidate verification on an external trust anchor**

Recompute the fingerprint, compare it to a configured keyring, catch all decode/key errors, validate the inner schema, and return separate `signature_valid` and `authority_trusted` fields. Preserve the stdlib verification path.

- [ ] **Step 3: Write and implement atomic authorization-store tests**

Use a temporary SQLite database. Test unique nonces, expiry, revocation, corrupt or unavailable storage, and two concurrent calls competing for the final allowance. `BEGIN IMMEDIATE` must let exactly one call consume that allowance; every store error denies before product code runs.

- [ ] **Step 4: Write state-signing and revocation-ingestion tests**

Cover canonical signed bytes, signer timeout/nonzero/extra output, inactive or mismatched fingerprint, tampered state, key rotation, valid append-only revocation import, idempotent replay, sequence rollback, conflicting rows, revoked signer, and all-or-nothing store failure. The signer and import configuration are process owned and cannot appear in request JSON.

- [ ] **Step 5: Add governed boot tests**

Assert valid state attaches and hydrates tier/verdict/classification digest; absent, malformed, stale, paused, and denied state produces a non-authorizing paused envelope; legacy packets without the field still parse.

- [ ] **Step 6: Implement `governance_state.py`, revocation ingestion, and wire boot**

The configured signed state file is written only by exact-scope classification/compliance endpoints using the external signer protocol, fsync, and atomic replace. The loader verifies canonical bytes, active signer trust, signatures, revocation, cross-references, and the 24-hour maximum age. The CLI imports only authenticated, monotonic, append-only revocation sets in one transaction. Neither path synthesizes allow from missing state. Prompt hydration renders facts only and cannot grant authority.

- [ ] **Step 7: Write exact POST-route tests before implementation**

```python
def test_lane_call_requires_exact_scope(client):
    response = client.post("/api/lanes/call", json={
        "lane": "forum", "tool": "forum_route", "arguments": {},
        "authorization_receipt": signed_for("forum/forum_verify"),
    })
    assert response.status_code == 403
    assert fake_mcp.calls == []
```

Cover 400 malformed, 401 bearer failure, 403 missing/invalid/expired/revoked/exhausted/wrong-scope authority, 404 unknown canonical lane/tool, 503 typed unavailable, and 200 exact scope.

- [ ] **Step 8: Implement the three service operations in `governance_gateway.py`**

- `POST /api/governance/classify`
- `POST /api/governance/compliance`
- `POST /api/lanes/call`

Resolve lane commands and tools only from the canonical manifest. Never accept caller argv, command paths, roots, or environment overrides.
Consume the action allowance atomically before calling classification, compliance, or lane code. A denied or failed consumption must leave the product call count at zero.

- [ ] **Step 9: Restore and harden the file gate**

Restore the old `gateway.py` ceiling. Move route logic out of the file. Make the gate compare the burn-down table with the merge base and fail if any grandfathered ceiling or total grows.

- [ ] **Step 10: Run gates and commit**

Run:

```powershell
python -m pytest -q tests/test_crypto_signatures.py tests/test_authorization_store.py tests/test_governance_state.py tests/test_boot.py tests/test_gateway_governance.py
python scripts/check_file_gate.py
python scripts/check_verifier_stdlib.py
```

Commit message: `feat: enforce trusted governed lane calls`

---

### Task 4: Repair Cloud IAM, Lean, and native-backend claim boundaries

**Files:**
- Modify: `harness/infra/cloud_iam.py`
- Modify: `harness/infra/kill_switch.py`
- Modify: `harness/infra/lean_adapter.py`
- Modify: `harness/lean_oracle.py`
- Modify: `harness/infra/native_detect.py`
- Create: `schemas/tadr-governance-v1.schema.json`
- Create: `docs/governance/TADR-DERIVATION.md`
- Modify: `tests/test_infra_cloud_iam.py`
- Modify: `tests/test_infra_lean_adapter.py`
- Modify: `tests/test_infra_native_detect.py`
- Modify: `docs/ASSESSMENT-AGENTIC-SECURITY-2026-08.md`

**Interfaces:**
- Consumes: trusted signed authorization from Task 3.
- Produces: exact revocation accounting, no live IAM call without dual authority, Lean results labeled by actual isolation posture, and backend receipts that name Python versus native execution.

- [ ] **Step 1: Write all-fail, partial, full, dry-run, and authority tests for IAM**

Assert `credentials_requested` and `credentials_revoked` are distinct; all-fail returns `executed=false` and zero revoked; dry-run returns zero revoked; same authority, missing signed authority, expired authority, and revoked authority execute no SDK call.

- [ ] **Step 2: Implement dual-authorized aggregate revocation**

Require two distinct confirmed authorities plus the Task 3 trusted receipt at the only public entrypoint. Revoke Vault leases before the self token. Seal all provider results, the kill-request seal, authorization reference, numerator, and denominator.

- [ ] **Step 3: Narrow Lean and native claims in tests first**

Until an isolated pinned Lean sidecar exists, both `lean_oracle` and the infrastructure adapter must refuse untrusted input and remain `UNVERIFIABLE` for promotion. Trusted local-artifact checks record the trust declaration, toolchain hash, platform, source hash, imports, axiom/admitted-hole checks, command, timeout, and isolation status. If `_flywheel_native` cannot be invoked, receipts must say `python`, never `native`.

- [ ] **Step 4: Implement actual backend dispatch or remove the native label**

Prefer a real `_flywheel_native` call only if the extension, ABI, build, package, and deterministic parity vectors are available. Otherwise keep the Python implementation and change public status to `python_reference_backend`.

- [ ] **Step 5: Correct research and product claims**

Cite the OpenAI PDF and arXiv v1 exactly. Describe 30,046 agent runs, about 3,300 successful agents, 340 targets, one week, 130K lines, and 5,900 declarations, plus semantic-faithfulness limits. Check in a Flywheel-owned derived TADR schema and a provenance note with doctrine version and source hash but no machine path. State that selected concepts derive from operator-provided doctrine, not an official standard or certification. State that the Lean paths check supplied trusted artifacts only and do not formalize or validate the ten results.

- [ ] **Step 6: Run tests and commit**

Run: `python -m pytest -q tests/test_infra_cloud_iam.py tests/test_infra_lean_adapter.py tests/test_infra_native_detect.py`

Commit message: `fix: align infrastructure receipts with executed evidence`

---

### Task 5: Ship a defensive native Governance desktop surface and CI gate

**Files:**
- Create: `desktop/lib/models/governance.dart`
- Modify: `desktop/lib/client/gateway_client.dart`
- Modify: `desktop/lib/views/governance_view.dart`
- Create: `desktop/test/governance_models_test.dart`
- Create: `desktop/test/governance_view_test.dart`
- Modify: `.github/workflows/ci.yml`
- Remove or retire: `desktop/.github/workflows/ci.yml`

**Interfaces:**
- Consumes: Task 3 gateway JSON.
- Produces: defensive tier, classification, control-evidence, and authorization-drift models with `match | drift | unverifiable` display states.

- [ ] **Step 1: Write model tests for empty, partial, wrong-type, stale, and complete JSON**

```dart
test('wrong checks type becomes unverifiable', () {
  final report = GovernanceReport.fromJson({'checks': 'bad'});
  expect(report.verdict, GovernanceVerdict.unverifiable);
});
```

- [ ] **Step 2: Run the focused Dart tests and confirm the model is absent**

Run: `flutter test test/governance_models_test.dart`

- [ ] **Step 3: Implement typed defensive parsing and client methods**

The client returns typed unavailable results for non-2xx, malformed JSON, and missing fields. Tier descriptions remain server-owned.

- [ ] **Step 4: Write widget tests for offline, malformed, drift, partial evidence, pass, and fail states**

The view must clear a previous error after successful reload and render missing compliance as UNVERIFIABLE rather than omitting it.

- [ ] **Step 5: Implement the view and label the checker accurately**

Use `Partial TADR control-evidence check` until measured coverage reaches the full required set. Render measured/required coverage.

- [ ] **Step 6: Add discoverable root CI commands**

Run `flutter analyze`, `flutter test`, and `flutter build windows --release` with `working-directory: desktop`. Preserve the existing Python matrix.

- [ ] **Step 7: Run local gates and commit**

Run:

```powershell
flutter analyze
flutter test
flutter build windows --release
```

Commit message: `feat: make governance state visible and defensive`

---

### Task 6: Harden Mneme replay and Relay authority, probes, transports, and receipts

**Files:**
- Modify: `public/mneme/src/mneme/replay.py`
- Modify: `public/mneme/src/mneme/memory.py`
- Modify: `public/mneme/src/mneme/mcp.py`
- Modify: `public/mneme/mneme.interop.json`
- Modify: `public/mneme/tests/test_crucible_replay.py`
- Create: `public/mneme/tests/test_mneme_mcp_replay.py`
- Create: `public/mneme/tests/test_mcp_governance.py`
- Modify: `public/relay/src/relay/local_mcp.py`
- Modify: `public/relay/src/relay/local_tools.py`
- Modify: `public/relay/src/relay/injection_probe.py`
- Modify: `public/relay/src/relay/endpoints.py`
- Modify: `public/relay/src/relay/messages_api.py`
- Modify: `public/relay/src/relay/local_loop.py`
- Create or modify: `public/relay/relay.interop.json`
- Create: `public/mneme/src/mneme/governance_client.py`
- Create: `public/relay/src/relay/governance_client.py`
- Create: `public/relay/tests/test_local_mcp_governance.py`
- Modify: `public/relay/tests/test_injection_probe.py`
- Modify: `public/relay/tests/test_endpoints.py`
- Modify: `public/relay/tests/test_messages_api.py`
- Modify: `public/relay/tests/test_local_agentic.py`

**Interfaces:**
- Consumes: `flywheel.governance-envelope/v1` and the process-owner verifier-command protocol defined in the execution-contract spec.
- Produces: immutable replay at every public boundary; server-owned Relay root/permission ceiling; fail-closed standalone authority consumption; side-effect-free probe; consistent non-2xx behavior; sealed `relay.turn-receipt/1`; Mneme and Relay owner manifests.

- [ ] **Step 1: Write the Mneme low-level bypass regression**

Direct public replay on a writable or ordinary read-only store must fail. CLI, library, and MCP success must use a process-owned immutable private snapshot.

- [ ] **Step 2: Enforce immutable replay and managed MCP lifecycle**

Expose `mneme.replay_crucible` through MCP. Close stores in `finally` or keep one managed server-lifetime store. Require governance for replay and forget; strict malformed requests return typed JSON-RPC errors.

- [ ] **Step 3: Write Relay authority and root-escape tests**

Cover missing/forged/expired/paused/wrong-tier authority, caller attempts to raise write/exec, caller attempts to select a different root, write-only authority, exec authority, and one exact allowed case.

For both Mneme and Relay, also cover missing verifier configuration, verifier
timeout/nonzero/malformed output, request-digest mismatch, and the one exact
MATCH decision. The verifier command and injected verifier are fixed at process
construction and cannot be supplied or replaced by an MCP caller.

- [ ] **Step 4: Make root and maximum permissions server-owned**

Remove `root`, `allow_write`, and `allow_exec` as authority-granting request fields. Prefer argv execution. If shell remains available, label an external OS/container sandbox as required and never describe the denylist as containment.

Implement the shared verifier protocol as small repository-local clients that
invoke the installed Flywheel CLI without a shell. Preserve zero runtime
dependencies. Missing or failed verification denies mutation before any product
call. Commit each repository's own owner manifest with its code.

- [ ] **Step 5: Make the injection probe side-effect-free**

Use a recording executor for write/edit/exec under every gate state. Hash canonical full scenarios, include injected text and arguments, report denominator and class coverage, and assert a tree receipt is byte-identical before/after even with write enabled.

- [ ] **Step 6: Normalize provider errors and deepen receipt binding**

Call `_require_ok()` for Anthropic and Gemini. Define full SHA-256 request/model/response binding, method version, stop reason, reproducibility state, denominator, and `does_not_prove`. Return UNVERIFIABLE when reconstruction inputs are absent. MCP returns the full receipt and a sealed ledger reference.

- [ ] **Step 7: Run full suites and commit separately per repo**

Run:

```powershell
python -m pytest -q
python -m build
```

Commit messages:

- Mneme: `fix: enforce immutable governed replay`
- Relay: `fix: close MCP authority and receipt boundaries`

---

### Task 7: Correct flagship adapters and publish owner manifests

**Files:**
- Create or update: owner manifests in Gather, Crucible, Index, Forum, Learn, Telos, and local-model
- Modify and test: the production adapter modules in Gather, Crucible, Index, Forum, and Learn
- Modify: Learn package exports, MCP version source, tool documentation, and tests
- Modify: Telos server manifest, tool catalog, freshness tests, README, USAGE, and current-state docs
- Create: language-neutral producer conformance vectors and thin Python/Node runners
- Modify: `harness/lanes.py`
- Modify: `tests/test_lanes.py`

**Interfaces:**
- Consumes: Proof Surface validation and the six-server/seven-lane vocabulary in the execution-contract spec.
- Produces: seven current owner manifests, real producer bundles, a six-server Telos contract, and a seven-lane Flywheel roster with no workaround.

- [ ] **Step 1: Write adapter regressions using actual producer outputs**

Crucible must map real `status` plus a canonical complete-row digest. Index must name `context-envelope` and preserve MATCH, DRIFT, and UNVERIFIABLE distinctly. Forum must map `gate_edited` and only observed event kinds. Gather and Learn must run their real adapters.

- [ ] **Step 2: Add portable cross-language conformance**

Python and Node producer runners write bundles into a temporary artifact root. A separately installed Proof Surface CLI validates those bytes. No sibling-source import or workspace-specific path is accepted as a release gate.

- [ ] **Step 3: Add one package-data owner manifest per lane**

Ground every command, MCP tool, module pointer, receipt kind, governance version, and health operation in a real path or executable. Source commit is injected by release generation and locked by hash, not hand-maintained as stale source text.

- [ ] **Step 4: Make Learn and Telos exact**

Document all 15 Learn tools, derive MCP version from package version, export the interop subpath, and supply a supported MCP launch. Add Learn to Telos so it names six flagship MCP servers. Remove `streamable-http` unless a real implementation and CI probe exist. Launch each server in freshness tests and fail on extra tools as well as missing tools.

- [ ] **Step 5: Harden Flywheel lane health**

The Flywheel roster names seven lanes: six flagship servers plus local-model. A process without status/doctor is `declared` or `stale`, never `live`.

- [ ] **Step 6: Run full suites and commit separately per owner repository**

Use narrow component-specific commits. Prepare new versions and release notes but do not publish packages or create registry releases.

---

### Task 8: Load, lock, validate, and probe the ten Plexus components

**Files:**
- Create: `public/plexus/plexus.interop.json`
- Modify: `public/plexus/src/plexus/manifest.py`
- Modify: `public/plexus/src/plexus/registry.py`
- Modify: `public/plexus/src/plexus/mesh.py`
- Modify: `public/plexus/src/plexus/run.py`
- Create: `public/plexus/src/plexus/probe.py`
- Create: `public/plexus/src/plexus/manifest_lock.py`
- Create: `public/plexus/scripts/build_manifest_lock.py`
- Modify: `public/plexus/src/plexus/cli.py`
- Modify: `public/plexus/src/plexus/mcp.py`
- Create: `public/plexus/tests/test_plexus_roster.py`
- Create: `public/plexus/tests/test_plexus_probe.py`
- Modify: `public/plexus/tests/test_plexus_manifests.py`

**Interfaces:**
- Consumes: seven lane manifests from Task 7, the exact committed Mneme and Relay manifest hashes from Task 6, and the Plexus-owned manifest.
- Produces: an installed-package-safe ten-component lock and `plexus.probe-receipt/1` for every component, including Plexus self-probe.

- [ ] **Step 1: Write exact-roster, schema, collision, and drift tests**

Reject duplicate JSON keys, non-object roots, unknown fields, unsupported versions, missing members, collisions, and hash drift. The exact components are Gather, Crucible, Index, Forum, Learn, Telos, local-model, Mneme, Relay, and Plexus.

- [ ] **Step 2: Implement portable discovery and a generated lock**

Use explicit configured paths, Python entry points, then the packaged aggregate lock. The build script imports Node and Python owner manifests into a temporary aggregate, records source/bundled hashes, and CI fails if regeneration differs. Runtime never assumes a workspace root.

- [ ] **Step 3: Fail closed on collisions and unsafe commands**

Structured plans store argv arrays. Non-executing shell rendering quotes every token. Unknown owners, collisions, and incompatible capability versions block routing.

- [ ] **Step 4: Implement receipt-backed probe and self-probe**

Emit manifest hash, argv profile, tool count, required health tool, status, duration, failure code, and `does_not_prove`. Missing health means declared/stale. Plexus probes its own status/doctor using the same contract.

- [ ] **Step 5: Run the full Plexus suite and portable package smoke**

Build wheel/sdist, install them into a clean temporary environment, validate the locked roster, and run `plexus probe --all --json` without a source checkout.

- [ ] **Step 6: Commit**

Commit message: `feat: probe a locked owner-manifest roster`

---

### Task 9: Implement the cross-harness executor and current endpoint evidence

**Files:**
- Create: `harness/cross_harness_executor.py`
- Create: `harness/cross_harness_oracles.py`
- Create: `scripts/run_cross_harness_execution.py`
- Modify: `harness/adapter_runtime_matrix.py`
- Modify: `harness/cross_harness_manifest.py`
- Modify: `harness/source_mined_bench.py`
- Modify: `harness/cli_entry.py`
- Modify: `scripts/run_harness_cli.py`
- Modify: `scripts/run_harness_comparison_report.py`
- Modify: `scripts/run_closed_loop_outcome_report.py`
- Modify: `benchmarks/agentic-task-set-v1.json`
- Modify: `benchmarks/cross-harness-adapter-contract-v1.json`
- Create: `tests/test_cross_harness_executor.py`
- Create: `tests/test_cross_harness_oracles.py`
- Modify: `tests/test_adapter_runtime_matrix.py`
- Modify: `tests/test_cross_harness_manifest.py`
- Modify: `tests/test_benchmark_execution_matrix.py`

**Interfaces:**
- Consumes: existing 98-row cross-harness manifest, endpoint registry, task set, endpoint-gate receipt, and the exact adapter/oracle/output contract in the execution-contract spec.
- Produces: `execute_cross_harness_manifest()`, deterministic completion oracles, endpoint-gate-aware readiness, commit-pinned attempt receipts, a 24-row Spark orchestration pilot, and an 84-attempt full matrix when pilot acceptance passes. Task 0 owns command receipts.

- [ ] **Step 1: Write executor tests with dry, unavailable, success, timeout, malformed-action, and receipt-tamper fixtures**

Each attempt must preserve run/source commit, task and prompt hash, model/adapter, tool-policy hash, repetition, cache state, raw output hash, tool trace, deterministic completion oracle, secondary rubric, elapsed time, resource observation, token/cost or explicit null, failure class, receipt path, and recheck verdict. Add tests that both existing synthesizers consume the generated `comparison-input.json` and `closed-loop-seed.json`.

- [ ] **Step 2: Implement endpoint-gate ingestion**

`adapter_runtime_matrix` accepts a `harness.model-endpoint-gate/v1` artifact. It marks a local role ready only when model reference, backend, profile hash, and successful generation row match. Remove the hardcoded false.

- [ ] **Step 3: Add deterministic task oracles and portable task inputs**

Give pilot tasks versioned `oracle` objects and repository-relative required inputs. Oracles inspect raw output and artifact bytes, never provider self-scores. If a task lacks a deterministic checker, completion is UNVERIFIABLE and excluded from completion comparisons.

- [ ] **Step 4: Implement one executor over the existing manifest**

Do not create a new task or scorecard schema. Typed unavailable rows stay outside performance denominators. Resource/cost/cache evidence joins each attempt before aggregation.
`codex_harness` is one direct read-only ephemeral `codex exec`. `flywheel_harness` uses the same Codex CLI backend/model request as a proposer inside `RouterAgent` and `local_loop.run_agent`. Label the result an orchestration-stack comparison, not a pure harness-only ablation. Record randomness control as controlled, unsupported, or unknown.

- [ ] **Step 5: Add a current CLI command and help contract**

```text
harness cross-harness-execute --manifest artifacts/closeout/FW-2026-08-02-CLOSEOUT/pilot/cross-harness-manifest.json --artifact-root artifacts/closeout/FW-2026-08-02-CLOSEOUT/pilot --tasks agt-001,agt-003,agt-009,agt-010 --roles codex_harness,flywheel_harness --repetitions 3
```

- [ ] **Step 6: Run static gates and current 14B/32B endpoint gates**

Generate profiles and run the two released Ollama tags separately with resource snapshots, seed 7, max 64 tokens, and a 300-second timeout. Record exact tag digests. This authorizes bounded generation only, not weight publication.

- [ ] **Step 7: Run the 24-row Spark pilot**

Use tasks `agt-001`, `agt-003`, `agt-009`, and `agt-010`, two roles, three repetitions. Require identical prompt and tool-policy hashes, nonzero shared comparison keys, explicit cache state, recheckable receipts, and a completed deterministic oracle for every compared row. If Spark is unavailable in one role, emit a typed unavailable result and keep the full matrix blocked.

- [ ] **Step 8: Run the 84-attempt matrix only after pilot acceptance**

Roles are Codex harness, Flywheel harness, Claude Code, OpenCode, local 14B, and local 32B. Preserve unavailable rows without counting them as failures. Use four core tasks plus the two model-specific endpoint/resource tasks described in the audit.

- [ ] **Step 9: Commit**

Commit message: `feat: execute cross-harness benchmark manifests`

---

### Task 10: Build and receipt a fresh BuildLang verifier release

**Files:**
- Modify: `compiler/tests/cli.rs`
- Modify: `compiler/src/main.rs`
- Modify: `docs/MODEL-RECEIPT.md`
- Create: `scripts/write_release_receipt.ps1`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: fresh Flywheel model-boundary and tool-call receipts from Task 9.
- Produces: a current release `buildc` that verifies both receipt families, documents the three-kind chain, and emits a source/build/binary receipt.

- [ ] **Step 1: Write CLI integration failures before changing help or code**

Add tests that verify a valid Flywheel tool receipt, reject a tampered one, admit the tool receipt in a mixed chain, and assert `receipt verify --help` and `receipt chain --help` name scientific, model-boundary, and tool-call receipts.

- [ ] **Step 2: Implement the minimal CLI/help corrections**

Preserve all existing schemas and validation. Do not add endpoint profiles to BuildLang; endpoint/model routing remains a Flywheel boundary.

- [ ] **Step 3: Run the full Rust release gate**

Run Cargo fmt, full tests, release build, version, doctor, scientific corpus, self corpus, model golden receipt, tool golden receipt, and fresh Task 9 receipts.

- [ ] **Step 4: Emit and validate a release receipt**

Record source commit, binary SHA-256, OS/architecture, Rust version, exact build command, full suite counts, ignored count, corpus counts, and verifier probe outputs. CI uploads the receipt and binary as workflow artifacts; it does not publish a package.

- [ ] **Step 5: Commit**

Commit message: `feat: gate Flywheel receipts in release builds`

---

### Task 10A: Merge and verify the upstream code plane

**Files:**
- No product edits. Only PR metadata and the Task 0 acceptance artifact tree are written.

**Interfaces:**
- Consumes: reviewed and terminal-green Task 1 through Task 10 branches.
- Produces: verified live default SHAs for Proof Surface, Flywheel core and desktop, Mneme, Relay, the flagship owners, Plexus, local-model where changed, and BuildLang.

- [ ] **Step 1: Rebase or merge current defaults into each narrow branch without rewriting published history**

Resolve only task-owned conflicts. Rerun each full repository gate through the acceptance recorder and require an exact clean-tree receipt.

- [ ] **Step 2: Open dependency-ordered PRs and wait for exact-head CI**

Use expected base and head SHAs. Merge Proof Surface first, then Flywheel governance, Mneme and Relay, flagship owners, Plexus, benchmark/executor code, desktop, and BuildLang. Never merge a stale topic branch wholesale.

- [ ] **Step 3: Verify live defaults**

Fetch every merged default, record its remote SHA and CI artifact identity, and assert no workflow PR remains open. Task 11 must branch from these live defaults and consume their exact manifest/artifact hashes.

---

### Task 11: Build current executable and regenerate the evidence pack

**Files:**
- Modify: Flywheel package builder and doctor files only where Task 9 tests expose a gap
- Create: `scripts/check_platform_lane_drift.py`
- Create: `tests/test_platform_lane_drift.py`
- Create: `project-docs/records/WORKSPACE-CONTEXT-MAP-2026-08-02.md`
- Create: `project-docs/records/TOOL-INTEGRATION-REPORT-2026-08-02.md`
- Create: `project-docs/records/HARNESS-ARCHITECTURE-ENDPOINT-REPORT-2026-08-02.md`
- Create: `project-docs/records/BENCHMARK-METHODOLOGY-2026-08-02.md`
- Create: `project-docs/records/CODEX-FLYWHEEL-BENCHMARK-COMPARISON-2026-08-02.md`
- Create: `project-docs/records/LOCAL-MODEL-BENCHMARK-SUMMARY-2026-08-02.md`
- Create: `project-docs/records/MNEME-READINESS-REPORT-2026-08-02.md`
- Create: `project-docs/records/RELAY-READINESS-REPORT-2026-08-02.md`
- Create: `project-docs/records/PLEXUS-READINESS-REPORT-2026-08-02.md`
- Create: `project-docs/records/MODEL-NAMING-PUBLISHING-PLAN-14B-32B-2026-08-02.md`
- Create: `project-docs/records/EXPERIMENTAL-OUTCOME-2026-08-02.md`
- Create: `project-docs/records/OBJECTIVE-EVIDENCE-MATRIX-2026-08-02.md`
- Create: `project-docs/records/CAPABILITY-CATALOG-2026-08-02.md`
- Create: `project-docs/records/ROADMAP-STATUS-2026-08-02.md`
- Create: `project-docs/records/NEXT-RECURSIVE-IMPROVEMENT-LOOP-2026-08-02.md`
- Create: `project-docs/records/FW-2026-08-02-ARTIFACT-INDEX.json`

**Interfaces:**
- Consumes: Task 10A live default SHAs, one canonical acceptance artifact root, and the platform/lane ownership contract.
- Produces: current Flywheel-source-bound external-runtime and full-runtime packages plus all required final reports with raw paths, hashes, denominators, limitations, and next actions.

- [ ] **Step 1: Gate the canonical platform/lane boundary**

Classify every remaining shared Flywheel/local-model file as platform-owned, lane-owned, generated shared contract, or legacy duplicate. Fail package acceptance on an unclassified or drifting duplicate. Record the exact local-model manifest/profile hash consumed by Flywheel.

- [ ] **Step 2: Build from a clean, exact Flywheel source commit**

Build an `external-runtime` bundle and label its endpoint dependency. Then build the `full-runtime` bundle with the supported serving runtime included. Require package `source_commit` equality, `SHIP_READY`, executable hashes, isolated install, serve startup, one bounded generation, shutdown/cleanup, and ZIP hash. Packaging does not imply benchmark success.

- [ ] **Step 3: Promote raw evidence into one durable indexed root**

Copy historical artifacts without rewriting them; record original path, SHA-256, timestamp, classification, denominator, and `does_not_prove`. New run artifacts live under one run id and source commit.

- [ ] **Step 4: Generate all required reports from the artifact index**

Every report separates verified facts, inferred interpretation, unknowns, and blockers. A typed unavailable provider is reported as unavailable and excluded from performance rates.

- [ ] **Step 5: Reconcile 14B and 32B release state**

Generate one authoritative release-state manifest per model. Preserve the measured 14B paired result (141/164 base versus 136/164 CPT, delta -3.05 points, p=0.404) with its control/contamination limits. Preserve the 32B 52/52 restart-reproduction result with its narrow scope. No model publication occurs in this task.

- [ ] **Step 6: Run report and package gates, then commit**

Run claim, writing, public-instruction, secret, file, package-doctor, and report-schema gates.

Commit message: `docs: publish current engine evidence pack`

---

### Task 11A: Merge and verify the canonical evidence pack

Open the Task 11 Flywheel PR from a fresh branch based on the Task 10A live
default. Wait for exact-head CI, merge with expected-head protection, fetch the
new default, and record the live SHA plus package and artifact-index hashes.
Tasks 12 and 13 branch only after this checkpoint.

---

### Task 12: Complete public user, security, maintenance, and release documentation

**Files:**
- Modify each affected README, USAGE, CHANGELOG, examples, API/CLI/MCP reference, and package metadata in Flywheel, Proof Surface, Gather, Crucible, Index, Forum, Learn, Telos, Mneme, Relay, Plexus, and BuildLang.
- Create missing `SECURITY.md`, `SUPPORT.md`, `docs/configuration.md`, `docs/troubleshooting.md`, `docs/integrations.md`, and `docs/MAINTENANCE.md` where the corresponding audited gap exists.
- Modify release workflows, CODEOWNERS, and package-version sources only after actual code and artifact identity are stable. Workflows stay dry-run or manually withheld in this goal.

**Interfaces:**
- Consumes: exact live code, tests, package versions, manifest roster, and the Task 11A live evidence SHA.
- Produces: public docs that match CLI, MCP, HTTP, Python/Node/Rust, desktop, package, security, ownership, limitations, and release behavior.

- [ ] **Step 1: Write doc-contract tests before copy changes**

Add drift tests for package/version/MCP identity, tool counts, receipt-kind tables, owner-manifest roster, public links, forbidden local paths, em dashes, mojibake, placeholders, secret-shaped text, and unsupported claims.

- [ ] **Step 2: Update feature-first quickstarts and exact command references**

Every repository documents install, first successful command, configuration names without values, status/doctor, CLI/API/MCP surface, integrations, failure codes, troubleshooting, security boundary, known limitations, and release evidence.

- [ ] **Step 3: Add ownership and lifecycle contracts**

Name repository ownership, supported versions, maintenance expectations, compatibility window, deprecation path, retirement criteria, disclosure route, incident posture, data retention, and local/network/exec boundaries. Do not invent a private contact; use the verified repository security-advisory path where configured.

- [ ] **Step 4: Reconcile versions and releases**

Use new version proposals for changed products. Do not republish old bytes under old versions or enable Relay's collided `relay-agent` distribution name. Prepare packages, checksums, SBOMs, provenance, changelogs, and `READY_TO_RELEASE` records. Do not publish to PyPI, npm, Hugging Face, or another registry; do not trigger a production release workflow or create an uploading release. Record the withheld command and gate state without running it.

- [ ] **Step 5: Run full repo suites and public gates, then commit per repo**

Each repo commit includes code-facing docs and changelog together. No documentation-only claim may get ahead of the tested implementation.

---

### Task 13: Regenerate demos, decks, portfolio, and profile from verified sources

**Files:**
- Create: `PRODUCT.md` and `DESIGN.md` at the Flywheel root from the existing canon and product source, as required by the Impeccable setup flow
- Create: `project-docs/outreach/public-projection.schema.json`
- Create: `project-docs/outreach/public-projection.json`
- Create: `project-docs/scripts/build_public_projection.py`
- Create: `project-docs/tests/test_public_projection.py`
- Modify: `demos/README.md`, `demos/index.json`, `demos/scripts/*.json`
- Regenerate: `demos/*/player.html`, `demos/*/transcript.json`
- Create: a native governance demo script, player, and transcript
- Modify and regenerate: canonical public and audience-specific outreach deck sources/PDFs
- Replace: `flywheel-desktop/docs/deck/flywheel-telos-deck.html`
- Modify: portfolio Flywheel and demonstrations pages
- Modify: profile README last
- Create: derivative generation manifests with source commit and SHA-256

**Interfaces:**
- Consumes: live default SHAs, the Task 11A artifact index, and the exact allowlist/generation contract in the execution-contract spec. Each derivative branch/worktree is created fresh after Task 11A; current dirty, diverged, or behind checkouts are never reused as merge sources.
- Produces: scrubbed, generated, hashed, visually inspected public artifacts. The generator cannot read or write private prospect/client roots.

- [ ] **Step 1: Finish the Impeccable project context before visual edits**

Use the existing design and voice canon, desktop product docs, tokens, site CSS, and brand assets to create the root product brief. Default register is product; marketing/deck tasks explicitly use the brand register. Capture the two-family, aperture, verdict-color, restraint, accessibility, and anti-template rules in DESIGN.md.

- [ ] **Step 2: Add the projection schema, generator, and privacy tests before regenerating artifacts**

The allowlist names every input, output, renderer, and required check. The generator uses argv arrays, refuses sources outside configured public roots, refuses forbidden roots, and emits input/output SHA-256 values, product commit, command hashes, tool versions, and check results. Reject absolute paths, private/prospect names, credentials, em dashes, mojibake, more than two type families, stale source commit, and missing generated-from records. Preserve raw receipts and generate scrubbed projections.

- [ ] **Step 3: Regenerate all demos from source JSON**

Record the release commit, environment statement, receipt hash, and limitations. Add native governance, tamper, organization, and open-source flows. Use repository-relative commands.

- [ ] **Step 4: Rebuild four separate deck narratives**

Maintain public product, investor/commercial, technical talk, and enterprise evaluation/security variants. Do not reuse the no-slide event package as a general deck. Retire stale derivative PDFs and keep philosophical material separate.

- [ ] **Step 5: Update portfolio only after Flywheel is live**

Remove categorical exclusivity. Link to live release evidence, demos, checksums, and limitations. Run link and deploy gates.

- [ ] **Step 6: Update profile last**

Describe verified maturity, not the stale `0.1.0 source prototype` state and not unsupported enterprise readiness.

- [ ] **Step 7: Render and inspect every visual surface**

Sites: 1440x900, 1024x768, 390x844, 320x568, 200% zoom, keyboard-only, reduced motion. Decks: 1920x1080 and 1366x768. PDFs: 100%, 150%, 200%. Store an inspection receipt per layout class with renderer, viewport/zoom, artifact hash, clipping, overflow, contrast, focus, reduced-motion, inspector, and timestamp. Reject clipping, hidden overflow, unintended scrollbars, contrast below 4.5:1 for body text, missing focus, and unhandled reduced motion.

- [ ] **Step 8: Commit generated sources and verified derivatives**

Commit message per repo: `docs: regenerate verified public release surfaces`

---

### Task 14: Public-derivative integration, live verification, and recursive closeout

**Files:**
- Modify: design status, objective matrix, capability catalog, roadmap, experimental outcome, and next-loop report only with actual final state
- Create: `project-docs/records/FW-2026-08-02-COMPLETION-CHECKLIST.md`

**Interfaces:**
- Consumes: Task 10A and Task 11A live defaults plus every documentation and derivative task commit, test receipt, artifact hash, PR head, CI result, and live default SHA.
- Produces: no open workflow PR, no workflow-owned dirty diff, verified live defaults, and a final requirement-to-evidence matrix.

- [ ] **Step 1: Run task-level review after every implementation task**

Use a fresh reviewer to compare code with the task text, then a quality reviewer for correctness, security, performance, maintainability, tests, and public claims. Fix findings before starting the next task.

- [ ] **Step 2: Run one final cross-repository review**

Review trust boundaries, schema/version compatibility, canonical roster, generated-doc provenance, public privacy allowlist, benchmark denominators, model release gates, and branch histories.

- [ ] **Step 3: Run clean-worktree full gates through the acceptance recorder**

Run all repo-local suites, Flutter analyze/test/build, Cargo fmt/test/build, both package classes, doctor/status, interop conformance, public-surface scans, secret scans, writing scans, link checks, browser renders, and package/executable smokes. `scripts/run_acceptance_command.py` records argv, repository-relative cwd, start/end/duration, exit code, stdout/stderr hashes, source/HEAD identity, environment-variable names without values, and `does_not_prove` under the durable workflow artifact root. A clean-tree assertion must fail on unreviewed workflow changes.

- [ ] **Step 4: Push remaining documentation and derivative branches and open PRs**

Use GitHub connector PR creation. Verify each base and head SHA before opening. Never force-push.

- [ ] **Step 5: Wait for exact-head terminal CI**

Watch checks to completion. Diagnose and repair failures on the same task branch. Do not merge an unchecked Relay probe head or any stale branch wholesale.

- [ ] **Step 6: Merge remaining public surfaces with expected-head protection and verify live defaults**

Merge dependency order: repository user docs, public projections and demos, decks, portfolio, then profile. Upstream code and the evidence pack are already live through Tasks 10A and 11A. Fetch each default and verify remote SHA, proposed version metadata, CI artifacts, GitHub Pages/site response, checksum, and link target. Registry publication, production release workflows, and model uploads remain withheld.

- [ ] **Step 7: Close the durable loop**

Update the spec status, completion checklist, objective matrix, capability catalog, roadmap, experimental outcome, and next recursive loop from the live receipts. Mark unavailable external providers and unpublished models honestly. No required repo may have an open workflow PR or unreviewed workflow-owned change.

- [ ] **Step 8: Mark the active Codex goal complete**

Only after the objective is actually achieved, call the goal completion mechanism and report final usage returned by it.

---

## Self-review result

- R1 recovery and mapping: completed before plan execution and preserved in the audit reports and Task 9 context map.
- R2 governance: Tasks 1 through 5.
- R3 Mneme, Relay, Plexus, and cross-lane interop: Tasks 6 through 8.
- R4 harnesses, endpoints, executable, and benchmarks: Tasks 9 through 11.
- R5 required reports, model plan, catalog, roadmap, and next loop: Task 11 and Task 14.
- R6 public user documentation: Task 12.
- R7 demos, outreach, decks, portfolio, and profile: Task 13.
- R8 review, CI, remotes, and live closure: Task 14.
- Placeholder scan: no deferred implementation placeholder is present. Conditional outcomes are explicit fail-closed release gates.
- Type consistency: trusted authorization, control receipt, owner manifest, probe receipt, and cross-harness executor names match their producing and consuming tasks.
