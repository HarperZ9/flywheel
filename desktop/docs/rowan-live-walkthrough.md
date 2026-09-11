# Rowan live walkthrough

The Studio view includes the Rowan presenter and a draft guided walkthrough
entry point. The walkthrough owns the versioned retry-policy scenario, guidance
state, terminal semantic oracle, and operation locator checks. It no longer owns
the native operation lifecycle.

The live panel is mounted only when the shell passes a shared
`RowanWalkthroughOperationHost`. That host is the seam for the native
session-lived Rowan operation controller: endpoint/model/root selection,
start-once approval, stop, reconnect, recovery, progress, snapshots, and terminal
results all come from the shared controller. PR #193 should stay draft until the
native operator UI commit provides that host or an adapter for it.

The scenario is versioned as `rowan.retry-policy.read-only` /
`2026-09-10.1`. The goal asks for a read-only review of the synthetic retry
policy task. The oracle expectation and defect label are kept outside the start
request and run only against a terminal result returned by the shared host.

Execution boundaries:

- The walkthrough panel does not create `GatewayOperations`,
  `GatewayOperationController`, `OperationController`, grant storage, task
  storage, direct POST paths, or an `agent.run` body.
- Readiness requires endpoint, exact model, input root, and a current Journey
  head before the panel asks the shared host to start. The host remains
  responsible for canonical operation construction and Journey-bound approval.
- Guidance pause only stops walkthrough guidance highlighting. It does not stop
  an executing operation. The Stop button delegates to the shared host.
- Provider-visible reasoning captions attach through `captionBuilder`, which is
  passed the same operation host used by the walkthrough. Hidden internal
  chain-of-thought is labelled unavailable and is not fabricated or exported.
- Bounded follow-up is exposed through `onReviewFollowUp` only after the oracle
  passes and the same terminal operation record is reopened through the host.
- Offline host, denied approval, interrupted stream, missing stored record, and
  wrong semantic answer remain visible as walkthrough outcomes.

Verification in this branch:

- `test/rowan_walkthrough_controller_test.dart` checks denial handling,
  semantic oracle behavior, and reopen locator matching without any operation
  lifecycle state.
- `test/rowan_walkthrough_panel_test.dart` uses a fake shared operation host to
  verify host delegation, duplicate-submission blocking, reopen gating, caption
  attachment, and the draft prelude state.

Those tests simulate the shared host. They do not claim that a live model ran or
that the native controller commit has been composed into this branch.
