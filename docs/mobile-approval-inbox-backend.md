# Mobile approval inbox backend contract

Status: backend contract for the first mobile approval inbox increment. This is not a provider sign-in flow, biometric authority, credential vault, or device-control transport. It is an authenticated owner-scoped view over existing gateway grant proposals.

## Capability negotiation

`POST /api/gateway-grants/capabilities`

Request:

```json
{"schema":"flywheel.gateway-grant-capabilities-request/v1"}
```

Response:

```json
{
  "schema": "flywheel.gateway-grant-capabilities/v1",
  "proposal_list": true,
  "proposal_read": true,
  "reviewed_approval": true,
  "durable_reject": true,
  "review_max_bytes": 32768
}
```

An inbox client must call this first. If the route is absent or `reviewed_approval` is not true, show upgrade required. Do not fall back to legacy `approve-once`.

## List proposals

`POST /api/gateway-grants/list`

Request:

```json
{
  "schema": "flywheel.gateway-grant-list-request/v1",
  "state": "pending",
  "limit": 25,
  "cursor": null
}
```

`state` may be `pending`, `recoverable`, or `decided_recent`. `pending` contains prepared, unexpired proposals. `recoverable` contains prepared or approved, unexpired proposals that an initiating client may need to recover. `decided_recent` contains approved or rejected proposals whose indexed decision time is within the last 24 hours. `limit` defaults to 25 and is capped at 50. `cursor` is an opaque string returned by the server.

Response:

```json
{
  "schema": "flywheel.gateway-grant-list/v1",
  "server_time": "2026-09-07T12:00:00Z",
  "state": "pending",
  "items": [
    {
      "schema": "flywheel.gateway-grant-list-item/v1",
      "proposal_ref": "prp_...",
      "planned_grant_ref": "gnt_...",
      "proposal_state": "prepared",
      "derived_state": "pending",
      "record_sha256": "64hex",
      "expires_at": "2026-09-07T12:02:00Z",
      "operation_ref": "op_...",
      "review_available": true,
      "review_sha256": "64hex",
      "summary": {"schema": "flywheel.gateway-grant-summary/v1"}
    }
  ],
  "next_cursor": null,
  "index_complete": true,
  "list_status": "complete",
  "coverage_scope": "maintained_index",
  "recovery_required": null,
  "decided_recent_window_seconds": 86400,
  "inspected_index_rows": 1,
  "record_reads": 1
}
```

The list row is enough to show a queue. It is not enough to approve. Fetch `read` and render the full exact review before enabling approval.

The list is backed by an owner-scoped SQLite proposal index at `gateway-grant-proposals/<owner_ref>/proposal-index.sqlite3`. The proposal JSON record remains the authority for approval, rejection, and dispatch. List reads at most `limit + 1` index rows and at most that many bounded proposal records per page. It never scans and validates the full owner proposal history to satisfy a small page.

`index_complete` is part of the UI contract. Its `coverage_scope` is `maintained_index`: it means the bounded page was checked against the maintained listing index and the normal index lifecycle has no known incomplete mutation. It is not filesystem reconciliation, tamper proofness, or proof that no proposal JSON exists outside the maintained index. If `index_complete` is false or `recovery_required` is present, the UI must show incomplete or recovery required state and must not treat an empty list as proof that no proposals exist. `list_status` values:

- `complete`: indexed rows checked for this page and the owner index is not known to be incomplete.
- `legacy_index_required`: proposal records exist without a complete index. The endpoint does not silently backfill by reading all historical proposal files.
- `index_mutation_pending`: an owner-scoped index mutation intent exists. The endpoint does not present filtered list results as complete until the source proposal record write has been confirmed into the index.
- `index_drift`: an index row pointed to a missing, oversized, unreadable, or mismatched proposal record. This is the expected conservative crash-recovery signal when an index write reached disk before the source record write or when files drift.
- `index_unavailable`: the index could not be opened safely.
- `recovery_required`: an explicit recovery marker exists for this owner index. The known reason is in `recovery_required`, for example `SCAN_LIMIT_EXCEEDED`, `SOURCE_RECORD_INVALID`, or `INDEX_REPLACE_FAILED`.

Crash and drift semantics are fail-closed for display completeness in the maintained index lifecycle. Prepare, legacy approve, reviewed approve, and reject first write a dirty mutation marker under the owner proposal lock, then write the source proposal record, then update the index row and clear the dirty marker in one SQLite transaction. If a process stops between those steps, list returns `index_complete:false`. Direct SQLite tampering or corruption outside that lifecycle is not detected by every list call; use explicit reconcile when recovery is required or when external index corruption is suspected.

## Explicit bounded index reconcile

Initial recovery is a backend command:

```powershell
python -m harness.gateway_grant_index_reconcile --state-root <state_root> --owner-ref <owner_ref> --limit 1000
```

The command is owner scoped and takes the same owner proposal lock used by approve and reject. It scans at most `limit` proposal JSON records and at most `limit * 4 + 64` directory entries, reads each record with the 1 MiB capped proposal reader, validates every source record with the existing proposal validator, and then atomically replaces `proposal-index.sqlite3`. It does not edit proposal JSON, issue grants, consume grants, dispatch operations, or change credential storage.

If the scan is partial or invalid, the command preserves the old index and writes `proposal-index-recovery.marker`. List then returns `index_complete:false`, `list_status:"recovery_required"`, and a `recovery_required` reason. A successful full bounded scan clears the marker.

## Read exact review

`POST /api/gateway-grants/read`

Request:

```json
{
  "schema": "flywheel.gateway-grant-read-request/v1",
  "proposal_ref": "prp_..."
}
```

Response with review:

```json
{
  "schema": "flywheel.gateway-grant-read/v1",
  "proposal_state": "prepared",
  "derived_state": "pending",
  "record_sha256": "64hex",
  "review_available": true,
  "review": {
    "schema": "flywheel.gateway-grant-review/v1",
    "proposal_ref": "prp_...",
    "planned_grant_ref": "gnt_...",
    "record_sha256": "64hex",
    "review_sha256": "64hex",
    "operation_ref": "op_...",
    "action": "plugin.call",
    "journey_ref": "jrn_...",
    "expected_event_head": "64hex",
    "client_request_id": "request-1",
    "destination": {"kind": "plugin", "ref": "relay"},
    "tool": "relay.run",
    "scopes": ["write", "exec", "network", "plugin"],
    "data_refs": [],
    "credential_refs": [],
    "execution_plan_sha256": "64hex",
    "operation_sha256": "64hex",
    "arguments_sha256": "64hex",
    "operation": {"name": "relay", "tool": "relay.run"},
    "expires_at": "2026-09-07T12:02:00Z"
  }
}
```

The `operation` member is exact and complete. Credentials remain opaque refs. If the exact review exceeds `review_max_bytes`, approval is unavailable.

Unavailable response:

```json
{
  "schema": "flywheel.gateway-grant-read/v1",
  "derived_state": "review_unavailable",
  "review_available": false,
  "unavailable_reason": "OPERATION_REVIEW_TOO_LARGE"
}
```

## Reviewed approve

`POST /api/gateway-grants/approve-reviewed-once`

Request:

```json
{
  "schema": "flywheel.gateway-grant-reviewed-approval-request/v1",
  "proposal_ref": "prp_...",
  "review_sha256": "64hex"
}
```

Response:

```json
{
  "schema": "flywheel.operation-grant-approval/v1",
  "grant_ref": "gnt_...",
  "expires_at": "2026-09-07T12:02:00Z"
}
```

The server recomputes the exact review under the owner proposal lock and denies unavailable or mismatched review hashes before issuing a grant.

## Legacy approve

`POST /api/gateway-grants/approve-once`

This remains compatible with existing proposal-ref-only clients:

```json
{"proposal_ref":"prp_..."}
```

New inbox clients must not use it. It exists for current local grant sheets and concurrent callers that predate reviewed inbox approval.

## Reject

`POST /api/gateway-grants/reject`

Request:

```json
{
  "schema": "flywheel.gateway-grant-reject-request/v1",
  "proposal_ref": "prp_...",
  "expected_record_sha256": "64hex"
}
```

Response:

```json
{
  "schema": "flywheel.gateway-grant-rejection/v1",
  "proposal_ref": "prp_...",
  "proposal_state": "rejected",
  "record_sha256": "64hex"
}
```

Reject transitions only `prepared` proposals to `rejected`. It never issues, consumes, dispatches, executes, or cancels. Reject after approval returns a conflict, not a false rejection. Active cancellation remains the existing operation cancel path.
