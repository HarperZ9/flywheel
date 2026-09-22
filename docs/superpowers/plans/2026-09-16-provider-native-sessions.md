# Provider-native sessions implementation plan

For agentic workers: use the subagent-driven-development or executing-plans skill
to implement and review each bounded task.

**Goal:** Deliver native Codex and Claude sessions with recoverable execution and
shared source-linked context, then measure improvements over baseline workflows.

**Architecture:** Extend the existing provider clients and gateway/desktop agent
surfaces. Keep native IDs and execution policy distinct from normalized UI events.
Canon remains shared context authority.

**Tech stack:** Python stdlib engine, official provider local protocols and
supported adapters, Flutter desktop, existing Canon API/MCP.

**Spec:** `docs/superpowers/specs/2026-09-16-provider-native-sessions-design.md`.

## Global constraints

- No learned model on the accept path; verifier remains stdlib-only.
- No new runtime dependency for the first Codex transport increment.
- No file over 300 lines. Preserve public instruction and claim gates.
- Preserve native execution holds until their actual policy boundary is checked.
- No account readiness, installation or release claims from mocked tests.
- Persistent sessions and their listed controls are the baseline, not completion
  of the user requirement to exceed that baseline.

## Task 1: Codex bidirectional transport and typed session client

**Owner:** one implementation owner after final source-map handoff.

**Existing files:** `harness/codex_app_server_client.py`,
`tests/test_codex_app_server_client.py`,
`tests/test_codex_app_server_notifications.py`.

**New files:** small session/transport helpers and targeted tests, named in the
owner handoff before edits. Do not add a second account/auth implementation.

**Consumes:** official JSON-RPC frames and generated installed-runtime schemas.
**Produces:** typed thread/turn requests, separate notification and server-request
delivery, correlated authorized replies, and explicit transport failure state.

- [x] Add failing interleaving/server-request/EOF/overflow tests against the real
  transport logic with a deterministic in-memory or child-process server.
- [x] Implement response demultiplexing, bounded event delivery and serialized
  writes; retain the account-only notification default.
- [x] Add initialize/initialized and typed thread/turn operations matched to the
  generated schema. Unknown approval requests never become automatic approvals.
- [x] Verify account regressions, session controls, late/duplicate responses and
  malformed frames. Independently review failure handling and custody.
- [x] Run an isolated no-generation real-runtime handshake and record limits.

September 16 checkpoint: 35 focused transport/client tests pass, independent
bounded rereview passes, and the installed Codex 0.144.6 app server accepts the
new client's initialize/initialized exchange. The owned process exits on stdin
EOF with code 0 and the reader joins. No account query, thread, model turn or
tool request was started. Closing a stream cannot guarantee cancellation of a
frame already being written; ambiguous outbound state requires reconciliation.
These checks do not establish native execution policy or durable session readiness.

## Task 2: Execution and recovery binding

Reuse existing gateway agent/session, grant and Journey mechanisms after the
source maps identify their extension points. Do not remove the direct CLI hold
to make a green test. Bind workspace, provider configuration, permission scope,
native session IDs and owned process lifecycle. Add restart reconciliation and
uncertain-outcome state before enabling automatic reconnection.

- [ ] Freeze interfaces and exact file ownership from the completed source maps.
- [ ] Test hostile configuration changes, approval replay, disconnect during a
  side effect, interruption races and missing native history.
- [ ] Run a synthetic real session with two turns and a bounded tool operation.

## Task 3: Claude persistent adapter

Choose the supported persistent interface using the Claude source map and
installed runtime evidence. Reuse existing Claude account and execution policy.
Implement native session identity, streaming control, tool/approval exchange,
cancel and resume against the same normalized contract without erasing native
differences. Retain separate authentication requirements for each supported path.

- [ ] Freeze exact files/interfaces and verify provider/runtime compatibility.
- [ ] Test the shared failure controls plus Claude-specific permissions behavior.
- [ ] Record a real synthetic multi-turn/restart session acceptance.

## Task 4: Desktop and shared-context integration

Reuse the existing account controls, agent events and chat/Journal stores. Add
native session navigation, pending requests, attachments, steer/stop/resume and
recovery visibility. Route shared context references through Canon. Do not create
a competing memory store or silently import unrelated provider histories.

- [ ] Map and assign exact client/controller/view files after adapter interfaces
  freeze, then run Flutter analysis and tests.
- [ ] Exercise native UI against real provider sessions and interrupt/restart.
- [ ] Test a source-linked provider/local-model handoff with missingness controls.

## Task 5: Beyond-baseline evaluation and release

- [ ] Predeclare matched workload and budgets for latency, continuity, approval
  burden, tool outcomes, attachment fidelity and parallel-agent coordination.
- [ ] Preserve raw bounded evidence and independent failure controls.
- [ ] Run complete source gates on composed changes, then build and accept exact
  candidate bytes. Keep source shipping separate from installation/publication.

Tasks 2-5 require more detailed file-level plans after Task 1 and the source maps.
They are required unfinished work, not claims that these features are delivered.
