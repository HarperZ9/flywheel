# Spec: Rowan Native Operator UI

## Objective
Make Rowan present and control the existing supervised `agent.run` operation from the native desktop/mobile shell. The user should be able to choose an endpoint and exact model, review workspace and budgets, approve once, observe, reconnect, cancel, reopen by Journey locator, and continue with explicit review. The UI must not start Relay goal-only runs or persist private trace bodies in generic assistant/session state.

## Requirements
- [x] Replace Rowan's work-task sink with the grant-bound operation lifecycle already used by AgentPanel.
- [x] Keep the Rowan controller shell/session-lived so closing and reopening the panel does not create a second operation or lose observation state.
- [x] Include endpoint, optional exact model ID, workspace root, effort/max steps, token budget, timeout, write/exec grants and optional continuation context in the canonical `agent.run` body.
- [x] Reset selected model when endpoint changes and invalidate pending approval when operation inputs change.
- [x] Reconnect by `snapshot` then `watch(after:lastSequence)`; do not POST a new task after SSE interruption.
- [x] Add client support for the Journey-filtered operation metadata list; treat list rows as navigation hints and fetch snapshots before reconnect/cancel.
- [x] Persist only Journey operation locators and UI hints in the local session store; no goals, prompts, results, trace bodies or public chat/speech events.
- [x] Permit remote gateway workspace roots for `agent.run.root` while keeping other secret/path validation closed.
- [x] Keep trace integration GET-only and based on accepted snapshots when the trace viewer branch composes.

## Technical Approach
- Add `RowanOperationController` in `desktop/lib/controllers/rowan_operation_controller.dart` to compose `GatewayOperations`, `GatewayOperationController`, and `OperationController`.
- Extend `GatewayOperations` with a strict parser for `flywheel.gateway-operation-list/v1` from `GET /api/operations?journey_ref=...`.
- Extend `JourneySessionStore` with optional `operation_ref`, `operation_event_head_sha256`, and `operation_request_sha256` locators.
- Update the shell assistant sink and `AssistantPanel` so agent-channel requests prepare/start Rowan operations instead of Relay runs, while retaining the legacy Relay sink for explicit Relay surfaces/tests.
- Update shell dependencies/chrome to share one Rowan controller across assistant openings.
- Update AgentPanel/AgentGates to share the exact model/budget body shape.

## Files to Modify
- `desktop/lib/controllers/rowan_operation_controller.dart` - new shared controller.
- `desktop/lib/client/gateway_operations.dart` - operation discovery client.
- `desktop/lib/models/operation_models.dart` - discovery response model.
- `desktop/lib/models/gateway_grant_models.dart` - remote agent root validation.
- `desktop/lib/services/journey_session_store.dart` - optional operation locator.
- `desktop/lib/assistant/assistant_executor.dart` - supervised operation sink.
- `desktop/lib/widgets/assistant_panel.dart` - Rowan operation controls/status.
- `desktop/lib/shell/flywheel_dependencies.dart`, `flywheel_shell.dart`, `shell_chrome.dart` - shared lifetime and scope injection.
- `desktop/lib/ide/agent_panel.dart`, `agent_gates.dart` - exact model/budget controls.
- Focused desktop tests for parser, root validation, no duplicate start, reconnect, denial, model invalidation and session-store private-data boundary.

## Success Criteria
- [x] Targeted Flutter tests pass for operation state/discovery, journey session store, agent panel gates, and Rowan assistant controller behavior.
- [x] `flutter analyze` completes with no issues.
- [x] No full Flutter suite is run unless root explicitly schedules it.
- [x] Git diff shows no backend, shader, Studio walkthrough, grant parser/approval renderer, or private trace file edits.

## Blockers
The assigned worktree was missing and was recreated from the exact ed41 baseline. `origin/main` had advanced by the time work began, so this branch intentionally uses the task's named baseline, not the current remote tip.

## Verification
- `C:/flutter/bin/dart.bat format lib/controllers/rowan_operation_controller.dart lib/models/operation_models.dart test/operation_state_test.dart`
- `C:/flutter/bin/dart.bat format lib/widgets/assistant_panel.dart lib/assistant/assistant_executor.dart lib/assistant/assistant_intent.dart`
- `C:/flutter/bin/flutter.bat analyze` - no issues found.
- `C:/flutter/bin/flutter.bat test test/operation_state_test.dart test/journey_session_store_test.dart test/rowan_operation_controller_test.dart test/agent_permission_defaults_test.dart test/agent_panel_continuation_handoff_test.dart test/plugin_grants_test.dart test/assistant_executor_test.dart` - 42 checks passed.
- `git diff --check` - no patch whitespace errors; Flutter platform registrant line-ending churn was restored and left out of the patch.

## Status: IMPLEMENTED; AWAITING INDEPENDENT REVIEW BEFORE COMMIT/PUSH
