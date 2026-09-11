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
- [x] Compose the Rowan Studio walkthrough through a non-null shared operation host, with the walkthrough retaining guidance/oracle state only.
- [x] Keep Android assistant work commands on the paired gateway plus supervised operation path, not the blocked Relay start route.

## Technical Approach
- Add `RowanOperationController` in `desktop/lib/controllers/rowan_operation_controller.dart` to compose `GatewayOperations`, `GatewayOperationController`, and `OperationController`.
- Extend `GatewayOperations` with a strict parser for `flywheel.gateway-operation-list/v1` from `GET /api/operations?journey_ref=...`.
- Extend `JourneySessionStore` with optional `operation_ref`, `operation_event_head_sha256`, and `operation_request_sha256` locators.
- Update the shell assistant sink and `AssistantPanel` so agent-channel requests prepare/start Rowan operations instead of Relay runs, while retaining the legacy Relay sink for explicit Relay surfaces/tests.
- Update shell dependencies/chrome to share one Rowan controller across assistant openings.
- Add `RowanOperationHostAdapter` so Studio walkthrough controls delegate to the same session-lived controller.
- Update AgentPanel/AgentGates to share the exact model/budget body shape.

## Files to Modify
- `desktop/lib/controllers/rowan_operation_controller.dart` - new shared controller.
- `desktop/lib/client/gateway_operations.dart` - operation discovery client.
- `desktop/lib/models/operation_models.dart` - discovery response model.
- `desktop/lib/models/gateway_grant_models.dart` - remote agent root validation.
- `desktop/lib/services/journey_session_store.dart` - optional operation locator.
- `desktop/lib/assistant/assistant_executor.dart` - supervised operation sink.
- `desktop/lib/widgets/assistant_panel.dart` - Rowan operation controls/status.
- `desktop/lib/shell/flywheel_dependencies.dart`, `flywheel_shell.dart`, `shell_chrome.dart`, `view_factory.dart` - shared lifetime and scope injection.
- `desktop/lib/controllers/rowan_operation_host_adapter.dart`, `rowan_walkthrough_operation_host.dart`, `rowan_walkthrough_controller.dart` - walkthrough host seam and oracle-only walkthrough state.
- `desktop/lib/views/studio_view.dart`, `desktop/lib/widgets/rowan_studio_prelude.dart`, `rowan_walkthrough_panel.dart` - Studio host attachment.
- `desktop/lib/ide/agent_panel.dart`, `agent_gates.dart` - exact model/budget controls.
- Focused desktop tests for parser, root validation, no duplicate start, reconnect, denial, model invalidation, session-store private-data boundary, walkthrough host delegation, and mobile-sized shell controls.

## Success Criteria
- [x] Targeted Flutter tests pass for operation state/discovery, journey session store, agent panel gates, and Rowan assistant controller behavior.
- [x] `flutter analyze` completes with no issues.
- [x] Full Flutter suite is run once after root's scheduling slot opens.
- [x] Git diff shows no backend, shader, grant parser/approval renderer, or private trace file edits.

## Composition dependencies
- Exact `agent.run` model, token, timeout and remote-root execution depends on the backend exact-binding slice.
- Lost-first-response recovery depends on the operation discovery route.
- Private trace and caption rendering attach through their existing GET-only seams when those branches compose.

## Verification
- `C:/flutter/bin/dart.bat format lib/controllers/rowan_operation_controller.dart lib/models/operation_models.dart test/operation_state_test.dart`
- `C:/flutter/bin/dart.bat format lib/widgets/assistant_panel.dart lib/assistant/assistant_executor.dart lib/assistant/assistant_intent.dart`
- `C:/flutter/bin/flutter.bat analyze` - no issues found.
- `C:/flutter/bin/flutter.bat test test/operation_state_test.dart test/operation_discovery_test.dart test/journey_session_store_test.dart test/journey_session_operation_store_test.dart test/rowan_operation_controller_test.dart test/agent_permission_defaults_test.dart test/agent_panel_continuation_handoff_test.dart test/plugin_grants_test.dart test/assistant_executor_test.dart test/journey_shell_test.dart test/gateway_autostart_shell_test.dart` - 50 checks passed before walkthrough composition.
- `C:/flutter/bin/flutter.bat test test/rowan_operation_controller_test.dart test/rowan_operation_host_adapter_test.dart test/rowan_walkthrough_controller_test.dart test/rowan_walkthrough_panel_test.dart test/navigation_reachability_test.dart test/journey_shell_test.dart test/gateway_autostart_shell_test.dart test/assistant_executor_test.dart` - 28 checks passed after walkthrough host composition.
- `git diff --check` - no patch whitespace errors; Flutter platform registrant line-ending churn was restored and left out of the patch.

## Status: IMPLEMENTED; FULL FLUTTER SUITE PENDING AFTER REBASE
