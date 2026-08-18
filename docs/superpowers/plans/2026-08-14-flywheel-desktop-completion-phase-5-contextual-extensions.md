# Flywheel Desktop Completion Phase 5 Contextual Extensions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Incident Compiler, Frontier Claims, and Domain Packs only as truth-preserving contextual Journey extensions whose exact backend contracts have been accepted.

**Architecture:** A fail-closed capability document binds each extension to accepted Journey/packet schemas, operations, containment, and limits; the server enforces that document again on every route. Incident compilation is a deterministic proposal, Frontier preserves independent source axes, and packs separate data admission from executable authority. Flutter renders only advertised states inside existing Journey lenses.

**Tech Stack:** Python 3.11+ standard library, Phase 1 Journey CAS/grants, Phase 3 truth states, Flutter 3.44.6, Dart 3.6+, pytest, Flutter test.

**Spec:** `docs/superpowers/specs/2026-08-13-flywheel-desktop-completion-design.md`

## Global Constraints

- No learned model on the accept path.
- No receipt, no accept; denominators and `does_not_prove` are mandatory.
- No later phase may become an implementation prerequisite for an earlier phase.
- Python containment is an independent capability gate and does not reorder these phases.
- Flutter must not derive evidence truth or treat receipt presence as verification.
- Write, exec, plugin, and network access default to denied; secrets use opaque credential handles and never enter Journey events.
- Telemetry is off by default.
- Missing containment must retain the accepted EXECUTION_CONTAINMENT_UNAVAILABLE null and must never fall back to ordinary execution or claim sandboxing.
- No provider, endpoint, model, or network dispatch from evidence routes
- New Python and Dart files stay at or below 300 physical lines.
- The verifier path keeps zero third-party runtime dependencies.
- Existing public paths, secrets, private artifacts, and historical receipts never enter fixtures.
- Each implementation task uses RED, GREEN, focused regression, gates, review, then a narrow commit.
- No public release is permitted before all six phases pass, even if it uses the non-executing profile.

---

## Per-task evidence envelope

For every numbered task, record `git rev-parse HEAD`, `git rev-parse HEAD^{tree}`, branch/worktree identity, and clean task-boundary status before RED. New production files stay at or below 300 physical lines, grandfathered over-limit files shrink, new/modified production functions stay at or below 60 lines, and test functions stay at or below 80 lines. Before handoff, record exact RED/GREEN/verification commands and exits, test and mutation denominators, touched-file SHA-256 values, measured file/function ceilings, limitations, `does_not_prove`, the task commit as rollback point, and receiving-owner acceptance. A missing field blocks the next task; reject with `git revert --no-edit HEAD` and rerun phase-to-date gates.

### Task P5-T1: Freeze fail-closed extension capabilities

**Files:**
- Create: `harness/evidence_extension_contracts.py`
- Test: `tests/test_evidence_extension_contracts.py`

**Interfaces:**
- Consumes: accepted Phase 1 Journey schema/head, Phase 3 grant schema, packet schema, and independently accepted Incident, Frontier, pack, and containment receipts.
- Produces: `capability_document(*, journey: dict, incident_contract: dict | None, frontier_contract: dict | None, pack_contracts: list[dict], containment: dict) -> dict` with schema `flywheel.evidence-capabilities/v1`; each row is exactly `{id,schema,state,operations,journey_schema,packet_schema,containment_class,limits,reason,contract_sha256,acceptance_receipt_sha256}` and state is `read_only|data_only|execution_locked|available`.

- [ ] **Write RED tests.** Require canonical JSON and hashes; reject missing/unknown schemas, unaccepted receipts, head/schema drift, duplicate IDs, unknown operations/states, executable operations without accepted process containment, and rows whose limits are absent. Prove an advertisement grants no authority and absent/unknown rows produce no capability.
- [ ] **Run RED.** From the repository root run `python -m pytest tests/test_evidence_extension_contracts.py -q`; expect import failure because the capability contract does not exist.
- [ ] **Implement minimal GREEN.** Validate exact fields/enums with standard-library code, derive rows only from accepted receipts, retain `execution_locked` when data is admissible but execution containment is not, and expose a pure `authorize_capability(document, *, capability_id, operation, journey_schema, packet_schema, contract_sha256) -> bool` that never consumes a grant.
- [ ] **Verify.** Run the RED command and `python scripts/check_file_gate.py`; expect PASS, zero provider/network dispatch, and `harness/evidence_extension_contracts.py` at or below 300 lines.
- [ ] **Commit scope.** Run `git add harness/evidence_extension_contracts.py tests/test_evidence_extension_contracts.py && git commit -m "feat: define contextual evidence capabilities"`.

### Task P5-T2: Compile deterministic Incident proposals

**Files:**
- Create: `harness/incident_case.py`
- Create: `harness/incident_proposal.py`
- Test: `tests/test_incident_case.py`
- Test: `tests/test_incident_proposal.py`

**Interfaces:**
- Consumes: capability `incident-compiler` whose exact schema is `flywheel.incident-case/v1` and state is `read_only|available`, an authorized owner, active `journey_ref`, accepted `event_head_sha256`, and public-safe admitted facts/claims.
- Produces: `new_incident_case(*, case_id: str, journey_ref: str, event_head_sha256: str, source_refs: list[dict], failure: dict, created_at: str) -> dict` using `flywheel.incident-case/v1`; and `compile_incident_proposal(*, case: dict, projection: dict, capability: dict) -> dict` using `flywheel.incident-proposed-graph/v1` fields `{proposal_id,state,journey_ref,basis_event_head_sha256,capability_sha256,source_fact_ids,claims,checks,edges,review_requirements,limitations,does_not_prove,graph_sha256}`, with `state == "proposed"`.

- [ ] **Write RED tests.** Freeze deterministic ordering/hash, referenced-fact membership, acyclic edges, sanitized metadata, explicit review requirements and `does_not_prove`; reject raw paths/secrets, invented facts, accepted/PASS/receipt/execution/command/code fields, stale heads, and any model/oracle/subprocess/plugin/network/store call.
- [ ] **Run RED.** Run `python -m pytest tests/test_incident_case.py tests/test_incident_proposal.py -q`; expect import failure because the case schema and pure compiler do not exist.
- [ ] **Implement minimal GREEN.** Compile only the supplied admitted projection, strip private metadata through Phase 1 public helpers, and return a proposal without appending, self-accepting, executing, or writing a lesson. Later admission must be a separately granted Phase 1 CAS command bound to proposal and graph hashes.
- [ ] **Verify.** Run the RED command plus `python -m pytest tests/test_evidence_extension_contracts.py tests/test_evidence_route.py -q`; expect PASS and byte-identical proposals for identical inputs.
- [ ] **Commit scope.** Run `git add harness/incident_case.py harness/incident_proposal.py tests/test_incident_case.py tests/test_incident_proposal.py && git commit -m "feat: compile incident proposals"`.

### Task P5-T3: Preserve Frontier axes without a composite

**Files:**
- Create: `harness/frontier_claim.py`
- Create: `harness/frontier_claim_projection.py`
- Test: `tests/test_frontier_claim.py`
- Test: `tests/test_frontier_claim_projection.py`

**Interfaces:**
- Consumes: capability `frontier-claims`, active Journey/head, and the existing independent fields `review_state,verdict,evidence_kind,community_state,novelty_state,fidelity_state,freshness_state,reproduction_state`.
- Produces: `new_frontier_claim(*, claim_id: str, journey_ref: str, source: dict, proposition: dict, created_at: str) -> dict` using `flywheel.frontier-claim/v1`; `project_frontier_axes(*, claim: dict, journey_ref: str, event_head_sha256: str) -> dict` using `flywheel.frontier-axes/v1`, four separately hashed objects `identification`, `verification`, `policy`, and `value`, plus raw-preserving nulls; and `append_frontier_axis_event(*, owner_ref: str, journey_ref: str, expected_event_head: str, client_request_id: str, grant_ref: str, claim_id: str, axis: str, patch: dict) -> dict` changing exactly one server-owned axis through CAS.

- [ ] **Write RED tests.** Prove the lossless mapping: identification owns source/proposition/authorship; verification owns verdict/evidence kind/fidelity/freshness/reproduction; policy owns review/community/admission; value owns novelty/importance. Require every legacy value and null to round-trip; reject composite scores, cross-axis mutation, stale head/grant, inferred novelty, and translating `NOT_FOUND_IN_CORPUS` into novel.
- [ ] **Run RED.** Run `python -m pytest tests/test_frontier_claim.py tests/test_frontier_claim_projection.py tests/test_frontier.py -q`; expect missing-module failure before implementation.
- [ ] **Implement minimal GREEN.** Use explicit allowlists and independent canonical hashes; preserve unknown raw values as invalid-response facts instead of coercing them. The append helper validates capability then delegates one typed CAS command and never retrieves sources or executes a checker.
- [ ] **Verify.** Run the RED command and `python scripts/check_file_gate.py`; expect PASS with no aggregate trust field and no regression in existing `harness/frontier.py` behavior.
- [ ] **Commit scope.** Run `git add harness/frontier_claim.py harness/frontier_claim_projection.py tests/test_frontier_claim.py tests/test_frontier_claim_projection.py && git commit -m "feat: project independent frontier axes"`.

### Task P5-T4: Admit versioned Domain Pack contracts

**Files:**
- Create: `harness/domain_pack.py`
- Create: `harness/domain_pack_qa.py`
- Test: `tests/test_domain_pack.py`
- Test: `tests/test_domain_pack_qa.py`

**Interfaces:**
- Consumes: public-safe pack bytes, fixture manifest, license/provenance, Phase 3 grant for admission, and containment receipt when execution is declared.
- Produces: `verify_pack_manifest(manifest: dict, *, fixtures_root: Path) -> dict`, `run_pack_qa(manifest: dict, fixtures: list[dict]) -> dict`, and `flywheel.domain-pack/v1` fields `{pack_id,version,pack_sha256,domain_id,claim_types,journey_schema,packet_schema,oracle_bindings,fixtures,capabilities,containment_class,license,resource_limits,public_metadata_policy,limitations,does_not_prove,owner,review_due_at,retirement}`.

- [ ] **Write RED tests.** Require correct/incorrect/ambiguous/malformed/stale/contested/unsupported fixtures; exact oracle id/version/source hash/evidence kind/determinism; SPDX/ref/hash/redistribution; numeric CPU/memory/process/output/time limits; QA denominator, detected/escaped mutations, platform skips, resources, and `does_not_prove`. Reject false accepts, dynamic imports, plugin discovery, commands, missing license/owner/limits, secret or host paths, and executable/network/write/secrets capabilities unless accepted containment and exact grants exist.
- [ ] **Run RED.** Run `python -m pytest tests/test_domain_pack.py tests/test_domain_pack_qa.py -q`; expect import failures because admitted pack contracts are absent.
- [ ] **Implement minimal GREEN.** Treat `data_only` packs as manifests plus admitted data, keep executable packs `execution_locked` without accepted process containment, and return QA schema `flywheel.domain-pack-qa/v1`; capability advertisement and registration never execute pack code.
- [ ] **Verify.** Run the RED command plus `python -m pytest tests/test_oracle_registry.py -q`; expect PASS, zero escaped planted false accepts, and standard-library-only validation.
- [ ] **Commit scope.** Run `git add harness/domain_pack.py harness/domain_pack_qa.py tests/test_domain_pack.py tests/test_domain_pack_qa.py && git commit -m "feat: admit versioned domain packs"`.

### Task P5-T5: Enforce routes and render contextual Flutter extensions

**Files:**
- Create: `harness/evidence_extension_route.py`
- Create: `desktop/lib/models/evidence_extensions.dart`
- Create: `desktop/lib/client/evidence_extensions_client.dart`
- Create: `desktop/lib/widgets/incident_extension.dart`
- Create: `desktop/lib/widgets/frontier_claim_extension.dart`
- Create: `desktop/lib/widgets/domain_pack_extension.dart`
- Modify: `harness/gateway.py`
- Modify: `desktop/lib/client/gateway_client.dart`
- Modify: `desktop/lib/widgets/journey_lenses.dart`
- Test: `tests/test_evidence_extension_route.py`
- Test: `tests/test_gateway.py`
- Test: `desktop/test/evidence_extensions_test.dart`

**Interfaces:**
- Consumes: Tasks P5-T1 through P5-T4, Phase 1 owner/CAS/grant service, and Phase 2 `JourneyProjection`/lens host.
- Produces: authenticated routes `GET /api/journeys/capabilities`, `POST /api/journeys/incident-propose`, `POST /api/journeys/frontier-project`, `POST /api/journeys/frontier-axis`, `POST /api/journeys/domain-pack-project`; Dart `EvidenceCapability`, `IncidentProposal`, `FrontierAxes`, `DomainPackProjection`, and `EvidenceExtensionsClient` exact decoders.

- [ ] **Write RED tests.** Require auth, owner isolation, exact Journey/head/schema/contract hash and grant where mutating; absent/unknown/stale capability denies before dispatch. Widget tests require no empty surface for absent/unknown rows; Incident only in an active Journey, Frontier only in Diagnose/Verify, pack state visible contextually, execution locked text explicit, no top-level nav route, and no verdict inference or composite.
- [ ] **Run RED.** Run `python -m pytest tests/test_evidence_extension_route.py tests/test_gateway.py -q` and from `desktop/` run `flutter test test/evidence_extensions_test.dart`; expect missing routes/types/widgets.
- [ ] **Implement minimal GREEN.** Keep `gateway.py` and the oversized Dart client as thin dispatch/barrel edits; route all validation through the new modules. Decode unknown rows as hidden, render accepted read/data-only states without enabling execution, and invalidate any approval when head, operation, arguments, or contract hash changes.
- [ ] **Verify.** Run both RED commands and `flutter analyze`; expect PASS with no thirtieth-plus-one navigation destination and no provider/model/network call.
- [ ] **Commit scope.** Run `git add harness/evidence_extension_route.py harness/gateway.py desktop/lib/models/evidence_extensions.dart desktop/lib/client/gateway_client.dart desktop/lib/client/evidence_extensions_client.dart desktop/lib/widgets/incident_extension.dart desktop/lib/widgets/frontier_claim_extension.dart desktop/lib/widgets/domain_pack_extension.dart desktop/lib/widgets/journey_lenses.dart tests/test_evidence_extension_route.py tests/test_gateway.py desktop/test/evidence_extensions_test.dart && git commit -m "feat: add capability-gated journey extensions"`.

### Task P5-T6: Issue the contextual-extension acceptance receipt

**Files:**
- Create: `tests/test_contextual_extensions_acceptance.py`
- Create: `desktop/test/contextual_extensions_acceptance_test.dart`
- Create: `project-docs/records/2026-08-14-desktop-phase-5-contextual-extensions.md`

**Interfaces:**
- Consumes: accepted outputs and commit/tree hashes from P5-T1 through P5-T5.
- Produces: acceptance record `flywheel.desktop-phase-acceptance/v1` with phase `5`, source/workspace binding, commands/exits, fixture and mutation denominators, capability/contract/receipt hashes, file/function ceilings, limitations, rollback commit, receiving owner, and `does_not_prove`.

- [ ] **Write RED acceptance tests.** Cover absent/unknown/stale capabilities, deterministic Incident proposal with no acceptance or execution, all Frontier values/nulls independently preserved, data-only pack admission, executable pack lock, exact-grant mutation, and no new destination/provider/model/network dispatch.
- [ ] **Run RED.** Run `python -m pytest tests/test_contextual_extensions_acceptance.py -q` and from `desktop/` run `flutter test test/contextual_extensions_acceptance_test.dart`; expect failure until all acceptance evidence is assembled.
- [ ] **Implement minimal GREEN.** Add only public synthetic fixtures and generate the record from actual command results and SHA-256 inputs; a missing denominator, contract acceptance, containment fact, hash, reviewer, or `does_not_prove` is a blocking null, never an inferred PASS.
- [ ] **Verify.** Run `python -m pytest tests/test_contextual_extensions_acceptance.py -q`, `python -m pytest tests/ -q`, and `python scripts/check_file_gate.py`; then from `desktop/` run `flutter analyze` and `flutter test`. Expect all PASS with no live service/provider use.
- [ ] **Commit scope.** Run `git add tests/test_contextual_extensions_acceptance.py desktop/test/contextual_extensions_acceptance_test.dart project-docs/records/2026-08-14-desktop-phase-5-contextual-extensions.md && git commit -m "test: accept contextual journey extensions"`.

**Phase gate:** Phase 6 may start only after a reviewer accepts the Phase 5 record against its bound source tree. Roll back a failed task with `git revert --no-edit HEAD`; the receiving owner re-runs the task's focused commands and records acceptance before the next task starts.
