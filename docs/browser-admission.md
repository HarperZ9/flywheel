# Browser admission before driver dispatch

Browser control records a durable admission before invoking a bound driver.
The admission reserves one session attempt. A separate completion cites that
admission and records the driver's acknowledgement. The policy and action
grammar remain in `harness/browser_control.py`; the authenticated gateway uses
the existing `/api/browser` routes. No live driver is registered by this change.

## Requests and replay

Driver-bound requests must supply a `request_id`, unique within the session,
using 1–128 ASCII letters, digits, dot, underscore, colon or dash. The route
forwards this identifier to the existing attempt function:

```json
{
  "run_id": "owned-fixture",
  "request_id": "navigate-1",
  "action": {"kind": "navigate", "url": "https://example.test/"}
}
```

The same identifier and normalized action return the existing record without
another dispatch or budget charge. Reusing it with a different action refuses.
An interrupted attempt with no terminal record remains delivery-unknown; a
fresh process cannot retry it silently. Changing the identifier does not clear
the session's unknown-delivery pause. Reconcile externally before starting
another approved session; this API supplies no automatic recovery actuator.

Without a bound driver, requests may omit the identifier and receive an
automatically generated one. These records are explicitly `simulated: true`.
They preserve the previous policy-planning behavior and `performed: false`.
Planned navigation does not establish a driver-side origin after a driver is
bound later.

## What a completion establishes

- `{"ok": true, "performed": true}` is recorded as
  `driver_reported_performed`, with `performed: true`.
- An explicit `performed: false` acknowledgement is recorded as
  `driver_reported_not_performed`.
- Exceptions, missing or contradictory acknowledgements, and absent
  completions leave `performed: null` and unknown delivery. Exception text and
  raw driver results are not persisted; only a fixed error code and, when
  serializable, a result digest are retained.

These fields report the driver. They are not independent verification that
the intended target changed or that the task succeeded. In particular,
`driver_open_origin` is derived from acknowledged navigation, not an
independent browser observation. Legacy records are retained; historical
driver records without the new delivery fields pause further actuation and
do not establish a verified current origin or count as performed success.
Their raw historical flags remain on disk. Mixed legacy/new delivery fields
are invalid; removing a phase cannot downgrade a new admission to legacy.

Session `actions` contains one latest record per admission, including its
correlated completion when available. `attempted` counts admissions, including
refusals, but does not count terminal records twice. Raw history retains both
records. A new terminal has `kind: completion`; the existing action fields
remain available. The current desktop Browser view observes records; this
change does not make it a ready-to-use actuator or reconciliation interface.

## Persistence and availability

The browser store reuses the shared exclusive file lock, strict JSON parser,
canonical hashing and directory-flush primitives. Admission and completion
writes use flushed temporary files and atomic replacement. A failure before
durable admission means no driver call. A failure after dispatch leaves the
admission available for unknown-delivery handling. Invalid or inconsistent
history refuses instead of becoming an empty new session. A valid hash alone
does not validate an impossible delivery-state combination.

The per-session lock spans admission through completion. Concurrent processes
cannot spend the same budget slot or dispatch the same identifier twice. A
competing request can receive a bounded store-busy/unavailable response; a
future adapter still needs its own execution deadline. Durability relies on
the repository's filesystem primitives and the underlying filesystem. This
is not a defense against a hostile filesystem administrator or complete
rollback of every record.

## Boundary for a later Telos adapter

The existing action grammar contains URL, selector and field data. It does
not yet contain an authenticated opaque browser target or observation token.
Do not reinterpret a selector or Telos substring match as authorization.

A later adapter must bind the observed opaque target, browser session,
observation freshness, actual origin and caller request identifier to the
existing authorized operation before admission. That binding must survive
normalization and be present in both the admission and driver invocation.
Reject missing, changed or ambiguous targets and origin changes before
actuation. The adapter must also distinguish the driver acknowledgement from
an independently observed outcome. Reuse existing operation, grant and audit
interfaces; do not expose a raw Telos MCP actuator or treat a catalog response
as an action receipt.

Tests use inert drivers and filesystem-only synthetic effects. Process-death
and competing-process controls establish admission/replay behavior, not live
browser safety, target binding, privacy enforcement or Telos integration.
