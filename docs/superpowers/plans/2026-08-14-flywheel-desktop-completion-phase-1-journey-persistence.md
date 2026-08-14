# Flywheel Desktop Completion Phase 1 Journey Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the accepted file-scoped Evidence Journey transport into a per-user, server-owned, durably persisted Journey with CAS, idempotency, recovery, continuous check events, and truthful cancellation.

**Architecture:** Keep commit `665ef5e` and every v1 validator/null intact, then add v2 immutable events, projections, locks, and authoritative heads behind new service and route modules. The filesystem store acknowledges only after durable event and head commits; injected runners exercise lifecycle behavior without invoking providers, networks, or uncontained Python.

**Tech Stack:** Python 3.11+ standard library, canonical JSON/SHA-256, `msvcrt`/`fcntl` file locking, existing evidence packet/oracle interfaces, pytest.

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

### Task P1-T1: Freeze v1 and define the v2 event projection

**Files:**
- Create: `harness/journey_types.py`
- Create: `harness/journey_projection.py`
- Test: `tests/test_journey_projection_v2.py`
- Test: `tests/test_evidence_journey.py`

**Interfaces:**
- Consumes: accepted v1 `new_journey`, `project_journey`, `verify_journey`, and canonical helpers from `harness.evidence_json` without changing their bytes or schemas.
- Produces: `new_genesis(*, journey_ref: str, legacy_label: str | None, goal: str, intake: dict, actor_id: str, occurred_at: str) -> dict`, `reduce_events(events: list[dict]) -> dict`, and `project_lens(projection: dict, lens: str) -> dict` for `flywheel.evidence-journey-event/v2` and `flywheel.evidence-journey-projection/v2`.

- [ ] **Write RED tests.** Assert an event has exactly `schema,journey_ref,sequence,event_type,occurred_at,actor_id,request_sha256,payload,prior_event_sha256,event_sha256`; stage events follow `intake|decomposed|preflight|running|concluded|exported`, operational events do not advance stage, and all three lenses preserve identical `journey_ref,event_head_sha256,fact_ids,claim_ids,checks,verdicts,missing_evidence,stage,conclusion`.
- [ ] **Run RED.** Run `python -m pytest tests/test_journey_projection_v2.py tests/test_evidence_journey.py -q`; expect collection to fail with `ModuleNotFoundError: No module named 'harness.journey_projection'` while the existing v1 file remains green when run alone.
- [ ] **Implement minimal GREEN.** Validate `^jrn_[0-9a-f]{32}$`, exact enums, sequence continuity, canonical event hashes, immutable fact/claim definitions, four verdicts, and receipt states `missing|present_unchecked|MATCH|DRIFT|TAMPERED|UNVERIFIABLE`; lenses may reorder only presentation sections. The accepted v1 `/api/evidence/*` `journey_ref` remains a safe relative artifact ref, while only v2 `/api/journeys/*` interprets `journey_ref` as opaque; no value crosses those selectors implicitly.
- [ ] **Verify.** Run `python -m pytest tests/test_journey_projection_v2.py tests/test_evidence_journey.py -q`; expect PASS, then `python scripts/check_file_gate.py`; expect no new or grown violation.
- [ ] **Commit scope.** Run `git add harness/journey_types.py harness/journey_projection.py tests/test_journey_projection_v2.py && git commit -m "feat: define durable journey projection"`.

### Task P1-T2: Add exclusive locking and acknowledge-after-durability storage

**Files:**
- Create: `harness/journey_lock.py`
- Create: `harness/journey_store.py`
- Test: `tests/test_journey_store.py`
- Test: `tests/test_journey_store_crash.py`

**Interfaces:**
- Consumes: P1-T1 event validation and projection functions.
- Produces: `MutationCommand(owner_ref: str, journey_ref: str, expected_event_head: str | None, client_request_id: str, operation: str, body: dict)`, `MutationAck(journey_ref: str, event_head_sha256: str, event_sha256: str, projection_sha256: str, idempotent_replay: bool)`, and `JourneyStore.create/load/list/append` methods. `GENESIS_HEAD` is exactly `None`; every post-genesis mutation requires a 64-hex head.

- [ ] **Write RED tests.** With `tmp_path`, race two appends at one head, retry one `client_request_id` with same and changed bodies, inject failure before event fsync/projection replace/head replace/directory fsync, and assert zero acknowledged loss, duplicate logical event, or silent overwrite; expect `HEAD_CONFLICT`, `IDEMPOTENCY_MISMATCH`, `STORE_BUSY`, or `STORE_COMMIT_FAILED` with no host detail.
- [ ] **Run RED.** Run `python -m pytest tests/test_journey_store.py tests/test_journey_store_crash.py -q`; expect import failure for `harness.journey_store`.
- [ ] **Implement minimal GREEN.** Store under `state_root / "journeys" / "v2" / "owners" / owner_ref`, use `ExclusiveJourneyLock.acquire(lock_path: Path, timeout_s: float = 2.0)`, reread the head under lock, bind `canonical_sha256({owner_ref,journey_ref,expected_event_head,operation,body})` to the request id while excluding only `grant_ref` and the idempotency key, create the immutable event with exclusive creation and fsync, atomically replace/fsync projection then `flywheel.evidence-journey-head/v2`, and fsync containing directories before returning `MutationAck`.
- [ ] **Verify.** Add a 20-case parametrized concurrency test, then run `python -m pytest tests/test_journey_store.py tests/test_journey_store_crash.py -q`; expect all cases PASS, no duplicate sequence, and one winning CAS per head without an undeclared pytest plugin.
- [ ] **Commit scope.** Run `git add harness/journey_lock.py harness/journey_store.py tests/test_journey_store.py tests/test_journey_store_crash.py && git commit -m "feat: persist journey heads atomically"`.

### Task P1-T3: Add owner binding, one-use grants, and the Journey service

**Files:**
- Create: `harness/operation_grants.py`
- Create: `harness/journey_service.py`
- Test: `tests/test_operation_grants.py`
- Test: `tests/test_journey_service.py`

**Interfaces:**
- Consumes: `JourneyStore`, `MutationCommand`, and `MutationAck` from P1-T2; stable `owner_ref` is loaded after gateway authentication and never read from request JSON or derived from the rotatable bearer token.
- Produces: `load_or_create_owner_ref(home: Path) -> str`, `GrantRequest(owner_ref, journey_ref: str | None, expected_event_head: str | None, operation_sha256, tool, arguments_sha256, scopes, data_refs, expires_at, nonce)`, `GrantStore.issue(request, *, approved: bool) -> dict`, `GrantStore.consume(grant_ref, request, *, now: str) -> dict`, and `JourneyService.create/list/resume/append`.

- [ ] **Write RED tests.** Assert grants use the server clock, a 120-second default and 300-second maximum TTL, are one-use, and are exact across owner/Journey/head/operation/tool/arguments/scopes/data refs/expiry/nonce. Only `tool == "journey.create"` may bind both Journey and head to null before the server generates `jrn_` plus 32 lowercase hex; every other grant requires the exact opaque Journey/head. Bearer-token rotation preserves owner access, ownership cannot be enumerated, list is per owner, and a legacy display label never selects storage.
- [ ] **Run RED.** Run `python -m pytest tests/test_operation_grants.py tests/test_journey_service.py -q`; expect imports to fail for both new modules.
- [ ] **Implement minimal GREEN.** Persist `owner.ref` with owner-only ACL handling; store grant records under `state_root / "grants" / owner_ref`; and protect issue/consume with `ExclusiveJourneyLock`, atomic replace, file flush, and directory fsync. Store only grant digests/consumption state, return an idempotent stored result before grant consumption, otherwise durably burn the exact grant before mutation, and return `PERMISSION_REQUIRED|PERMISSION_DENIED|APPROVAL_EXPIRED` through fixed messages. A crash after burn but before mutation requires a new approval and never widens authority.
- [ ] **Verify.** Run `python -m pytest tests/test_operation_grants.py tests/test_journey_service.py tests/test_gateway_auth.py -q`; expect PASS and no token, credential, raw environment, or host path in stored bytes.
- [ ] **Commit scope.** Run `git add harness/operation_grants.py harness/journey_service.py tests/test_operation_grants.py tests/test_journey_service.py && git commit -m "feat: bind journey mutations to exact grants"`.

### Task P1-T4: Recover stores and import v1 without invented custody

**Files:**
- Create: `harness/journey_migration.py`
- Create: `harness/journey_recovery.py`
- Test: `tests/test_journey_migration.py`
- Test: `tests/test_journey_recovery.py`

**Interfaces:**
- Consumes: authoritative head/event/request layout from P1-T2 and `JourneyService` ownership from P1-T3.
- Produces: `import_v1_snapshot(snapshot: dict, *, actor_id: str, store: JourneyStore, created_at: str) -> MutationAck`, `migrate_store(store_root: Path, *, target_version: int) -> dict`, `migrate_packet(packet_root: Path, *, target_schema: str, out_root: Path) -> dict`, and `recover_store(store_root: Path, *, now: str) -> dict` with `completed,quarantined,indexes_rebuilt,starts_closed,read_only,diagnostic_refs`.

- [ ] **Write RED tests.** Cover v1 byte preservation and digest citation through an explicit safe `snapshot_ref`, v2 genesis `custody_before_import:false`, server-assigned import time with legacy timestamps retained only as snapshot facts, and chats/workspaces/settings/receipts remaining legacy refs unless explicitly imported. Require packet migration to write a derived packet with source digest while preserving original bytes; cover backup-first journaled idempotent migration, orphan event completion/quarantine, index rebuild, last-head preservation, failed rollback, and unsupported newer schema opening read-only with mutation `VERSION_MISMATCH`.
- [ ] **Run RED.** Run `python -m pytest tests/test_journey_migration.py tests/test_journey_recovery.py -q`; expect import failure for the migration and recovery modules.
- [ ] **Implement minimal GREEN.** Never rewrite source snapshots or events; write migration journal and backup before the version pointer, atomically replace the pointer last, restore it on failure, and expose only safe relative diagnostic refs.
- [ ] **Verify.** Run `python -m pytest tests/test_journey_migration.py tests/test_journey_recovery.py tests/test_evidence_journey.py -q`; expect PASS and byte-identical v1 fixtures after success and injected failure.
- [ ] **Commit scope.** Run `git add harness/journey_migration.py harness/journey_recovery.py tests/test_journey_migration.py tests/test_journey_recovery.py && git commit -m "feat: recover and migrate journey custody"`.

### Task P1-T5: Persist the full check lifecycle and truthful cancellation

**Files:**
- Create: `harness/journey_checks.py`
- Create: `harness/operation_supervisor.py`
- Modify: `harness/journey_service.py`
- Test: `tests/test_journey_checks.py`
- Test: `tests/test_operation_supervisor.py`
- Test: `tests/test_evidence_packet_containment.py`

**Interfaces:**
- Consumes: exact grants and durable mutation service from P1-T3 plus `run_journey_check(journey: dict, claim_id: str, oracle_id: str, candidate: Path, context: dict, *, artifact_root: Path | None = None) -> dict` and `unavailable_result` from the accepted packet/containment baseline.
- Produces: `JourneyCheckService.request(command: CheckCommand) -> MutationAck`, `JourneyCheckService.run(operation_ref: str, runner: CheckRunner) -> MutationAck`, and `OperationSupervisor.request_cancel(*, owner_ref: str, journey_ref: str, expected_event_head: str, client_request_id: str, operation_ref: str, grant_ref: str, timeout_s: float) -> dict`.

- [ ] **Write RED tests.** Assert `check_requested` always commits; denied permission, unavailable oracle, unsupported capability, or Python containment commits `check_blocked`; admitted work commits `check_started` then exactly one `check_completed|check_failed|check_cancelled`; recovery closes abandoned starts; cancellation signals only an owned process tree and returns `CANCEL_UNAVAILABLE` when terminal control is not guaranteed.
- [ ] **Run RED.** Run `python -m pytest tests/test_journey_checks.py tests/test_operation_supervisor.py tests/test_evidence_packet_containment.py -q`; expect new-module import failures while accepted containment tests still PASS alone.
- [ ] **Implement minimal GREEN.** Inject `CheckRunner` and `OwnedProcess` protocols for tests; preserve Python pre-admission refusal before candidate read/oracle/spawn and without receipt; keep operation state `cancel_requested` until a durable terminal event is committed. This task controls Journey checks only; Phase 3 generalizes the same terminal contract to chat and agent operations.
- [ ] **Verify.** Run the RED command; expect PASS with zero oracle calls, candidate reads, child processes, or receipts in every Python-refusal case.
- [ ] **Commit scope.** Run `git add harness/journey_checks.py harness/operation_supervisor.py harness/journey_service.py tests/test_journey_checks.py tests/test_operation_supervisor.py tests/test_evidence_packet_containment.py && git commit -m "feat: persist journey check lifecycle"`.

### Task P1-T6: Expose authenticated durable routes and CLI without weakening transport

**Files:**
- Create: `harness/journey_route.py`
- Create: `harness/grant_route.py`
- Create: `harness/journey_cli.py`
- Create: `harness/evidence_public.py`
- Modify: `harness/gateway_auth.py`
- Modify: `harness/evidence_route.py`
- Modify: `harness/gateway.py`
- Modify: `harness/cli_entry.py`
- Test: `tests/test_journey_route.py`
- Test: `tests/test_grant_route.py`
- Test: `tests/test_journey_cli.py`
- Test: `tests/test_evidence_public.py`
- Test: `tests/test_gateway_auth.py`

**Interfaces:**
- Consumes: P1-T3 service/grants, P1-T5 checks/cancellation, and characterization-tested accepted public metadata/ref/result behavior extracted from `harness.evidence_route` without semantic change.
- Produces: `journey_post(path: str, raw: bytes, *, owner_ref: str, state_root: Path, evidence_root: Path, clock: Callable[[], str]) -> tuple[dict,int]`, `grant_post(path: str, raw: bytes, *, owner_ref: str, state_root: Path, clock: Callable[[], str]) -> tuple[dict,int]`, `load_or_create_owner_ref(home: Path) -> str`, CLI `grant prepare|approve-once`, and actions `create|list|resume|append|check|cancel|export` with strict allowlists.

- [ ] **Write RED tests.** Define exact request fields: create `goal,intake_ref,client_request_id,grant_ref`; list `{}`; resume `journey_ref,lens`; append `journey_ref,expected_event_head,client_request_id,grant_ref,command`, where command type is only `advance_stage|record_claim|record_next_action`; check `journey_ref,expected_event_head,client_request_id,grant_ref,claim_id,oracle_id,candidate_ref,context_ref`; cancel `journey_ref,expected_event_head,client_request_id,grant_ref,operation_ref`; export `journey_ref,expected_event_head,client_request_id,grant_ref,packet_ref`. Assert clients cannot submit timestamps, hashes, sequence, actor, lifecycle events, verdict transitions, or receipt state; also assert durable error codes, auth/ownership, non-echo messages, and no provider/network dispatch.
- [ ] **Run RED.** Run `python -m pytest tests/test_journey_route.py tests/test_grant_route.py tests/test_journey_cli.py tests/test_gateway_auth.py -q`; expect route imports to fail.
- [ ] **Implement minimal GREEN.** First move the accepted metadata/ref/result helpers into `evidence_public.py` under byte/behavior characterization tests and import them from both routes. Keep `/api/evidence/start|project|check|export|recheck` unchanged; add thin `/api/journeys/` and `/api/grants/` dispatch, load stable `owner_ref` only after bearer authentication, assign times from the injected server clock, pass only safe roots, and move enough dispatch code out of grandfathered files that none grows.
- [ ] **Verify.** Run the RED command plus `python -m pytest tests/test_evidence_route.py tests/test_evidence_route_uri_security.py tests/test_evidence_packet_containment.py -q`; expect PASS and exact accepted behavior from `665ef5e`.
- [ ] **Commit scope.** Run `git add harness/journey_route.py harness/grant_route.py harness/journey_cli.py harness/evidence_public.py harness/gateway_auth.py harness/evidence_route.py harness/gateway.py harness/cli_entry.py tests/test_journey_route.py tests/test_grant_route.py tests/test_journey_cli.py tests/test_evidence_public.py tests/test_gateway_auth.py && git commit -m "feat: expose durable journey custody"`.

### Task P1-T7: Seal Phase 1 crash, restart, and transport acceptance

**Files:**
- Create: `benchmarks/fixtures/evidence-journey/durable-restart-v2.json`
- Create: `tests/test_journey_persistence_e2e.py`
- Create: `project-docs/records/2026-08-14-desktop-phase-1-journey-persistence.md`
- Test: `tests/test_evidence_route_uri_security.py`
- Test: `tests/test_evidence_packet_containment.py`

**Interfaces:**
- Consumes: public Phase 1 routes, schemas, recovery report, and packet export/recheck from P1-T1 through P1-T6.
- Produces: a public-safe acceptance fixture and record containing source/tree hashes, event/request denominators, injected crash points, recovery outcomes, exact packet schema `flywheel.evidence-packet/v1`, packet SHA-256, commands, limitations, and `does_not_prove`.

- [ ] **Write RED acceptance.** Drive create, append, conflict, same-digest retry, changed-digest rejection, blocked Python check, fake contained check, cancellation, restart, list/resume, export, and clean-directory recheck; fixture fields are `schema,goal,intake,commands,expected_events,expected_terminal_counts` and contain no local paths or secrets.
- [ ] **Run RED.** Run `python -m pytest tests/test_journey_persistence_e2e.py -q`; expect failure because the acceptance fixture and record do not yet exist.
- [ ] **Implement minimal GREEN.** Add the deterministic fixture and generate the record from captured local test outputs; require acknowledged-loss `0`, duplicate-logical-event `0`, silent-overwrite `0`, and unclosed-check-request `0`, while stating that general Python containment and release readiness are not proved.
- [ ] **Verify.** Run `python -m pytest tests/test_evidence_* tests/test_journey_* tests/test_operation_* tests/test_grant_route.py -q`, `python scripts/check_file_gate.py`, `python scripts/check_verifier_stdlib.py`, `python scripts/check_claim_language.py`, `python scripts/check_public_instructions.py`, `python scripts/check_writing.py --profile procedure --gate project-docs/records/2026-08-14-desktop-phase-1-journey-persistence.md`, `python -m pytest tests/ -q`, and `python -m harness.cli_entry gate`; expect exit 0 and gate PASS/rewitness MATCH without network access.
- [ ] **Commit scope.** Run `git add benchmarks/fixtures/evidence-journey/durable-restart-v2.json tests/test_journey_persistence_e2e.py project-docs/records/2026-08-14-desktop-phase-1-journey-persistence.md && git commit -m "test: accept durable journey persistence"`.
