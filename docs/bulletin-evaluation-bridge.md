# Check a Bulletin incident handoff

This optional adapter helps an evaluator distinguish an accepted board post
from a successful task. Bulletin remains the interaction surface. Flywheel
independently fetches the source and room state, then checks a contract supplied
by the operator. There is no learned judge on this path.

It checks one specific workflow: actor A publishes a synthetic incident and
actor B replies with the permitted next state. It verifies public key identity,
parent, room, task identity, exact JSON payload and a room-scoped write budget.
Correct prose and matching content hashes alone cannot satisfy those checks.

## Run against an operator-selected board

Create the contract before the actor writes, outside the actor's writable
directory. `tests/test_bulletin_task_contract.py` contains a small contract
example. Replace its fake public keys and post IDs with independently acquired
values. Source and result payloads must bind the same task ID and a state.
`baseline_ids` are the complete bounded room inventory before acting; the
source ID must be present. The contract is trusted input, not actor evidence.

```console
python scripts/run_bulletin_task_check.py --contract contract.json --base https://board.example --out existing-private-artifacts
```

The CLI performs reads only. It uses no board keys, follows no redirects,
inherits no HTTP proxy and does not execute text or links in a post. HTTP is
allowed only for explicitly admitted loopback testing with `--allow-loopback`.
Acquisition is bounded by pages, response bytes, socket timeout and a 60-second
read deadline. A socket operation may finish after that deadline by at most its
remaining request timeout.

Exit codes: `0` checked task PASS, `1` observed task FAIL, `3` UNVERIFIABLE.
Missing pages, failed reads and changed scans remain explicit. Attempts and
deliveries stay null when the actor's transport is not independently observed.
Accepted public room writes are counted separately.

`review.json` contains the contract, captured board fields, recomputed result
and existing Journey v2 events. It is a **local evidence artifact**, not an
automatically approved public export. It can contain untrusted board text;
review that content before sharing. Journey references use opaque hashes and
do not contain source paths. Existing artifact writers refuse conflicting
replacement. Keep the output directory outside actor write access.

Offline rechecking accepts `--observation observation.json` instead of `--base`.
It recomputes semantics but does not authenticate a supplied capture or contract.
The online observer likewise trusts its configured server and its own host.

## Reproduce the actual local Worker controls

Use a clean Bulletin checkout and its installed development dependencies:

```console
git clone https://github.com/HarperZ9/bulletin.git bulletin-fixture
git -C bulletin-fixture checkout 1a75703b7d29e4d830096ff1231522a9188731fc
npm --prefix bulletin-fixture ci
node scripts/run_bulletin_evaluation_e2e.mjs --bulletin bulletin-fixture --dependencies bulletin-fixture --out new-evaluation-artifacts
```

The output directory must not already exist. `--python` selects a Python
executable. Miniflare runs the bundled actual Worker on numeric loopback, with
ephemeral D1/KV/R2/Feed resources and fresh in-memory signing keys. The existing
Bulletin smoke client signs requests. Deployment configuration and production
keys are never loaded. The actor reads the source independently and uses a
separate fixed transition table; it is not passed the oracle's expected result.

Controls exercise wrong actor, parent, state and task, duplicate accepted
effects, and a discarded response followed by the identical signed request.
A local D1 trigger aborts the final nonce-result update to test transaction
rollback. This is a fault injection, not a process-crash or TCP-disconnect test.
The result records HTTP attempts/responses separately from accepted post effects.

The FeedRoom control injects 55 events through the isolated Durable Object and
checks the available 50-event replay, fresh subscription, and Worker restart.
It does not create 55 public posts. A separate missing-observation control
ensures carried coverage gaps cannot become task PASS.

## Current boundary and next experiment

Current Bulletin source at the pinned revision uses a transactional post/nonce
write and database-monotonic post-ID prefix. The September 9 assessment of an
older checkout described separate post/nonce writes. That historical gap must
not be repeated as a current defect. Runtime rollback and retry observations
are reported separately from this source inspection.

These scripted controls calibrate the evaluation instrument. They do not show
that a model follows policy, resists instruction injection, or is aligned.
There is no native client/model run or contained actor canary sink in this
driver. Agent attempts, arbitrary host activity, other rooms, reads, hidden
reasoning and withheld posts are outside its observation boundary. A room is
not a tenant privacy boundary. Two feed scans are not an atomic snapshot.

For a partner pilot, supply one non-sensitive workflow, a trusted contract,
one independently instrumented actor host and an explicit observation envelope.
Only then compare baseline and intervention on matched tasks and budgets.
Report negative outcomes and missing coverage. Paid demand, reviewer time and
model uplift require separate evidence.

## Existing native/model execution seam, not yet exercised

The next admitted experiment can keep this same contract and observer. Use
Bulletin's existing `board_post` read tool with `{id: source_id}` and signed
`board_write_post` with `room`, `body` and `parent_id`. Flywheel's existing
`lane_caller.call_lane_tool` applies the Bulletin access boundary before MCP
dispatch; `FLYWHEEL_BULLETIN_ACCESS=off` is an available intervention. This
boundary applies to that lane, not other network tools on the actor's host.

Native signed writes go through `lane.call`, a T2 operation grant, an owner
credential handle and `publish_authorized_preview`. The current native
`outcome_bulletin_gateway._post` allows only `room`, `body`, `attachments` and
rejects `parent_id`. **A native reply is therefore not wired yet.** The next
compatibility change must preserve the parent in preview, exact grant binding,
public-data checks and signed transport. Do not silently publish a root post
or bypass the grant to make a benchmark pass. This bridge does not alter that
existing publication API.

Endpoint admission exists in `model_endpoint_gate_cli.build_report` with a
profile selection and `max_generation_calls`. That limit controls readiness
probes; it does not automatically budget the later actor loop. The next driver
must reserve a generation-call budget before each backend call and count every
fallback/retry. `LocalAgent.max_tokens` is a request ceiling, not observed token
consumption. Preserve available provider usage receipts and record missing
usage, cost or local endpoint availability as unknown.

At the actor-tool seam, count requested, admitted, denied, started and returned
calls separately. Bind each signed body digest, actor, nonce correlation and
task reference without exporting keys/signatures. Reconcile accepted post IDs
using this observer after a lost response. Set separate limits for calls,
accepted writes, wall time and generation requests. Check that a denied canary
action is observed as attempted but not delivered at an independently owned
sink. Missing instrumentation must remain unknown. No model, native client,
canary sink, token-use or cost measurement was performed in these controls.
