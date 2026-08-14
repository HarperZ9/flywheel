# Flywheel Desktop Completion Phase 3 Truth Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every approved P0 truth, permission, cancellation, and work-loss defect with failing-before and passing-after evidence.

**Architecture:** Shared typed states replace boolean or presence-based claims, while device-local journals protect unsent prompts and dirty buffers. Phase 1 grants and operation custody expand to every mutation/external call; the UI can request exact cancellation but cannot declare a terminal state before the server commits it.

**Tech Stack:** Python 3.11+ standard library, existing gateway/Journey/grant services, Flutter 3.44.6, Dart 3.6+, `crypto`, pytest, Flutter test.

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

### Task P3-T1: Preserve chat prompts and render receipt truth

**Files:**
- Create: `desktop/lib/services/chat_draft_store.dart`
- Modify: `desktop/lib/models/chat.dart`
- Modify: `desktop/lib/views/agent_view.dart`
- Modify: `desktop/lib/widgets/chat_composer.dart`
- Modify: `desktop/lib/widgets/chat_thread.dart`
- Test: `desktop/test/chat_truth_test.dart`
- Test: `desktop/test/chat_draft_test.dart`

**Interfaces:**
- Consumes: `ReceiptState` from Phase 2 and the existing conversation/chat stream wire shape.
- Produces: `enum PromptDisposition { accepted, retained }`, `typedef SubmitPrompt = Future<PromptDisposition> Function(String text)`, `ChatDraftStore.save/load/delete`, and explicit `ChatMessage.receiptState` independent of `receipt` presence.

- [ ] **Write RED tests.** With no selected model, submit a prompt and require the composer text plus device draft to remain; on accepted submission persist before clearing; render `missing` and `present_unchecked` explicitly; never show `verified` or `MATCH` merely because a receipt map exists; keyboard activation must open receipt detail.
- [ ] **Run RED.** From `desktop/`, run `flutter test test/chat_truth_test.dart test/chat_draft_test.dart`; expect failures because `onSend` is synchronous, the composer clears unconditionally, and receipt presence renders `verified`.
- [ ] **Implement minimal GREEN.** Await `SubmitPrompt`, clear only on `accepted`, journal `{draft_ref,conversation_ref,text,text_sha256,state,updated_at}` before transport, delete only after server acceptance, and map only a server verification result to `MATCH`; split helpers so touched files do not grow past their current ceilings.
- [ ] **Verify.** Run the RED command and `flutter analyze`; expect PASS with zero prompt loss across no-model, error, navigation, and recreated-widget cases.
- [ ] **Commit scope.** Run `git add desktop/lib/services/chat_draft_store.dart desktop/lib/models/chat.dart desktop/lib/views/agent_view.dart desktop/lib/widgets/chat_composer.dart desktop/lib/widgets/chat_thread.dart desktop/test/chat_truth_test.dart desktop/test/chat_draft_test.dart && git commit -m "fix: preserve chat drafts and receipt truth"`.

### Task P3-T2: Protect dirty code buffers through close, navigation, and crash

**Files:**
- Create: `desktop/lib/services/code_draft_store.dart`
- Create: `desktop/lib/ide/code_buffer_session.dart`
- Create: `desktop/lib/ide/unsaved_work_guard.dart`
- Modify: `desktop/lib/views/code_view.dart`
- Modify: `desktop/lib/ide/tab_bar.dart`
- Modify: `desktop/lib/shell/flywheel_shell.dart`
- Test: `desktop/test/code_draft_store_test.dart`
- Test: `desktop/test/code_close_guard_test.dart`

**Interfaces:**
- Consumes: Phase 2 shell boundary and existing `OpenFile`/workspace save functions.
- Produces: `CodeDraft(path,diskSha256,bufferSha256,text,updatedAt)`, `enum CloseChoice { save, discard, cancel }`, `CodeBufferSession.snapshot/recover/save/discard`, and `UnsavedWorkGuard.requestNavigation(String routeId) -> Future<bool>`.

- [ ] **Write RED tests.** Dirty a buffer, then close file/workspace, navigate, request app exit, and recreate the app; require Save/Discard/Cancel, cancel leaves state intact, failed save blocks close, crash recovery appears only when disk digest still matches, and a changed disk yields a non-destructive comparison instead of overwrite.
- [ ] **Run RED.** From `desktop/`, run `flutter test test/code_draft_store_test.dart test/code_close_guard_test.dart`; expect failures because current dispose/close paths destroy controllers without a guard or journal.
- [ ] **Implement minimal GREEN.** Snapshot on edit with atomic flush/rename, intercept navigation through `UnsavedWorkGuard`, use `AppLifecycleListener.onExitRequested`, restore only after digest comparison, and extract controller logic until `code_view.dart` and each new file meet the file/function ceilings.
- [ ] **Verify.** Run the RED command and `flutter analyze`; expect PASS and zero buffer loss across every accepted close/crash/restart branch.
- [ ] **Commit scope.** Run `git add desktop/lib/services/code_draft_store.dart desktop/lib/ide/code_buffer_session.dart desktop/lib/ide/unsaved_work_guard.dart desktop/lib/views/code_view.dart desktop/lib/ide/tab_bar.dart desktop/lib/shell/flywheel_shell.dart desktop/test/code_draft_store_test.dart desktop/test/code_close_guard_test.dart && git commit -m "fix: guard dirty code buffers"`.

### Task P3-T3: Require exact grants on gateway mutations and external calls

**Files:**
- Create: `harness/gateway_grants.py`
- Modify: `harness/gateway.py`
- Modify: `harness/plugins.py`
- Modify: `harness/workflows.py`
- Test: `tests/test_gateway_operation_grants.py`
- Test: `tests/test_plugin_grants.py`
- Test: `tests/test_workflow_grants.py`

**Interfaces:**
- Consumes: Phase 1 `GrantRequest`, `GrantStore.consume`, stable `owner_ref`, CAS head, and canonical JSON digest.
- Produces: `authorize_gateway_operation(*, owner_ref: str, journey_ref: str, expected_event_head: str, client_request_id: str, grant_ref: str, tool: str, arguments: dict, scopes: list[str], data_refs: list[str]) -> AuthorizedOperation`.

- [ ] **Write RED tests.** Exercise chat/provider, agent, workflow, plugin probe/call, write, exec, and network paths with missing, global, stale-head, wrong-argument, wrong-tool, expired, reused, and valid once-only grants; registration and checkboxes grant nothing; denials occur before dispatch and expose fixed messages only.
- [ ] **Run RED.** Run `python -m pytest tests/test_gateway_operation_grants.py tests/test_plugin_grants.py tests/test_workflow_grants.py -q`; expect import failure for `harness.gateway_grants` and current ungranted plugin call to fail the new assertion.
- [ ] **Implement minimal GREEN.** Canonicalize the complete operation, validate exact scopes `write|exec|plugin|network`, durably consume before dispatch, pass an immutable `AuthorizedOperation` to extracted route handlers, and shrink `gateway.py` by more lines than the thin dispatch adds.
- [ ] **Verify.** Run the RED command plus `python -m pytest tests/test_operation_grants.py tests/test_gateway.py -q`; expect PASS with zero unauthorized dispatch calls.
- [ ] **Commit scope.** Run `git add harness/gateway_grants.py harness/gateway.py harness/plugins.py harness/workflows.py tests/test_gateway_operation_grants.py tests/test_plugin_grants.py tests/test_workflow_grants.py && git commit -m "fix: gate mutations with exact grants"`.

### Task P3-T4: Replace observation detachment with terminal operation Stop

**Files:**
- Create: `harness/gateway_operations.py`
- Create: `desktop/lib/models/operation_models.dart`
- Create: `desktop/lib/client/gateway_operations.dart`
- Create: `desktop/lib/client/gateway_sse_decoder.dart`
- Create: `desktop/lib/controllers/operation_controller.dart`
- Create: `desktop/lib/widgets/operation_controls.dart`
- Modify: `harness/gateway.py`
- Modify: `desktop/lib/client/gateway_streams.dart`
- Modify: `desktop/lib/views/agent_view.dart`
- Modify: `desktop/lib/ide/agent_panel.dart`
- Test: `tests/test_gateway_operations.py`
- Test: `desktop/test/operation_stop_test.dart`
- Test: `desktop/test/agent_permission_defaults_test.dart`

**Interfaces:**
- Consumes: Phase 1 `OperationSupervisor` terminal contract and P3-T3 exact grants.
- Produces: `start_operation(*, owner_ref: str, journey_ref: str, expected_event_head: str, client_request_id: str, grant_ref: str, operation: str, arguments: dict) -> OperationSnapshot`; `cancel_operation(*, owner_ref: str, journey_ref: str, expected_event_head: str, client_request_id: str, operation_ref: str, grant_ref: str, timeout_s: float) -> OperationSnapshot`; Dart `ExecutionState`; and `GatewayOperations.start/watch/cancel`. Snapshots carry `operation_ref,journey_ref,event_head_sha256,state,can_cancel,terminal_event_ref`.

- [ ] **Write RED tests.** Assert agent write/exec defaults are false; a stream close never changes server state; Stop binds Journey/head/request/operation/grant, signals the owned process tree, remains `cancel_requested` until `cancelled|completed|failed`, seals exactly one terminal event, and returns `CANCEL_UNAVAILABLE` without a false cancelled label when control is not guaranteed.
- [ ] **Run RED.** Run `python -m pytest tests/test_gateway_operations.py -q`; expect import failure. From `desktop/`, run `flutter test test/operation_stop_test.dart test/agent_permission_defaults_test.dart`; expect failures for write=true and Detach semantics.
- [ ] **Implement minimal GREEN.** Run controllable work behind an owned worker/process-tree handle, emit `operation_ref` before progress, keep closing a view observational only, remove `Leave running`, and show Stop only when `can_cancel`. Move SSE framing into `gateway_sse_decoder.dart`, operation state into `operation_controller.dart`, and controls into `operation_controls.dart`; leave `gateway_streams.dart` below 300 lines and `agent_panel.dart` below its 295-line baseline.
- [ ] **Verify.** Run both RED commands; expect PASS, descendant cleanup, one terminal event, and no UI terminal claim before that event.
- [ ] **Commit scope.** Run `git add harness/gateway_operations.py harness/gateway.py desktop/lib/models/operation_models.dart desktop/lib/client/gateway_operations.dart desktop/lib/client/gateway_sse_decoder.dart desktop/lib/controllers/operation_controller.dart desktop/lib/widgets/operation_controls.dart desktop/lib/client/gateway_streams.dart desktop/lib/views/agent_view.dart desktop/lib/ide/agent_panel.dart tests/test_gateway_operations.py desktop/test/operation_stop_test.dart desktop/test/agent_permission_defaults_test.dart && git commit -m "fix: make stop a terminal server action"`.

### Task P3-T5: Bind Plan Run to the complete forged contract

**Files:**
- Create: `harness/plan_run_contract.py`
- Create: `desktop/lib/client/gateway_plan.dart`
- Create: `desktop/lib/controllers/plan_controller.dart`
- Create: `desktop/lib/widgets/plan_run_controls.dart`
- Modify: `harness/gateway.py`
- Modify: `harness/workflows.py`
- Modify: `desktop/lib/models/plan_models.dart`
- Modify: `desktop/lib/views/plan_view.dart`
- Test: `tests/test_plan_run_contract.py`
- Test: `desktop/test/plan_run_binding_test.dart`

**Interfaces:**
- Consumes: persisted forge seal/PRP, P3-T3 exact grant, and existing workflow runner.
- Produces: `PlanRunBinding(prp_id,prompt,prompt_sha256,gates,gates_sha256,seal_sha256)`, `verify_plan_run(binding: dict, stored_seal: dict) -> dict`, and `GatewayPlan.runBoundPlan(PlanRunBinding binding, GrantRef grantRef) -> Future<PlanRunResult>`.

- [ ] **Write RED tests.** Forge then mutate the goal-only run, full prompt, PRP ID, gate order/content, gate digest, or seal; every drift must return fixed `PLAN_BINDING_DRIFT` before workflow/endpoint dispatch, while an exact binding passes unchanged and is included in the run receipt.
- [ ] **Run RED.** Run `python -m pytest tests/test_plan_run_contract.py tests/test_forge_seal.py -q`; expect import failure. From `desktop/`, run `flutter test test/plan_run_binding_test.dart`; expect the request to contain only the current plan goal.
- [ ] **Implement minimal GREEN.** Canonicalize and seal all fields at forge time, require `prp_id,prompt,prompt_sha256,gates,gates_sha256,seal_sha256` plus the exact grant at run time, compare before dispatch, and render a drift refusal without silently reforging. Move request/state handling to `plan_controller.dart` and controls to `plan_run_controls.dart`, leaving `plan_view.dart` below its 295-line baseline. Rename the current `externallyCheckable ? verified : unverifiable` presentation to neutral `checkable|manual`; checkability is not execution evidence.
- [ ] **Verify.** Run both RED commands plus `python -m pytest tests/test_gateway.py tests/test_profiles_workflows.py -q` and from `desktop/` `flutter test test/plan_models_test.dart`; expect PASS with zero dispatch on every planted drift.
- [ ] **Commit scope.** Run `git add harness/plan_run_contract.py harness/gateway.py harness/workflows.py desktop/lib/client/gateway_plan.dart desktop/lib/controllers/plan_controller.dart desktop/lib/widgets/plan_run_controls.dart desktop/lib/models/plan_models.dart desktop/lib/views/plan_view.dart tests/test_plan_run_contract.py desktop/test/plan_run_binding_test.dart && git commit -m "fix: bind runs to forged plan evidence"`.

### Task P3-T6: Align receipt-proof schemas and recompute inclusion in Dart

**Files:**
- Create: `harness/receipt_proof.py`
- Create: `desktop/lib/models/receipt_proof.dart`
- Create: `desktop/lib/widgets/receipt_proof_panel.dart`
- Modify: `harness/gateway.py`
- Modify: `desktop/lib/views/receipts_view.dart`
- Test: `tests/test_receipt_proof_route.py`
- Test: `desktop/test/receipt_proof_test.dart`
- Test: `desktop/test/receipts_view_truth_test.dart`

**Interfaces:**
- Consumes: `harness.transparency_log.inclusion_proof/verify_inclusion` and Phase 2 receipt states.
- Produces: one `flywheel.receipts-proof/v2` wire object with `schema,leaf,index,tree_size,merkle_root,audit_path`; each audit step is exactly `{hash,side:left|right}`; Dart `verifyReceiptProof(ReceiptProof) -> ReceiptProofResult`.

- [ ] **Write RED tests.** Cross-language fixtures cover valid proof, wrong leaf/root/side/order/index/size, malformed hex, odd promotion, absent leaf, and present-but-unchecked loading; the widget may show `MATCH` only after the pure Dart recomputation lands on the advertised root.
- [ ] **Run RED.** Run `python -m pytest tests/test_receipt_proof_route.py -q`; expect missing-module failure. From `desktop/`, run `flutter test test/receipt_proof_test.dart test/receipts_view_truth_test.dart`; expect parse-field mismatch and false verified-label failures.
- [ ] **Implement minimal GREEN.** Normalize gateway proof keys in the new route module; in Dart hash leaf as `sha256(0x00 || leafBytes)` and each node as `sha256(0x01 || left || right)`, reject any malformed step, and keep state `present_unchecked` until recomputation. Move proof interaction/rendering to `receipt_proof_panel.dart` so `receipts_view.dart` falls below 300 lines.
- [ ] **Verify.** Run both RED commands plus `python -m pytest tests/test_gateway.py -q`; expect PASS and matching Python/Dart vectors.
- [ ] **Commit scope.** Run `git add harness/receipt_proof.py harness/gateway.py desktop/lib/models/receipt_proof.dart desktop/lib/widgets/receipt_proof_panel.dart desktop/lib/views/receipts_view.dart tests/test_receipt_proof_route.py desktop/test/receipt_proof_test.dart desktop/test/receipts_view_truth_test.dart && git commit -m "fix: verify receipt inclusion in desktop"`.

### Task P3-T7: Type connection state, compose scaling, and seal the P0 matrix

**Files:**
- Create: `harness/desktop_status.py`
- Create: `desktop/lib/models/connection_state.dart`
- Create: `desktop/lib/services/gateway_status.dart`
- Create: `desktop/lib/widgets/system_text_scaler.dart`
- Create: `desktop/lib/accessibility/accessible_action.dart`
- Create: `desktop/lib/widgets/rail_item.dart`
- Create: `desktop/lib/widgets/rail_resizer.dart`
- Create: `desktop/lib/widgets/fw_verdict.dart`
- Create: `desktop/lib/widgets/fw_layout.dart`
- Create: `tests/test_desktop_status.py`
- Create: `desktop/test/connection_state_test.dart`
- Create: `desktop/test/critical_accessibility_test.dart`
- Create: `project-docs/records/2026-08-14-desktop-phase-3-truth-safety.md`
- Modify: `harness/gateway.py`
- Modify: `desktop/lib/app.dart`
- Modify: `desktop/lib/shell/flywheel_shell.dart`
- Modify: `desktop/lib/widgets/side_rail.dart`
- Modify: `desktop/lib/widgets/chat_sidebar.dart`
- Modify: `desktop/lib/widgets/fw.dart`
- Modify: `desktop/lib/widgets/graph_canvas.dart`
- Modify: `desktop/lib/widgets/split_pane.dart`
- Modify: `desktop/lib/ide/file_tree.dart`
- Modify: `desktop/lib/ide/lint_index_sheet.dart`
- Modify: `desktop/lib/ide/open_panel.dart`
- Modify: `desktop/lib/ide/tab_bar.dart`

**Interfaces:**
- Consumes: all P3 task outcomes and Phase 2 app/shell; this task removes the current P0 pointer-only actions, while Phase 4 audits every destination and critical flow under assistive display modes.
- Produces: status schema `flywheel.desktop-status/v1`, `ConnectionPhase.starting|online|degraded|offline|authRequired|versionMismatch`, and `SystemTextScaler(system,userScale)` where `scale(fontSize) = system.scale(fontSize) * userScale`.

- [ ] **Write RED tests.** Distinguish startup, 200 healthy, partial/degraded, no response, 401, and incompatible API; assert system 2.0 scaling combined with user 1.2 yields 2.4 rather than 1.2; every current raw pointer action in the listed rail/chat/graph/split/file/tab/open/lint surfaces exposes labels, keyboard invocation or adjustment, and visible focus.
- [ ] **Run RED.** Run `python -m pytest tests/test_desktop_status.py -q`; expect import failure. From `desktop/`, run `flutter test test/connection_state_test.dart test/critical_accessibility_test.dart`; expect bool-state, replaced-scaler, and pointer-only failures.
- [ ] **Implement minimal GREEN.** Add a read-only authenticated status route, map typed failures without echo, compose the system scaler, and replace pointer-only actions with the shared focusable semantic primitive (keyboard increments for drag-only controls). Move rail item/resizer code to `rail_item.dart`/`rail_resizer.dart` and verdict/layout primitives to `fw_verdict.dart`/`fw_layout.dart`; leave `side_rail.dart` and `fw.dart` below 300 lines. Record one failing-before/passing-after row for every Phase 3 P0 with command, source commit, artifact hash, limitation, and receiving-owner acceptance.
- [ ] **Verify.** Run `python -m pytest tests/test_desktop_status.py tests/test_gateway_operations.py tests/test_gateway_operation_grants.py tests/test_plan_run_contract.py tests/test_receipt_proof_route.py -q`, `python -m pytest tests/ -q`, `python scripts/check_file_gate.py`, `python scripts/check_verifier_stdlib.py`, `python scripts/check_claim_language.py`, and `python scripts/check_public_instructions.py`; then from `desktop/` run `flutter test test/chat_truth_test.dart test/chat_draft_test.dart test/code_draft_store_test.dart test/code_close_guard_test.dart test/operation_stop_test.dart test/agent_permission_defaults_test.dart test/plan_run_binding_test.dart test/receipt_proof_test.dart test/receipts_view_truth_test.dart test/connection_state_test.dart test/critical_accessibility_test.dart`, `flutter analyze`, and `flutter test`. Expect exit 0, zero false verified labels, zero unauthorized dispatch, zero accepted work loss, and zero fake Stop.
- [ ] **Commit scope.** Run `git add harness/desktop_status.py harness/gateway.py desktop/lib/models/connection_state.dart desktop/lib/services/gateway_status.dart desktop/lib/widgets/system_text_scaler.dart desktop/lib/accessibility/accessible_action.dart desktop/lib/widgets/rail_item.dart desktop/lib/widgets/rail_resizer.dart desktop/lib/widgets/fw_verdict.dart desktop/lib/widgets/fw_layout.dart desktop/lib/app.dart desktop/lib/shell/flywheel_shell.dart desktop/lib/widgets/side_rail.dart desktop/lib/widgets/chat_sidebar.dart desktop/lib/widgets/fw.dart desktop/lib/widgets/graph_canvas.dart desktop/lib/widgets/split_pane.dart desktop/lib/ide/file_tree.dart desktop/lib/ide/lint_index_sheet.dart desktop/lib/ide/open_panel.dart desktop/lib/ide/tab_bar.dart tests/test_desktop_status.py desktop/test/connection_state_test.dart desktop/test/critical_accessibility_test.dart project-docs/records/2026-08-14-desktop-phase-3-truth-safety.md && git commit -m "test: close desktop truth and safety P0s"`.
