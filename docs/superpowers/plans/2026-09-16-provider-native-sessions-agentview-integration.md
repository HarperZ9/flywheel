# Provider Native Sessions AgentView Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire provider-native sessions into AgentView as a real user path with native-session navigation, source-linked context, pending approval visibility, and explicit stop/resume/reconcile controls.

**Architecture:** Keep the reviewed typed provider-session request/state slice as the gateway boundary. Add a small AgentView-owned orchestration layer that reuses `GatewayOperationController`, `OperationController`, `GatewayOperations`, `ChatContextController`, and the existing Journey-scoped grant sheet instead of introducing another memory store or authorization path. The UI becomes a three-mode surface: text chat, workspace agent, and native session.

**Tech Stack:** Flutter desktop, existing Dart gateway clients/controllers, Journey grant scope, Canon context-memory bridge, provider-session gateway operations.

**Spec:** `docs/superpowers/specs/2026-09-16-provider-native-sessions-design.md`; current Task 4 entry in `docs/superpowers/plans/2026-09-16-provider-native-sessions.md`.

## Global Constraints

- Do not edit the frozen reviewed desktop files until independent rereview clears the current HOLD repair.
- No provider launch, provider authentication read, model generation, install, build, release, or AgentView readiness claim from this plan.
- Reuse Journey-bound `GatewayOperationScope` and the one-shot grant sheet. Do not add a second approval system.
- Reuse Canon context-memory APIs and source-context attachment APIs. Do not add another memory store.
- Preserve default provider runtime disabled/empty-registry behavior as an honest incomplete state.
- Provider writes with indeterminate history or side effects must require reconcile before fresh send.
- Every edited file must remain under the repo file gate.

---

## Current source facts this plan relies on

- `desktop/lib/views/agent_view.dart` currently stores `_agentMode` as a bool and switches only between text chat and `AgentModePane`.
- `desktop/lib/widgets/chat_header.dart` renders only `chat` and `agent` mode chips.
- `desktop/lib/views/agent_view_admission.dart` already runs `ChatContextController.prepare()` before text chat dispatch, displays `ChatContextStatus`, and captures user turns into Canon with `source_surface: agent-view-text-chat`.
- `desktop/lib/ide/agent_panel.dart` already owns endpoint/model controls, permission toggles, grant preparation/approval, `OperationController.observe`, typed stop approval, live trace rendering, and past run replay for `agent.run`.
- `desktop/lib/widgets/provider_session_pane.dart` is a standalone inspectable pane with buttons for send, stop, resume, and reconcile, but no dispatch binding.
- `desktop/lib/models/provider_session_operations.dart` can produce typed `provider.session.turn`, `provider.session.resume`, and `provider.session.reconcile` operations with `attachment_refs` and source/target operation refs.
- `desktop/lib/client/gateway_operations.dart` admits `/api/provider-sessions/turn`, `/api/provider-sessions/resume`, and `/api/provider-sessions/reconcile` SSE starts and validates watched operation refs.
- `desktop/lib/controllers/provider_session_controller.dart` folds `progress.provider_session` and terminal results, rejecting stale operation refs and preserving reconcile-required terminal states.
- `desktop/lib/widgets/operation_grant_sheet.dart` and `GatewayOperationController` already bind approvals to current operation plus current Journey head.
- `desktop/lib/client/source_context_api.dart` exposes source-context inspect/select/attach routes that can produce source-linked attachment payloads; `desktop/lib/client/gateway_context_memory.dart` and `desktop/lib/controllers/chat_context_controller.dart` expose Canon preflight/capture for shared context.
- `desktop/lib/widgets/codex_account_panel.dart` and `desktop/lib/controllers/codex_account_controller.dart` already provide the existing Codex account control surface, but AgentView does not embed it today.

## Target UX state machine

- `textChat`: existing chat flow, unchanged.
- `workspaceAgent`: existing `AgentModePane`, unchanged except for enum-based mode selection.
- `nativeSession.idle`: provider selected, no active operation, turn input enabled.
- `nativeSession.checkingContext`: Canon preflight/capture and optional source attachment are running; send disabled.
- `nativeSession.awaitingGrant`: grant sheet is open; close/deny consumes no approval and returns to idle with draft retained.
- `nativeSession.running`: operation SSE stream is observing; stop button is enabled only when `OperationSnapshot.state == running && canCancel == true`.
- `nativeSession.needsReconcile`: terminal or close-indeterminate state requires `provider.session.reconcile`; fresh send disabled.
- `nativeSession.terminalReady`: history and side-effect statuses allow another turn or explicit resume.
- `nativeSession.observerError`: no fresh send if side-effect status is unknown; show reconcile/resume options according to the folded provider state.

## File structure

- Modify `desktop/lib/views/agent_view.dart`: replace `_agentMode` with an enum, own the native-session controller lifecycle, and pass Canon/status dependencies to the native session surface.
- Modify `desktop/lib/views/agent_view_layout.dart`: render the third mode and keep sidebar/composer behavior explicit per mode.
- Modify `desktop/lib/widgets/chat_header.dart`: replace the boolean mode API with a small mode enum and render `chat`, `agent`, and `native` chips.
- Create `desktop/lib/models/agent_view_mode.dart`: enum `AgentViewMode { chat, workspaceAgent, nativeSession }` with labels.
- Create `desktop/lib/controllers/provider_session_operation_controller.dart`: AgentView-owned orchestration around `ProviderSessionController`, `OperationController`, `GatewayOperationController`, `GatewayOperations`, Canon context prep, and provider-session request builders.
- Create `desktop/lib/widgets/provider_session_surface.dart`: user-facing native-session pane with provider/model controls, account-control link, source-context controls, prompt field, pending approval state, provider event state, and trace/private attachment widgets.
- Modify `desktop/lib/widgets/provider_session_pane.dart`: keep it as the factual state card, but accept a compact status string and expose button keys for tests after rereview clears.
- Modify `desktop/lib/models/provider_session_state.dart` only if rereview clears and tests prove an additional send/resume guard is needed.
- Test `desktop/test/agent_view_native_session_test.dart`: AgentView mode navigation, grant/dispatch path, pending approval denial, stop/reconcile/resume controls, and source-linked handoff.
- Test `desktop/test/provider_session_operation_controller_test.dart`: controller state transitions without widget coupling.
- Extend `desktop/test/agent_mode_split_test.dart`: existing chat/agent split becomes chat/agent/native split.

---

### Task 1: Introduce AgentView mode enum and header navigation

**Files:**
- Create: `desktop/lib/models/agent_view_mode.dart`
- Modify: `desktop/lib/widgets/chat_header.dart`
- Modify: `desktop/lib/views/agent_view.dart`
- Modify: `desktop/lib/views/agent_view_layout.dart`
- Test: `desktop/test/agent_mode_split_test.dart`

**Interfaces:**
- Consumes: current `ChatHeader(agentMode: bool, onMode: ValueChanged<bool>)` API.
- Produces: `AgentViewMode` enum and `ChatHeader(mode: AgentViewMode, onMode: ValueChanged<AgentViewMode>)`.

- [ ] **Step 1: Write the failing navigation test**

```dart
testWidgets('AgentView switches among chat, workspace agent, and native session', (tester) async {
  await _pump(tester, AgentView(
    client: GatewayClient(),
    alive: true,
    settings: DesktopSettings(),
  ));
  await tester.pump();

  expect(find.text('Point the agent at a workspace'), findsNothing);
  expect(find.text('Provider native session'), findsNothing);

  await tester.tap(find.text('agent'));
  await tester.pump();
  expect(find.text('Point the agent at a workspace'), findsOneWidget);

  await tester.tap(find.text('native'));
  await tester.pump();
  expect(find.text('Provider native session'), findsOneWidget);
  expect(find.text('Point the agent at a workspace'), findsNothing);

  await tester.tap(find.text('chat'));
  await tester.pump();
  expect(find.text('Provider native session'), findsNothing);
});
```

- [ ] **Step 2: Run the focused test and confirm it fails**

Run: `flutter test test/agent_mode_split_test.dart`

Expected: FAIL because the `native` chip and native session body do not exist.

- [ ] **Step 3: Add `AgentViewMode`**

```dart
enum AgentViewMode { chat, workspaceAgent, nativeSession }

extension AgentViewModeLabel on AgentViewMode {
  String get label => switch (this) {
        AgentViewMode.chat => 'chat',
        AgentViewMode.workspaceAgent => 'agent',
        AgentViewMode.nativeSession => 'native',
      };
}
```

- [ ] **Step 4: Convert `ChatHeader` to mode chips**

Render one `FwModeChip` per `AgentViewMode.values`, set active when `mode == value`, and call `onMode(value)` only when `!streaming`. Keep endpoint/model controls visible only in `AgentViewMode.chat`.

- [ ] **Step 5: Convert `AgentView` state to the enum**

Replace `_agentMode` with `_mode = AgentViewMode.chat`. Convert `_applyStartTaskHandoff()` to set chat mode, and `_useWorkspaceGoal()` to set workspace-agent mode.

- [ ] **Step 6: Add a temporary native-session body using the existing pane**

Until Task 2 lands, render `ProviderSessionPane(controller: _providerSession)` in native mode with all callbacks null. This keeps Task 1 navigation testable without dispatch.

- [ ] **Step 7: Re-run the focused test**

Run: `flutter test test/agent_mode_split_test.dart`

Expected: PASS.

---

### Task 2: Add provider-session operation controller

**Files:**
- Create: `desktop/lib/controllers/provider_session_operation_controller.dart`
- Test: `desktop/test/provider_session_operation_controller_test.dart`

**Interfaces:**
- Consumes: `GatewayOperations.start()`, `GatewayOperationController.prepare()`, `OperationController.observe()`, `ProviderSessionTurnRequest`, `ProviderSessionResumeRequest`, `ProviderSessionReconcileRequest`, and `ChatContextController.prepare()`.
- Produces: `ProviderSessionOperationController` with `sendTurn()`, `stop()`, `resume()`, `reconcile()`, `state`, `operation`, `terminalResult`, `contextOutcome`, and `pendingApproval`.

- [ ] **Step 1: Write the controller dispatch test**

```dart
test('sendTurn prepares provider turn and dispatches provider-session path', () async {
  final calls = <String>[];
  final controller = ProviderSessionOperationController(
    client: fakeGatewayClient(calls),
    grants: fakeGrantController(),
    contextController: fakeContextController(referenceText: 'Canon quote'),
    operationRequestId: () => 'desktop-provider-test',
  );

  await controller.sendTurn(
    provider: 'codex',
    workspaceRef: 'workspace-main',
    configDigest: 'a' * 64,
    model: 'gpt-5.5',
    text: 'Continue this work',
    attachmentRefs: const ['data_context.package:abc'],
  );

  expect(calls, contains('/api/gateway-grants/prepare/provider.session.turn'));
  expect(calls, contains('/api/provider-sessions/turn'));
  expect(controller.session.state.provider, 'codex');
});
```

- [ ] **Step 2: Write denial and close tests**

Add cases where the grant sheet/controller denies or returns null. Expected: no provider-session dispatch, draft text retained by the widget layer, provider session remains idle.

- [ ] **Step 3: Implement `sendTurn()` minimally**

Build `ProviderSessionTurnRequest` with:

```dart
input: [
  if (canonContext != null) {'type': 'input_text', 'text': canonContext},
  {'type': 'input_text', 'text': text},
],
resumePolicy: session.state.needsReconcile
    ? ProviderSessionResumePolicy.reconcileBeforeResend
    : session.state.nativeThreadId.isEmpty
        ? ProviderSessionResumePolicy.newThread
        : ProviderSessionResumePolicy.resumeAfterReconcile,
sourceOperationRef: session.state.operationRef.isEmpty ? null : session.state.operationRef,
```

Abort before building a turn when `session.state.needsReconcile` is true and no reconcile proof has been accepted.

- [ ] **Step 4: Implement SSE observation**

Use `OperationController.observe(GatewayOperations.start(body, path: providerSessionTurnPath), onProgress: session.acceptProgress, onInterrupted: mark observer error)`. On terminal result, call `session.acceptTerminal(result)` and retain `terminalResult`.

- [ ] **Step 5: Implement `stop()`**

Delegate to `OperationController.stopOperation()` and `GatewayOperationController.prepare()` exactly as `AgentPanel._stop()` does. Dispatch through `GatewayOperations.cancel()` only after approval.

- [ ] **Step 6: Implement `resume()` and `reconcile()`**

`resume()` builds `ProviderSessionResumeRequest` from the current `operationRef`, `nativeThreadId`, and `lastProviderEventId` and dispatches `providerSessionResumePath`. `reconcile()` builds `ProviderSessionReconcileRequest` with `targetOperationRef: session.state.operationRef` and dispatches `providerSessionReconcilePath`.

- [ ] **Step 7: Run controller tests**

Run: `flutter test test/provider_session_operation_controller_test.dart`

Expected: PASS.

---

### Task 3: Replace standalone pane with AgentView native-session surface

**Files:**
- Create: `desktop/lib/widgets/provider_session_surface.dart`
- Modify: `desktop/lib/views/agent_view.dart`
- Modify: `desktop/lib/views/agent_view_layout.dart`
- Modify: `desktop/lib/widgets/provider_session_pane.dart`
- Test: `desktop/test/agent_view_native_session_test.dart`

**Interfaces:**
- Consumes: `ProviderSessionOperationController`, `ProviderSessionPane`, `CodexAccountController` status, `SourceContextApi`, and `ChatContextOutcome`.
- Produces: visible native-session workflow in AgentView.

- [ ] **Step 1: Write the widget test for a grant-backed turn**

Use `GatewayOperationScope` with a fake Journey binding. Enter text in the native prompt, tap `Send turn`, approve the grant sheet, and assert the request path is `/api/provider-sessions/turn`, not `/api/agent` or `/v1/chat/completions`.

- [ ] **Step 2: Build `ProviderSessionSurface`**

Include:

```text
- provider dropdown: codex, claude
- model text/model selector slot, if available
- account/control link: "Open account controls" using `FlywheelNav.jump(context, DestinationId.models)`
- source context button: "Attach source context"
- prompt TextField
- Send turn button
- embedded ProviderSessionPane factual state card
- OperationPrivateAttachments when an operation snapshot exists
- Canon context status line using ChatContextOutcome.displayText
```

- [ ] **Step 3: Wire callbacks**

Map buttons to controller calls:

```dart
onSendTurn: () => controller.sendTurn(...),
onStop: controller.stop,
onResume: controller.resume,
onReconcile: controller.reconcile,
```

Disable send when controller is authorizing/running or `state.needsReconcile` is true. Disable resume without `state.canResume`.

- [ ] **Step 4: Add pending approval visibility**

Show `Awaiting one-operation approval` while `GatewayOperationController.pending` or proposal exists. If the sheet closes without approval, show `Approval denied or closed; no provider input was sent.`

- [ ] **Step 5: Run widget tests**

Run: `flutter test test/agent_view_native_session_test.dart test/provider_session_pane_test.dart`

Expected: PASS.

---

### Task 4: Source-linked handoff and attachments

**Files:**
- Modify: `desktop/lib/widgets/provider_session_surface.dart`
- Create: `desktop/lib/controllers/provider_session_source_controller.dart`
- Test: `desktop/test/provider_session_source_handoff_test.dart`

**Interfaces:**
- Consumes: `GatewaySourceContextApi.attach()`, `ContextMemoryPreflight.providerContext`, and provider turn `attachment_refs`.
- Produces: selected source-context package refs carried into `ProviderSessionTurnRequest.attachmentRefs` and visible in the grant sheet data refs or operation body.

- [ ] **Step 1: Write the attachment test**

Fake `/api/source-context/attach` to return a package ref such as `data_context.package:abc`. Tap `Attach source context`, send a turn, and assert `attachment_refs: ['data_context.package:abc']` appears in the prepared provider-session operation.

- [ ] **Step 2: Implement source attach controller**

Track `idle`, `inspecting`, `attached`, `failed`, and store `attachmentRefs` plus a short human status. Reject stale attach results if the prompt or root digest changes before attach returns.

- [ ] **Step 3: Show source handoff status**

Display exact refs and a does-not-prove line: `Attached refs are bounded context inputs; they do not prove provider read or tool success.`

- [ ] **Step 4: Run focused source tests**

Run: `flutter test test/provider_session_source_handoff_test.dart test/source_context_api_test.dart`

Expected: PASS.

---

### Task 5: Pending provider approvals and recovery controls

**Files:**
- Modify: `desktop/lib/widgets/provider_session_surface.dart`
- Modify: `desktop/lib/controllers/provider_session_operation_controller.dart`
- Modify: `desktop/lib/services/recovery_sources.dart`
- Test: `desktop/test/provider_session_recovery_ui_test.dart`

**Interfaces:**
- Consumes: provider progress phases `approval_replied`, `cancel_requested`, `cancel_acknowledged`, `close_indeterminate`, and `OperationSnapshot` state.
- Produces: UI states that distinguish approval pending, stop requested, close indeterminate, resume available, and reconcile required.

- [ ] **Step 1: Write recovery UI tests**

Cover these cases:

```text
- close_indeterminate disables Send turn and enables Reconcile.
- cancel_requested shows Stopping… and does not claim stopped.
- terminal failed with AGENT_NATIVE_INCOMPLETE creates a recovery item labelled provider-native session.
- malformed terminal result keeps Send turn disabled until Reconcile.
```

- [ ] **Step 2: Add provider recovery source**

Add `ProviderSessionRecoverySource` to `recovery_sources.dart` only if a durable local provider-session journal exists. If no durable source exists yet, keep this task to UI-only recovery state and record that missing recovery source as a remaining backend gap.

- [ ] **Step 3: Keep approval custody out of provider progress**

Do not approve native provider tool requests from progress events. Display them as pending facts until the backend exposes a grant-bound approval operation.

- [ ] **Step 4: Run recovery tests**

Run: `flutter test test/provider_session_recovery_ui_test.dart test/provider_session_controller_test.dart`

Expected: PASS.

---

### Task 6: Focused integration gates

**Files:**
- Existing touched files from Tasks 1-5 only.

**Interfaces:**
- Consumes: all preceding task deliverables.
- Produces: rereview-ready desktop native-session integration slice.

- [ ] **Step 1: Run focused Flutter tests**

Run:

```powershell
cd desktop
flutter test test/agent_mode_split_test.dart test/agent_view_native_session_test.dart test/provider_session_operation_controller_test.dart test/provider_session_source_handoff_test.dart test/provider_session_recovery_ui_test.dart test/provider_session_pane_test.dart test/provider_session_client_test.dart test/provider_session_controller_test.dart test/provider_session_operation_test.dart
```

Expected: PASS.

- [ ] **Step 2: Run scoped analyzer**

Run analyzer on the new/modified Dart files only.

Expected: `No issues found!`

- [ ] **Step 3: Run repo file and whitespace gates**

Run:

```powershell
cd ..
python scripts/check_file_gate.py
git diff --check
```

Expected: file gate clean and no whitespace errors in owned files.

## Self-review

- Spec coverage: conversations, streaming, approvals, attachments, cancellation, resume, recovery visibility, and Canon shared context all map to tasks. Real provider runtime acceptance remains outside this desktop plan.
- Placeholder scan: no placeholder task is left for execution; backend-only gaps are named as gaps rather than hidden behind UI work.
- Type consistency: the plan consistently uses `ProviderSessionOperationController`, `ProviderSessionSurface`, `ProviderSessionController`, `GatewayOperationController`, and `OperationController`.

## Implementation addendum - 2026-09-16

Root corrections applied in the implemented desktop slice:

- `GatewayOperations.watch()` now rejects progress events whose `provider_session.operation_ref` is present and differs from the watched operation ref.
- AgentView now exposes native sessions as a third header chip while preserving chat history/drafts, workspace-agent seed state, and native-session draft text by Journey/provider key across mode switches.
- The native-session surface fetches provider runtime binding from `POST /api/provider-sessions/binding` with the active Journey ref, event head, provider, workspace ref, selected model and permission scope before enabling send/resume/reconcile. If that read surface is missing, rejected, disabled or not Journey-bound, the UI shows binding unavailable and disables send. It does not accept user-entered workspace/config/capability digests and does not fabricate placeholders. Turn/resume/reconcile payloads carry the returned `provider_binding_ref` with the gateway-derived config/capability facts.
- Initial execution remains the existing Journey-bound gateway operation grant sheet. Live provider permission requests are read through `GET /api/provider-sessions/approvals?operation_ref=...`; approval and denial use the separate grant-bound `provider.session.approval.respond` action and `POST /api/provider-sessions/approvals/respond` endpoint rather than a display-only progress label.
- Runtime execution/readiness is still bounded by backend admission. Mocked desktop tests prove request shaping, mode preservation, and failure boundaries only.
