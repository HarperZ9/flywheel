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
- [x] Attach the private trace viewer and opt-in captions to accepted live and reopened Rowan operations without storing private trace bodies in generic state.
- [x] Map authenticated private `model_inference` lifecycle records to inference activity captions; keep provider summary unavailable until a supported summary channel lands.
- [x] Compose the Rowan Studio walkthrough through a non-null shared operation host, with the walkthrough retaining guidance/oracle state only.
- [x] Keep Android assistant work commands on the paired gateway plus supervised operation path, not the blocked Relay start route.
- [x] Add an absent-by-default tool protocol selector and freeze `tool_protocol: native` only after explicit user selection.
- [x] Treat failed reconnect and lost-response recovery as unavailable until a fresh snapshot succeeds; do not enable follow-up or submit a duplicate operation from cached data.
- [x] Preserve product positioning: Flywheel is the primary coding app and full flagship surface; Rowan operates Flywheel. This slice adds no voice-provider behavior or provider claims.

## Technical Approach
- Add `RowanOperationController` in `desktop/lib/controllers/rowan_operation_controller.dart` to compose `GatewayOperations`, `GatewayOperationController`, and `OperationController`.
- Extend `GatewayOperations` with a strict parser for `flywheel.gateway-operation-list/v1` from `GET /api/operations?journey_ref=...`.
- Extend `JourneySessionStore` with optional `operation_ref`, `operation_event_head_sha256`, and `operation_request_sha256` locators.
- Update the shell assistant sink and `AssistantPanel` so agent-channel requests prepare/start Rowan operations instead of Relay runs, while retaining the legacy Relay sink for explicit Relay surfaces/tests.
- Update shell dependencies/chrome to share one Rowan controller across assistant openings.
- Add `RowanOperationHostAdapter` so Studio walkthrough controls delegate to the same session-lived controller.
- Update AgentPanel/AgentGates to share the exact model/budget body shape.
- Add the `AgentToolProtocol` picker used by Rowan and AgentPanel. Compatibility mode omits `tool_protocol`; native mode sends the explicit `native` value for backend review.
- Add private operation attachments through the composed PR186/PR194 seams. The host passes trusted `OperationSnapshot`, optional terminal result and progress to projection helpers before rendering trace and caption panels.
- Recover lost initial POST responses by matching the persisted request hash across bounded Journey operation-list pages. If discovery is unavailable or the bound is exhausted, block duplicate starts until the operator explicitly dismisses the recovery blocker.

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
- `desktop/lib/models/agent_tool_protocol.dart` - compatibility/native protocol selector.
- `desktop/lib/widgets/operation_trace_projection.dart`, `operation_trace_entry.dart`, `operation_caption_entry.dart`, `operation_private_attachments.dart`, `agent_caption_panel.dart` - accepted private trace/caption attachment.
- `desktop/lib/models/agent_caption.dart` - inference lifecycle caption parser.
- Focused desktop tests for parser, root validation, no duplicate start, reconnect, denial, model invalidation, session-store private-data boundary, walkthrough host delegation, and mobile-sized shell controls.

## Success Criteria
- [x] Targeted Flutter tests pass for operation state/discovery, journey session store, agent panel gates, and Rowan assistant controller behavior.
- [x] `flutter analyze` completes with no issues.
- [x] Full Flutter suite is run once after root's scheduling slot opens.
- [x] Git diff shows no backend, shader, grant parser/approval renderer, or private trace file edits.

## Composition dependencies
- Exact `agent.run` model, token, timeout and remote-root execution depends on the backend exact-binding slice.
- Lost-first-response recovery depends on the operation discovery route.
- Private trace and caption rendering depend on the composed PR186 and PR194 GET-only reader seams.

## Verification
- `C:/flutter/bin/dart.bat format lib/controllers/rowan_operation_controller.dart lib/models/operation_models.dart test/operation_state_test.dart`
- `C:/flutter/bin/dart.bat format lib/widgets/assistant_panel.dart lib/assistant/assistant_executor.dart lib/assistant/assistant_intent.dart`
- `C:/flutter/bin/flutter.bat analyze` - no issues found.
- `C:/flutter/bin/flutter.bat test test/operation_state_test.dart test/operation_discovery_test.dart test/journey_session_store_test.dart test/journey_session_operation_store_test.dart test/rowan_operation_controller_test.dart test/agent_permission_defaults_test.dart test/agent_panel_continuation_handoff_test.dart test/plugin_grants_test.dart test/assistant_executor_test.dart test/journey_shell_test.dart test/gateway_autostart_shell_test.dart` - 50 checks passed before walkthrough composition.
- `C:/flutter/bin/flutter.bat test test/rowan_operation_controller_test.dart test/rowan_operation_host_adapter_test.dart test/rowan_walkthrough_controller_test.dart test/rowan_walkthrough_panel_test.dart test/navigation_reachability_test.dart test/journey_shell_test.dart test/gateway_autostart_shell_test.dart test/assistant_executor_test.dart` - 28 checks passed after walkthrough host composition.
- `C:/flutter/bin/flutter.bat test test/agent_caption_test.dart test/rowan_operation_protocol_recovery_test.dart test/rowan_private_attachments_test.dart test/agent_panel_tool_protocol_test.dart test/rowan_walkthrough_panel_test.dart` - focused trace, caption, tool protocol and recovery controls passed.
- `C:/flutter/bin/flutter.bat test test/agent_caption_test.dart test/rowan_operation_protocol_recovery_test.dart test/rowan_private_attachments_test.dart test/agent_panel_tool_protocol_test.dart test/rowan_walkthrough_panel_test.dart` - 18 focused checks passed after independent-review recovery, stale direct-ref, and wording fixes.
- `C:/flutter/bin/flutter.bat test test/rowan_operation_controller_test.dart test/agent_caption_test.dart test/rowan_operation_protocol_recovery_test.dart test/rowan_operation_recovery_guards_test.dart test/rowan_private_attachments_test.dart test/agent_panel_tool_protocol_test.dart test/rowan_walkthrough_panel_test.dart` - 24 focused checks passed after denial-locator, failed-reconnect, paged recovery, stale direct-ref, trace attachment, caption parser, and tool-protocol fixes.
- `C:/flutter/bin/flutter.bat analyze` - no issues found after the final controller/session-locator split.
- `C:/flutter/bin/flutter.bat test` - full desktop Flutter suite passed with 1056 checks and 8 skips after trace/caption/tool-protocol composition and review fixes.
- `git diff --check` - no patch whitespace errors; Flutter platform registrant line-ending churn was restored and left out of the patch.

## Status: IMPLEMENTED; INDEPENDENT REVIEW FIXES APPLIED
