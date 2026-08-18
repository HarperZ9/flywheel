# Flywheel Desktop Completion Phase 2 Journey Flutter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the durable Evidence Journey the desktop home with equal Rescue, Diagnose, and Verify lenses, restart resumption, and drafts retained until a durable server acknowledgement.

**Architecture:** Typed Dart models defensively parse only server-owned v2 projections; a thin API adapter transports exact refs, heads, grants, and request IDs. A controller coordinates device-local draft/session stores with the server, while focused widgets reorder the same immutable facts without deriving verdicts or receipt truth.

**Tech Stack:** Flutter 3.44.6, Dart 3.6+, existing `http` and `crypto` packages, JSON device-local persistence, Flutter test.

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

### Task P2-T1: Define defensive Journey and evidence-state models

**Files:**
- Create: `desktop/lib/models/evidence_state.dart`
- Create: `desktop/lib/models/journey_models.dart`
- Test: `desktop/test/journey_models_test.dart`
- Test: `desktop/test/journey_lens_consistency_test.dart`

**Interfaces:**
- Consumes: Phase 1 schemas `flywheel.evidence-journey-projection/v2`, `flywheel.evidence-journey-list/v2`, and `flywheel.evidence-transport-error/v1`.
- Produces: `ReceiptState`, `JourneyStage`, `JourneyOperationState`, `JourneyLens`, `GrantProposal`, `GrantRef`, `JourneyProjection.fromJson`, `JourneySummary.fromJson`, `JourneyMutationAck.fromJson`, `JourneyExportResult.fromJson`, and `JourneyFailure.fromJson`.

- [ ] **Write RED tests.** Parse exact states and core fields `journey_ref,event_head_sha256,fact_ids,claim_ids,checks,verdicts,missing_evidence,stage,conclusion,receipt_states,next_actions,detail`; malformed/missing lists become empty plus parse issues, an unknown server verdict or receipt state preserves the raw value and yields local `invalidResponse` rather than a truth value, and three fixture lenses must have identical core facts and head.
- [ ] **Run RED.** From `desktop/`, run `flutter test test/journey_models_test.dart test/journey_lens_consistency_test.dart`; expect compile failure because the model files do not exist.
- [ ] **Implement minimal GREEN.** Define receipt wire values exactly `missing|present_unchecked|MATCH|DRIFT|TAMPERED|UNVERIFIABLE`; receipt-ref presence never selects a state, raw values survive parse failure, and `JourneyProjection.sameEvidenceAs(other)` compares core IDs/checks/verdicts/missing evidence/stage/conclusion/head without recomputing any fact.
- [ ] **Verify.** Run the RED command and `flutter analyze`; expect PASS and no unchecked cast from gateway-controlled lists.
- [ ] **Commit scope.** Run `git add desktop/lib/models/evidence_state.dart desktop/lib/models/journey_models.dart desktop/test/journey_models_test.dart desktop/test/journey_lens_consistency_test.dart && git commit -m "feat: model durable journey projections"`.

### Task P2-T2: Add the typed Journey API adapter

**Files:**
- Create: `desktop/lib/client/journey_api.dart`
- Test: `desktop/test/journey_api_test.dart`
- Test: `desktop/test/journey_api_error_test.dart`

**Interfaces:**
- Consumes: Phase 1 action envelopes and P2-T1 Dart models; uses public `GatewayClient.getJson` and `GatewayClient.postJson` only.
- Produces: `abstract interface class JourneyApi` and `class GatewayJourneyApi implements JourneyApi` with `prepareGrant`, `approveGrantOnce`, `create`, `list`, `resume`, `append`, `check`, `cancel`, and `export` futures.

- [ ] **Write RED tests.** Use `http/testing.dart` to assert exact paths and JSON fields, bearer-aware client reuse, no path interpolation from `journey_ref`, and typed mapping of `HEAD_CONFLICT`, `AUTH_REQUIRED`, `VERSION_MISMATCH`, `STORE_COMMIT_FAILED`, and malformed success bodies.
- [ ] **Run RED.** From `desktop/`, run `flutter test test/journey_api_test.dart test/journey_api_error_test.dart`; expect compile failure for `JourneyApi`.
- [ ] **Implement minimal GREEN.** Use signatures `Future<GrantProposal> prepareGrant(GrantIntent intent)`, `Future<GrantRef> approveGrantOnce(String proposalRef)`, `Future<JourneyMutationAck> create(JourneyCreateRequest request)`, `Future<List<JourneySummary>> list()`, `Future<JourneyProjection> resume(String journeyRef, JourneyLens lens)`, `Future<JourneyMutationAck> append(JourneyAppendRequest request)`, `Future<JourneyMutationAck> check(JourneyCheckRequest request)`, `Future<JourneyMutationAck> cancel(JourneyCancelRequest request)`, and `Future<JourneyExportResult> export(JourneyExportRequest request)`; every mutation carries `clientRequestId,expectedEventHead,grantRef` where Phase 1 requires them.
- [ ] **Verify.** Run the RED command and `flutter analyze`; expect PASS, canonical field names, and no local file path in a URL or error string.
- [ ] **Commit scope.** Run `git add desktop/lib/client/journey_api.dart desktop/test/journey_api_test.dart desktop/test/journey_api_error_test.dart && git commit -m "feat: add typed journey client"`.

### Task P2-T3: Persist drafts and the active session locally

**Files:**
- Create: `desktop/lib/services/journey_draft_store.dart`
- Create: `desktop/lib/services/journey_session_store.dart`
- Test: `desktop/test/journey_draft_store_test.dart`
- Test: `desktop/test/journey_session_store_test.dart`

**Interfaces:**
- Consumes: `journey_ref` and `event_head_sha256` vocabulary from P2-T1; stores no server truth or credential values.
- Produces: `JourneyDraft(draftRef,journeyRef,baseEventHeadSha256,kind,payload,payloadSha256,state,updatedAt)`, `JourneyDraftStore.save/list/delete/markFailed`, and `JourneySessionStore.load/save/clear`.

- [ ] **Write RED tests.** Round-trip states `clean|dirty|saving|saved|save_failed|recovery_available`; reject secrets and absolute/traversal refs; preserve a dirty draft through process-style reload; and retain it after simulated conflict, auth failure, malformed ack, and store failure while deleting only after an ack matches both request ID and new head.
- [ ] **Run RED.** From `desktop/`, run `flutter test test/journey_draft_store_test.dart test/journey_session_store_test.dart`; expect imports to fail.
- [ ] **Implement minimal GREEN.** Accept an injected `File` for tests, write canonical JSON through a sibling temporary file plus flush and rename, hash payload bytes with `crypto`, and persist only active `journey_ref`, selected lens, selection ref, and local view state in the session record.
- [ ] **Verify.** Run the RED command; expect PASS with byte-stable records and no draft deletion before acknowledgement.
- [ ] **Commit scope.** Run `git add desktop/lib/services/journey_draft_store.dart desktop/lib/services/journey_session_store.dart desktop/test/journey_draft_store_test.dart desktop/test/journey_session_store_test.dart && git commit -m "feat: preserve journey drafts locally"`.

### Task P2-T4: Coordinate resume, lens changes, and acknowledged append

**Files:**
- Create: `desktop/lib/controllers/journey_controller.dart`
- Test: `desktop/test/journey_controller_test.dart`
- Test: `desktop/test/journey_restart_test.dart`

**Interfaces:**
- Consumes: `JourneyApi` from P2-T2 and draft/session stores from P2-T3.
- Produces: `JourneyController extends ChangeNotifier` with `initialize()`, `selectJourney(String)`, `selectLens(JourneyLens)`, `saveDraft(JourneyDraft)`, `submitStart(JourneyDraft)`, `submitAppend(JourneyDraft)`, `runCheck(JourneyCheckDraft)`, `requestCancel(String operationRef)`, and immutable `JourneyViewState`.

- [ ] **Write RED tests.** A stored active ref resumes on startup; lens fetches preserve equal core facts; append uses the projection head; success deletes the draft only after matching ack; `HEAD_CONFLICT` refreshes the server projection and keeps the draft; offline/auth/version/store failures expose typed recovery actions without changing facts.
- [ ] **Run RED.** From `desktop/`, run `flutter test test/journey_controller_test.dart test/journey_restart_test.dart`; expect compile failure for `JourneyController`.
- [ ] **Implement minimal GREEN.** Serialize mutations through one in-flight future, mint `client_request_id` once per draft and reuse it on retry, request an exact once-only grant from the explicit user action, never synthesize event heads/verdicts/receipt states, and update the session only from a parsed server acknowledgement.
- [ ] **Verify.** Run the RED command; expect PASS and identical facts/head for Rescue, Diagnose, and Verify after restart and conflict recovery.
- [ ] **Commit scope.** Run `git add desktop/lib/controllers/journey_controller.dart desktop/test/journey_controller_test.dart desktop/test/journey_restart_test.dart && git commit -m "feat: coordinate journey resume and append"`.

### Task P2-T5: Render equal Rescue, Diagnose, and Verify lenses

**Files:**
- Create: `desktop/lib/views/journey_view.dart`
- Create: `desktop/lib/widgets/journey_lenses.dart`
- Create: `desktop/lib/widgets/journey_cards.dart`
- Test: `desktop/test/journey_view_test.dart`
- Test: `desktop/test/journey_accessibility_smoke_test.dart`

**Interfaces:**
- Consumes: `JourneyController`, `JourneyViewState`, and P2-T1 server projection fields.
- Produces: `JourneyView(controller: JourneyController)`, `JourneyLensSelector`, `RescueLens`, `DiagnoseLens`, `VerifyLens`, and hidden `JourneyExtensionHost` slots that render nothing until Phase 5 supplies an accepted capability.

- [ ] **Write RED tests.** Verify equal lens prominence, same visible head/stage/fact IDs/verdicts, Rescue next action plus rollback, Diagnose support/contradiction/missing evidence, Verify checks/receipts/limits, explicit honest nulls, keyboard-selectable tabs, and no `MATCH` label for `present_unchecked`.
- [ ] **Run RED.** From `desktop/`, run `flutter test test/journey_view_test.dart test/journey_accessibility_smoke_test.dart`; expect missing-widget compile failures.
- [ ] **Implement minimal GREEN.** Use existing tokens and `Fw` components, text/icon plus verdict-only color, `Semantics(selected: lens == selectedLens, button: true)`, visible focus, `MediaQuery.disableAnimationsOf(context)`, and server-provided strings/collections only; keep Phase 2 animation decisions local until Phase 4 centralizes duration, and keep each widget/function focused and each new file below 300 lines.
- [ ] **Verify.** Run the RED command and `flutter analyze`; expect PASS with no client-side hash, verdict, claim, or missing-evidence derivation.
- [ ] **Commit scope.** Run `git add desktop/lib/views/journey_view.dart desktop/lib/widgets/journey_lenses.dart desktop/lib/widgets/journey_cards.dart desktop/test/journey_view_test.dart desktop/test/journey_accessibility_smoke_test.dart && git commit -m "feat: render three journey lenses"`.

### Task P2-T6: Make Journey the home and seal Phase 2 acceptance

**Files:**
- Create: `desktop/lib/app.dart`
- Create: `desktop/lib/shell/flywheel_shell.dart`
- Create: `desktop/lib/shell/view_factory.dart`
- Create: `desktop/test/journey_shell_test.dart`
- Create: `project-docs/records/2026-08-14-desktop-phase-2-journey-flutter.md`
- Modify: `desktop/lib/main.dart`
- Modify: `desktop/test/widget_test.dart`

**Interfaces:**
- Consumes: Journey view/controller/API/stores from P2-T1 through P2-T5 and all 29 existing destination widgets.
- Produces: `FlywheelApp`, `FlywheelShell`, and `buildDestinationView` split below file ceilings; startup route is Journey and the 29 preexisting destinations remain reachable.

- [ ] **Write RED acceptance.** Assert Journey is the first/startup view, all prior labels still navigate, active Journey resumes after a new app instance, all three lenses show the same head/facts, and failed/conflicted append preserves the draft with an actionable recovery state.
- [ ] **Run RED.** From `desktop/`, run `flutter test test/journey_shell_test.dart test/widget_test.dart`; expect failure because Journey is not the startup destination and the shell has not been split.
- [ ] **Implement minimal GREEN.** Reduce `main.dart` to bootstrap/export duties, move app theme ownership to `app.dart`, move polling/process/shell state to `flywheel_shell.dart`, move view imports/switching to `view_factory.dart`, inject the Journey dependencies, and do not regroup routes until Phase 4.
- [ ] **Verify.** From `desktop/`, run `flutter analyze` and `flutter test`; expect exit 0. From the repo root run `python scripts/check_file_gate.py`, `python scripts/check_public_instructions.py`, and `git diff --check`; expect exit 0 and no grown grandfathered file.
- [ ] **Commit scope.** Run `git add desktop/lib/main.dart desktop/lib/app.dart desktop/lib/shell/flywheel_shell.dart desktop/lib/shell/view_factory.dart desktop/test/journey_shell_test.dart desktop/test/widget_test.dart project-docs/records/2026-08-14-desktop-phase-2-journey-flutter.md && git commit -m "feat: make journey the desktop home"`.
