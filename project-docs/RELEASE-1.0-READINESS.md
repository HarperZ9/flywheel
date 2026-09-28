# Flywheel 1.0 readiness

Updated: 2026-09-15. This register tracks readiness; it is not a release receipt.

## Release decision

Flywheel 1.0 must provide a usable evaluator workflow from import and execution
through source review, interruption, persistence, and reviewer handoff. Tests of
individual components do not establish the installed workflow or external value.
The earlier register treated the completed 0.6.2 checklist as sufficient for a
1.0 promotion. That conclusion is superseded by the acceptance criteria below.

Source integration and publication are operator-authorized work. Readiness is a
technical gate, not a request for another general permission. Any specific
installation or security-sensitive interaction retains its own boundary.

## Current version boundary

- This version-alignment branch declares source metadata for a 1.0.0 candidate.
  That is not a release receipt and does not establish readiness by itself.
- Latest published application release checked on September 13 is
  [0.6.2](https://github.com/HarperZ9/flywheel/releases/tag/v0.6.2).
- An existing installed 0.6.2 client does not validate later source changes.
- A local development installer has been compiled. It does not establish a
  published 1.0.0 tag, GitHub Release, PyPI package or installed acceptance.
- Source checks, hosted CI, packaged artifacts, installed acceptance, publication,
  and external use require separate evidence.

## Current candidate holds

- Full Python acceptance passed locally after the gateway-auth and acceptance
  recorder repairs, with recorded inputs unchanged. Bind the gate to the final
  integrated source and rerun it if relevant inputs change.
- Full Flutter acceptance on the candidate line must retain generated-file
  reconciliation evidence when generated files change only by line endings.
- The local development candidate has app, engine, CRT, installer and SHA256SUMS
  evidence. Rebuild from the final accepted source commit and bind its manifests
  before installed acceptance; a dirty composition's base commit is insufficient.
- Installed acceptance must cover preflight, metadata, full engine restart, and
  Inspect import/reopen receipts on the same candidate bytes.

## Acceptance matrix

The [architectural mission](../docs/ARCHITECTURAL-MISSION.md) couples evaluation
with the general-user harness. The following rows retain the expanded native
application requirements alongside the existing reviewer and release gates.

| Workflow | Existing implementation or evidence | Remaining release acceptance |
|---|---|---|
| Inspect evidence review | [Import and source references](../docs/INSPECT-EVIDENCE.md); score-edit history, missing versus empty history, and versioned fixture drift landed in [PR238](https://github.com/HarperZ9/flywheel/pull/238). | Import, inspect exact source values, persist, close, and reopen through the installed application on the candidate bytes. |
| External task interoperability | [METR/Inspect task-image controls](https://github.com/HarperZ9/flywheel/pull/234) distinguish correct, wrong, and fallback answers. | Record supported versions and environment; hold scorer independence and broader compatibility claims unless separately tested. |
| Terminal action evidence | [Gateway effect evidence](../docs/GATEWAY-EFFECT-EVIDENCE.md) binds retained observations to the accepted private trace and terminal lifecycle. | Complete source integration and candidate acceptance; exercise cancelled, failed, completed, legacy, and unavailable-source states in the installed reviewer workflow. |
| Process review and incident simulation | Existing [incident-simulation evaluation](../docs/INCIDENT-SIM-EVALUATION.md), process-audit packets, and false-success controls. | Demonstrate a complete reviewer handoff with exact evidence, missingness, and the same bounded conclusions through CLI/API and Desktop. |
| Trace and Journey persistence | Existing retained trace and Journey evidence paths. | Verify restart, authorized source access, changed/missing evidence, read failures, and recovery on installed bytes. |
| Provider operation | Existing provider adapters and credential handling. | Test each advertised provider/auth route in its supported configuration. Credential presence is not successful inference or a provider guarantee. |
| Rowan interaction | Recorded cue library, animation and operation bindings are in candidate source. | On candidate bytes, verify user-controlled playback, truthful event predicates, captions, mute/stop, interruption and recovered-event behavior. Voice is not evidence of task correctness. |
| Navigable chat | Candidate outline, search, source links, bookmarks and notes preserve original message targets. | Exercise a long conversation, streaming, keyboard access, resizing, restart and missing targets in the compiled app without draft or history loss. |
| Model selection and cross-provider orchestration | Candidate route discovery and child-route handling. | Verify each supported authentication path, explicit model selection, independent child authority, cancellation and provenance. Synthetic routing does not prove live provider operation. |
| Studio and model observations | Candidate native visual/sound instruments, live-screen delivery and accountable actuation. | Verify actual capture-to-model and action-to-effect bindings, selected-source controls, rendered frames and device playback. Text-mediated observations do not establish native model senses. |
| API/MCP interoperability | Shared operation and receipt surfaces in candidate source. | Check supported protocol versions, equivalent results and permission denials on the same artifacts. Preserve necessary session state and report unsupported paths. |
| Windows packaging and upgrade | Existing frozen engine, installer, metadata, payload hashes, and launch checks. | Build from the accepted commit; retain complete payload manifests; verify install, launch, engine restart, upgrade behavior, and claimed recovery scope. |
| Android and Relay/Plexus handoff | Bundled components and source-level paths exist. | Physical device, network, identity, interruption, and resume acceptance remains separate. Bundle presence is not an end-to-end handoff result. |
| Public claims | [Independence register](../docs/INDEPENDENCE.md), versioned release notes, public source and fixtures. | Align all claims with the final candidate's actual coverage. A green source suite does not establish adoption, paid use, or regulatory approval. |

## Purple-team acceptance

Adversarial findings must feed named defensive artifacts. For this release,
prioritize misleading-success cases in ordinary coding and evaluation workflows:

1. Cancel a task after a retained write. Confirm that cancellation is not shown
   as rollback or absence of effects.
2. Supply altered or self-hashed worker evidence. Confirm that it cannot replace
   backend-derived evidence or gain authority merely by being self-consistent.
3. Change scoring history while preserving the final score. Confirm that drift
   and exact source references remain visible.
4. Pass untrusted content through a tool boundary. Check the enforced permission
   and resulting effects independently of the model's account of its intent.

Use owned fixtures and separately controlled observations for actual effects.
A coherent fabricated trace with matching hashes must not prove execution.
Retained traces establish a reference for consistency; they do not establish
complete observation, independent custody, or semantic truth.

Private adversarial tooling is not a public release requirement. Public examples
must be bounded, reproducible defensive controls without private runtime data.

## Reviewer usefulness

Compare Flywheel review with a native export plus a clear checklist, giving both
reviewers the same evidence. Measure missed issues, false accepts, correct unknown
judgments, and review time. Counterbalance case order and retain negative results.
A transcript-only condition can measure missing evidence, but it is not a fair
primary baseline for claims about the interface's usefulness.

Report scenario and metric coverage, omitted cases, shared evaluator dependencies,
and transfer limits beside results. User satisfaction or agreement is a separate
measure from evidence support and correctness. Small synthetic experiments do not
establish general model safety or superiority over another harness.

## Completion evidence

Before a 1.0 readiness claim, retain:

- The accepted source commit, review outcome, and exact-head CI results.
- Full engine and client gate results applicable to the changed source.
- Source-bound app, engine, and installer manifests with matching hashes.
- Installed workflow results, including source review, restart, and failure states.
- Explicit holds for untested providers, platforms, hardware, or recovery claims.
- Final aligned version metadata, release notes, and public claim checks.

Publication and external use are subsequent states. Do not mark either complete
from a local build or a sent outreach message. Keep this matrix open until its
required workflows have evidence or their unsupported promises are removed from
the release scope.
