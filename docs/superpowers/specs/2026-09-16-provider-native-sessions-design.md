# Provider-native sessions and continuity

Status: implementation design. No session parity or release acceptance is claimed.

## Outcome

People should work with Codex and Claude inside Flywheel without losing the
session capabilities that make their native clients useful. Persistent
conversations, streaming, tool calls, approvals, attachments, cancellation and
resume are entry requirements. The additional value is recoverable work across
providers and local models, shared context, inspectable effects, and coordination.

This extends the existing engine, Journey, account, agent and Canon surfaces.
It does not introduce another memory product or treat a one-shot response as a
native session. Provider limitations remain visible and do not silently reduce
the required product scope.

## Checked starting point

- The existing Codex app-server client handles accounts and model discovery. Its
  transport filters notifications to login completion and cannot yet serve as a
  concurrent bidirectional session transport.
- Native direct Codex CLI execution is held because configuration isolation has
  not been admitted. This hold remains until the execution boundary is checked.
- Codex app-server protocol generation from CLI 0.144.6 exposes thread start,
  resume, read, list and fork; turn start, steer and interrupt; and approval
  requests. Schema presence does not prove runtime or account availability.
- Claude's one-shot route has returned a response. Its persistent session and
  desktop coverage require their own source map and acceptance.

## Architecture

Keep three responsibilities separate:

1. Provider adapters retain native account, thread/session, turn and item IDs,
   raw event types, capability/version facts and provider-owned authentication.
2. Flywheel coordinates execution, permission decisions, event delivery,
   recovery and the native UI through existing gateway and Journey facilities.
3. Canon owns shared project context, decisions and source references. Provider
   sessions link to those records. Index remains the gatherer; it does not become
   another authority store.

The shared UI uses a normalized view with a reference to the original provider
event. Normalization must not invent reasoning, approval, completion, rollback,
or model identity. Unsupported and experimental capabilities remain typed.

Use Codex's official local app-server protocol for its persistent session path.
Evaluate Claude's official persistent interfaces against the installed runtime
and existing session code before choosing its implementation. Native-client
account use and API/SDK use are distinct authentication paths; do not extract or
repurpose provider tokens. App-specific proprietary features require an exposed
supported interface or an explicit capability gap.

## Baseline and additional acceptance

| Category | Entry requirement | Additional acceptance |
| --- | --- | --- |
| Conversations | Stable native ID and multi-turn context | Restart restores decisions, drafts, references and pending work; cross-provider handoff records what transferred and what did not. |
| Streaming | Native text/tool events shown while running | Bounded buffering, explicit loss detection, ordered recovery, responsive steering, and measured delivery delay under load. |
| Tools | Native calls and results retained | Agent ownership, effect receipts and dependency-aware coordination; a missing result cannot become success. |
| Approvals | Correct native request and response | Exact action/context binding, expiry, revocation and stale-response rejection; grant scope is inspectable without repetitive prompts for already authorized work. |
| Attachments | Supported text/image/file input | Source hash and transformation provenance, access boundaries, persistent references and a clear report of missing or unsupported content. |
| Cancellation | Interrupt request reaches the provider | Report acknowledged stop, retained effects and unresolved operations separately; do not label a request to stop as completed cancellation. |
| Resume | Reopen the native session | Reconcile history after disconnect/crash before resending; uncertain side effects require reconciliation rather than an automatic duplicate. |

Additional outcomes include parallel-agent steering with explicit ownership,
Canon retrieval before declaring context missing, and provider/local-model
handoffs that preserve source links and expose lossy transformations.

## Transport and authority requirements

- Correlate replies by request ID under concurrent requests. Never discard a
  reply merely because another caller is currently waiting.
- Separate client replies, notifications and server requests. A server request
  must never be mistaken for a response to a client request with the same ID.
- Serialize writes. Bound frame size, pending requests and event queues. Queue
  overflow, malformed frames and disconnects produce explicit incomplete state.
- Complete the documented initialize/initialized handshake. Do not enable
  experimental methods merely because the current account probe does so.
- Reply to pending approvals only through an authorized, correlated decision.
  Unknown or repeated server requests cannot silently receive approval.
- Preserve account-only notification behavior for existing callers while adding
  a session-aware surface. Share implementation rather than cloning clients.
- Provider project settings, hooks, MCP servers and plugins affect execution.
  Inspect effective configuration and enforce the selected execution boundary;
  removing the existing hold alone is not an implementation.
- Recovery identifiers are provider, native session, turn, item and request IDs.
  A transport cannot guarantee exactly-once external side effects. Reconcile
  unknown outcomes and avoid automatic replay of non-idempotent operations.
- Keep secrets out of public errors, evidence and Canon records. User-selected
  attachment content is scoped input, not permission to ingest unrelated files.

## Verification

First use deterministic protocol fixtures for interleaved requests, server
approvals, stream overflow, malformed frames, EOF, timeouts, duplicate responses,
and cancellation races. Retain existing account/auth tests.

Then use the installed official runtime for a no-generation handshake/schema
check in isolated state. This is compatibility evidence only. Follow with an
authorized synthetic workspace session that performs two turns, a bounded tool
action, an approval round trip, interruption and a process restart/resume.
Acceptance records source, executable version, configuration scope, native IDs,
event coverage, effects and unresolved outcomes without persisting credentials.

Native desktop acceptance must show the same events and recovery state. A
transport unit test, a fake server or a successful one-shot route cannot close
this requirement. Cross-provider handoff must use a synthetic source-linked
context packet and test a missing-artifact control.

Compare the native provider path and Flywheel using matched tasks, account/model
selection, permissions and environment. Measure completion quality, event loss,
recovery correctness, approval burden, latency distribution and resource use.
Declare budgets and workloads before measurement. No speed or superiority claim
follows from a single successful session.

Reviewers must be able to explain the data flow, authorization owner, storage
choice, rejected alternatives and known failure boundaries using this design
and the corresponding code. Each material claim needs a counterexample that
the checks would reject. A valid event hash alone cannot establish that a tool
effect succeeded or that a provider respected the requested permissions.

Recovery scenarios include delayed or stale approvals, authority revocation,
concurrent file changes, disconnect after input acceptance, disconnect after a
tool effect, and stale context on resume. Fixtures expose independent task
outcomes; the provider's final text cannot be the sole success oracle. Start
with deterministic transport cases and extend to actual native sessions only
after the execution boundary is validated.

## Delivery and limits

Deliver reviewed increments: transport/client, bounded session execution and
recovery, gateway/desktop integration, then cross-provider coordination and
comparative acceptance. Each increment must state the remaining baseline and
additional requirements. An internal transport increment is not an available
consumer feature and cannot be used to declare application 1.0 ready.

Official references:

- [Codex app-server](https://learn.chatgpt.com/docs/app-server)
- [Claude streaming input](https://code.claude.com/docs/en/agent-sdk/streaming-vs-single-mode)
- [Claude sessions](https://code.claude.com/docs/en/agent-sdk/sessions)
- [Claude permissions](https://code.claude.com/docs/en/agent-sdk/permissions)
