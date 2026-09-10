# Rowan task lifecycle

The native assistant distinguishes submission, execution state and reported
receipt assurance. A returned run ID means Submitted. A lost response means
submission outcome unknown; the assistant does not retry the write.

When the panel opens it reads recent tasks from the connected gateway's existing
Relay run store. These are labelled Gateway tasks because another device or
client may have started them. No local task database or conversation migration
is introduced. Each panel uses its supplied GatewayClient and inherits the
gateway's existing access policy. This view adds no authorization boundary;
callers must replace the executor when changing gateway or account context.

The panel refreshes locally submitted or selected active tasks every five seconds
while open. Refresh uses GET status/result by a validated opaque run reference,
never POST start. Reopening the panel recovers from GET runs. It does not resume
an interrupted worker, invent a cancellation operation, or resend a publication.
Gateway history is bounded by Relay retention; the local display retains at most
64 task metadata rows and reports unavailable reads explicitly.

## Contract and evidence boundary

The gateway already forwards `/api/relay/runs`, `/api/relay/status` and
`/api/relay/result` to Relay's local agent tools. Relay uses `state`, with values
`running`, `done`, `error` and `interrupted`. Unknown values stay unknown. The
contract was checked against the repository's Relay gitlink `84192bd3` and the
pending bundled-launch candidate `81d544b`; the latter adds request bindings while
preserving these fields. Request bindings and private diagnostic/result bodies
are not copied into this metadata projection.

Production Relay run IDs are sixteen lowercase hexadecimal characters. The
client rejects invalid refs before reading and requires matching IDs in status
and result replies. It retains only the ID, state, bounded step count, assurance
classification and a validated checkpoint digest. No prompts, credentials,
private errors or raw result objects are persisted by this feature. Original
results and failed receipts remain in the existing Relay store.

Execution completed does not establish an accurate answer or a successful public
action. A structurally valid result with Relay's `verified`, `chain_ok` and
`final_answer` all true is labelled as Relay-reported receipt integrity. A false
flag means the result needs review. If status confirms completion but the result
read fails or omits assurance fields, execution stays completed with receipt
assurance unavailable. Contradictory run IDs or states remain unknown. The client
does not independently verify the checkpoint and does not
promote it to semantic truth.

The existing submission sends only the goal. It does not enable Relay writes or
shell execution, widen grants, or route Bulletin publication around its approval
path. Native launch/outreach still needs the reviewed Bulletin operation and
independently retrieved publication readback. This change proves neither a real
hosted-model run nor mobile deployment nor cross-device conversation sync.

## Validation

Focused tests exercise unsafe IDs, missing/wrong result IDs, malformed histories,
lost reads, interrupted workers, explicit negative receipt flags, stale-list
races, recovered tasks, no recovery POST, narrow layout and diagnostic privacy.
The complete desktop analyzer/test suite and repository static gates run before
the release checkpoint. Network activity in these tests uses controlled HTTP
fixtures; no real task, post or device action is executed.
