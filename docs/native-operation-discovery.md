# Discover a native operation after reopening

`GET /api/operations?journey_ref=<journey>&limit=20` reads operation metadata
for the authenticated owner and one Journey. It requires configured bearer
authentication, including on loopback. It never starts a worker, reads model
credentials, or returns task goals, input, output or private trace bodies.

The response is `flywheel.gateway-operation-list/v1`:

- `journey_ref`: the selected Journey.
- `event_head_sha256`: the validated Journey head anchoring this page sequence.
- `operations`: existing `flywheel.gateway-operation-snapshot/v1` objects,
  ordered newest queued operation first. Their head is the page anchor.
- `request_sha256_by_operation`: one entry per returned operation, keyed by
  operation reference. Each value is SHA-256 of the canonical JSON string
  containing the original `client_request_id`, including JSON quotes.
- `next_cursor`: opaque cursor string, or null when that snapshot is exhausted.

Only `journey_ref`, optional `limit` (1 through 50, default 20), and optional
`cursor` are accepted. Duplicate, unknown or malformed parameters fail with
`INVALID_REQUEST` (422). The query is capped at 2,048 characters. A foreign or
missing Journey returns the same `NOT_FOUND` (404) response. Invalid, missing
committed events or exceeded read limits return `STORE_COMMIT_FAILED` (500),
with no partial list or reflected private values.

Save the client request ID before submitting a task. If the first start response
is lost, compute its digest and search these page maps for the exact matching
operation. Do not guess from the newest row or automatically submit again.
Request hashes are correlation metadata, not secrets or authorization tokens.
Use random, non-sensitive request IDs; common IDs remain dictionary-matchable.

All rows have `can_cancel: false`. Discovery is an anchored historical view;
fetch `GET /api/operations/<operation_ref>` for the current snapshot before
watching or preparing cancellation. Cancellation still uses its existing
one-use grant and current Journey head. Fetch the existing result/trace routes
to verify and inspect output. A terminal reference here is a durable event
locator; discovery does not read or establish the integrity of result bodies.

Pass the cursor unchanged with the same Journey to continue. The cursor binds
the authenticated owner, Journey, historical head and offset. New appends do
not shift its pages. Start without a cursor to refresh. Cursors carry no grant
and are not trusted as authority: their anchor must exist in the authenticated
Journey's validated current chain. An incompatible or forged anchor fails.

The reader pins the state-root directory and reads only the selected owner's
Journey. It follows immutable event filenames derived from validated sequence
and hash references; it does not enumerate other Journeys or follow symlinks or
reparse points. It reuses the Journey reducer and operation lifecycle validator.
Each request permits at most 4,096 committed events, 4 KiB for the head,
1 MiB per event, and 16 MiB total bytes. Large histories fail explicitly rather
than silently truncate. Reading is bounded but linear in the selected Journey's
history; pagination bounds the response, not the history validation work.

The read uses the immutable chain plus its committed head as one snapshot.
It does not mix in a concurrently replaced projection cache or acquire a
mutating store lock. The pinned filesystem backend must be supported.

Tests exercise real synthetic Journey storage, HTTP authentication, owner and
Journey separation, request correlation, stable pagination during append,
terminal locators, tampered events, forged cursors, foreign-chain transplant,
symlink rejection and read limits. No model calls are needed. Run the discovery
tests together with operation-route and private-trace HTTP regressions; these
checks do not prove a live model task or the desktop reopen workflow.
