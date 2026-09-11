# Rowan live walkthrough

The Studio view now mounts a guided Rowan walkthrough panel beside the Rowan
presenter. It prepares one supervised `agent.run` operation for a read-only
synthetic retry-policy review, watches the operation through the existing
gateway operation stream, evaluates the terminal answer with a separate semantic
oracle, and requires the same operation record to reopen before a bounded
follow-up reviewer can attach.

The scenario is versioned as `rowan.retry-policy.read-only` /
`2026-09-10.1`. The model input contains only the review goal, selected endpoint,
selected model, input root, budgets, and read-only execution flags. The oracle
expectation and defect label are intentionally not included in the operation
body.

Execution boundaries:

- The panel uses the existing Journey-bound gateway approval scope and existing
  `GatewayOperations` start/snapshot/cancel APIs. It does not create a runner,
  direct POST path, task database, or grant database.
- Readiness requires endpoint, explicit model, input root, and a current Journey
  head. Missing Journey selection, denied approval, interrupted stream, missing
  stored record, and wrong semantic answer remain visible.
- Guidance pause only stops walkthrough guidance highlighting. It does not stop
  an executing operation. The Stop button uses the existing approved cancel path.
- Provider-visible reasoning captions attach through `captionBuilder`. The panel
  always labels hidden internal chain-of-thought as unavailable and does not
  persist or export caption originals.
- Bounded follow-up is exposed through `onReviewFollowUp` after semantic oracle
  pass and stored-record reopen. A continuation provider must attach there; the
  panel does not fabricate private context.

Verification in this branch:

- `test/rowan_walkthrough_controller_test.dart` checks the scenario operation
  body, denial handling, semantic oracle, and reopen gate.
- `test/rowan_walkthrough_panel_test.dart` uses mocked gateway endpoints,
  model roster, SSE terminal event, and snapshot lookup to exercise the UI
  wiring. It verifies the dispatched supervised `agent.run` body and the
  follow-up gate.

Those widget tests simulate the gateway transport. They do not claim that a live
model was run or that the backend enforced `model`, `max_tokens`, or `timeout_s`;
that enforcement belongs to the native execution binding path.
