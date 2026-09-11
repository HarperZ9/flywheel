# Rowan live walkthrough

The Studio view includes the Rowan presenter and a guided walkthrough mounted on the shared Rowan operation host. The walkthrough owns the versioned retry-policy scenario, guidance state, terminal semantic oracle, and operation locator checks. It does not own the native operation lifecycle.

The live panel receives a `RowanWalkthroughOperationHost` backed by the session-lived `RowanOperationController`. Endpoint, execution mode, exact model, workspace root, approval, start, stop, reconnect, recovery, progress, snapshots, private trace attachment, captions, and terminal results all flow through that shared host. The walkthrough selector can switch between the API agent path and the `native_cli_session` path, but the shared controller still builds and reviews the operation request.

The scenario is versioned as `rowan.retry-policy.read-only` / `2026-09-10.1`. The goal asks for a read-only review of the synthetic retry policy task. The oracle expectation and defect label stay outside the start request and run only against a terminal result returned by the shared host.

Execution boundaries:

- The walkthrough panel does not create `GatewayOperations`, `GatewayOperationController`, `OperationController`, grant storage, task storage, direct POST paths, or an `agent.run` body.
- Readiness requires endpoint, supported execution mode, exact model, input root, and a current Journey head before the panel asks the shared host to start. The host remains responsible for canonical operation construction and Journey-bound approval.
- In API mode the UI can review tool protocol and API token/effort controls. In native CLI session mode the UI filters to the admitted `claude-cli` endpoint, shows CLI-owned auth, disables exec, labels output token bounds unsupported, and never enables Codex CLI.
- Guidance pause only stops walkthrough guidance highlighting. It does not stop an executing operation. The Stop button delegates to the shared host.
- Provider-visible operation captions attach through `captionBuilder`, which receives the same operation host used by the walkthrough. Hidden internal chain-of-thought is labelled unavailable and is not fabricated or exported.
- Bounded follow-up is exposed through `onReviewFollowUp` only after the oracle passes and the same terminal operation record is reopened through the host.
- Offline host, denied approval, interrupted stream, missing stored record, wrong semantic answer, and unsupported native CLI profile remain visible as walkthrough outcomes.

Verification in this branch:

- `test/rowan_walkthrough_controller_test.dart` checks denial handling, semantic oracle behavior, and reopen locator matching without any operation lifecycle state.
- `test/rowan_walkthrough_panel_test.dart` uses a fake shared operation host to verify host delegation, duplicate-submission blocking, reopen gating, caption attachment, and execution-mode selection through the shared host.
- `test/rowan_operation_protocol_recovery_test.dart` verifies lost-response recovery by request digest across operation-list pages and keeps the persisted execution mode on recovery.

Those tests simulate the shared host and gateway. They do not claim acceptance on a real provider, real native device, or physical Android bridge.