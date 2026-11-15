# M4.1 — the transport seam

M4.1 adds one interface, `Transport`, and one refusal hierarchy every wire
adapter satisfies. A live relay, an MCP transport, an HTTP or gRPC endpoint, a
stdio pipe: each lives in its own package and speaks to canon through this one
Protocol. The container carries no runtime dependency on any of them.

Code: `src/canon/transport/`. Tests: `tests/test_transport_base.py`,
`tests/test_transport_conformance.py`. Everything here is stdlib-only; the
wire-side handle is injected the way F1 injects the mneme and flywheel stores
(D-72).

## The interface

`Transport` is a `runtime_checkable` Protocol with a `name` and eleven members:

| member | contract |
|---|---|
| `name: str` | short adapter id, used in errors and receipts |
| `supported_kinds() -> frozenset[str]` | record kinds the wire carries; `push` refuses others |
| `caps() -> frozenset[str]` | capability tokens the wire preserves |
| `declared_drops() -> frozenset[str]` | capability tokens a round-trip loses |
| `pin() -> str` | the schema pin this wire speaks (default `canon.record/v1`) |
| `describe() -> TransportDescriptor` | machine-readable summary, all invariants enforced in `__post_init__` |
| `flatten(record) -> Record` | a copy safe to `push`, with removable dropped capabilities stripped |
| `push(record) -> TransportReceipt` | send one record; raises per `guard_push` and per wire failure |
| `fetch(scope, id) -> Record \| None` | the record under `(scope, id)`, or `None` on miss (D-75) |
| `list_keys(scope) -> list[str]` | keys the wire holds under one scope, order unspecified (D-76) |
| `list_all() -> list[str]` | keys across every canon scope |

The dispatch key is the `(scope, id)` pair, reused verbatim from F1's
`record_key` (D-72). A personality-block is deliberately present at both scopes
under one id (the F0 override case), so scope is part of the identity a wire
dispatches under.

## The capability model

`caps()` and `declared_drops()` return tokens from a fixed vocabulary of
seventeen (`TRANSPORT_CAPABILITIES`), split into three tiers.

**Record-enforceable** (three tokens): a single record can trigger the drop by
its own fields. `guard_push` refuses such a record on a wire that dropped the
capability, so the loss is never silent, and the caller must `flatten()` first
and thereby opt into it (D-71, mirroring F1's D-8).

| token | live when |
|---|---|
| `temporal-preserving` | the record's temporal block carries a live `valid_until` or `supersedes` |
| `provenance-preserving` | the record's provenance carries any field beyond the required `harness` + `source_hash` |
| `sized-payload-limit` | the canonical envelope exceeds the wire's `size_limit_bytes` |

**Structural** (eleven tokens): properties of the wire, not of one record's
fields. Declared for machine-readable disclosure but not record-triggerable, so
`guard_push` never raises on them.

`remote-read`, `remote-write`, `at-most-once`, `at-least-once`, `idempotent-push`,
`ordering-preserving`, `replay-safe`, `offline-safe`, `audit-chain`,
`foreign-envelope`, `schema-pin-verified`.

`TransportDescriptor` enforces one exclusion on this set: `at-most-once` and
`at-least-once` cannot both appear in `caps()`.

**Reserved** (three tokens): `tombstones`, `streamable`, `remote-batch`. No M4
adapter advertises them. Reserving them means a later Wave that adds them does
not renumber the vocabulary or edit `capabilities.py`.

## The wire envelope

`TransportEnvelope` is the canonical shape one record takes on the wire. It is a
runtime frozen dataclass, not a Wave 1 schema (D-73):

| field | shape |
|---|---|
| `record_json: str` | the record's `to_json()` verbatim; `sort_keys=True` |
| `pin: str` | the wire's schema pin (default `canon.record/v1`) |
| `idempotency_key: str` | domain-separated sha256, see below |
| `create_ord: int \| None` | the record's clock-free ordinal, if any |

`to_canonical_json()` writes the four keys sorted, with tight separators
(`","` and `":"`). Two sends of the same record produce byte-identical envelope
bytes on the wire. The envelope holds no `time`, `timestamp`, or `now` key
(D-77's twin: canon has no wall-clock authority).

## The idempotency key

```
idempotency_key(record) = sha256("canon-transport/v1\n" + record.to_json()).hexdigest()
```

The `"canon-transport/v1\n"` prefix comes from `canon.textutil.domain_prefix`,
the same helper R2 uses for its vault identity digest under
`"canon-vault/v1\n"`. Domain-separated by construction (D-74): a transport
idempotency key can never collide with a vault note filename, and neither
prefix is a substring of the other.

Determinism is by design. Two runs of the same record on any host produce the
same key. The wire is free to deduplicate on it. Collision detection is not
attempted (D-77, honest null).

## The refusal hierarchy

Every transport-level refusal roots at `TransportError`. Eleven subclasses
carry the reason:

| class | condition |
|---|---|
| `UnsupportedKind` | `record.kind` is absent from `supported_kinds()` |
| `DropError` | record exercises a record-enforceable cap the wire dropped |
| `SchemaMismatch` | envelope pin mismatch, or `validate_record` failed |
| `ContentTooLarge` | canonical envelope bytes exceed `size_limit_bytes` |
| `PayloadCorrupt` | wire decode failure (`json.loads`, `Record.from_dict`) |
| `IdentityMismatch` | fetched record's derived key does not match the requested key |
| `DuplicatePush` | replay-safe wire observed matching idempotency key with different bytes |
| `Unreachable` | handle raised `OSError`, `ConnectionError`, or `TimeoutError` |
| `AuthRefused` | handle raised a 401 / 403 / OAuth-refused equivalent |
| `RateLimited` | handle raised a 429 equivalent; carries `retry_after` |
| `RemoteRefused` | handle-side catch-all; carries `cause_text` |

No wire-adjacent handle error escapes canon un-wrapped. A live `ConnectionError`
comes back as `Unreachable`; a live `PermissionError` comes back as
`AuthRefused`; a live `RuntimeError` from a 429 comes back as `RateLimited` with
`retry_after` copied off the exception. Callers pattern-match on canon's
hierarchy and never on the underlying transport library's exception type.

## guard_push

`guard_push(transport, record)` is the shared pre-dispatch check every
`Transport.push` runs at the top of its body. Six branches, cheapest first,
each a helper under fifteen lines so the whole guard fits on one screen:

1. `_check_kind` — raises `UnsupportedKind`
2. `_check_validator` — runs `validate_record`; a non-empty problem list raises `SchemaMismatch`
3. `_check_pin` — compares `record.to_dict()["canon_schema"]` against `transport.pin()`; raises `SchemaMismatch`
4. `_check_drops` — intersects `capabilities_required(record)` with `declared_drops()`; a non-empty intersection raises `DropError`
5. `_check_size_cheap` — a fast heuristic on id, scope, kind, and data field lengths; raises `ContentTooLarge` before the full serialization
6. `_check_size_full` — the canonical serialization; raises `ContentTooLarge` on overflow

The cheap-size branch is not a substitute for the full check. It is a
performance shortcut: an obviously oversized record fails without paying for
its full serialization. Both branches carry the same error class and the same
disclosure semantics.

## flatten

`default_flatten(record, transport_drops)` reads only the record-enforceable
tokens the wire dropped. `temporal-preserving` maps onto the backend-side
`CAP_TEMPORAL` and strips the temporal block. `provenance-preserving` and
`sized-payload-limit` are honest nulls: the first is not removable at record
level (F0 requires `harness` + `source_hash`), the second cannot be resolved by
flatten (D-72). A wire's own `flatten` can override this default when it wants
richer behavior.

## The descriptor

`TransportDescriptor` is the wire's machine-readable summary. `__post_init__`
enforces every invariant a caller can rely on: non-empty `name`, `caps` and
`declared_drops` closed over `TRANSPORT_CAPABILITIES`, disjoint,
`at-most-once` and `at-least-once` not both present, positive `size_limit_bytes`.

The descriptor is a runtime dataclass, not a Wave 1 schema (D-73). A future
`canon.adapter/v1` schema would sit alongside; every existing name carries the
`Transport` prefix so no name collides (`TransportEnvelope` vs a possible
`canon.transform-envelope/v1`, and so on).

## The conformance suite

`tests/test_transport_conformance.py` parametrizes twenty-one cases over a
`transport_factory` fixture. A live adapter added later replaces the fixture
with its own factory and inherits every guarantee: round-trip, idempotency,
unreachable / auth-refused / rate-limited wrapping, corrupt / wrong-pin /
oversize / spoofed-key fetch verdicts, guard branches through push, flatten
symmetry.

The suite exercises `FakeRelayHandle` in `tests/_fakes.py`, which carries one
knob per refusal branch. That is the whole test contract for a new wire: wrap
your handle so each canon error class corresponds to the right underlying
condition, and the conformance suite runs unchanged.

## What stays out

Live wire, TLS, WebSocket, gRPC, stdio pipe, MCP dispatch: all in the relay
repo, not here. OAuth, JWK rotation, cert pinning, credential handling: none.
Retry policy, exponential backoff, circuit breaker, connection pooling,
keepalive, rate-limit token buckets: caller's or handle's job; canon does not
sleep. DNS discovery, service mesh: out. `delete`, `tombstone`, `exists`,
`health`, `close`, `__exit__`: not in the Protocol. Streaming, chunking,
multipart, `push_many`, `fetch_many`: deferred to Wave 2 under an explicit
`CAP_REMOTE_BATCH` design. Cross-provider routing: Wave 2. Signature
verification, trust labels, freshness enums, disclosure profiles: Wave 2 under
`canon.adapter/v1`. Wire encryption, compression: none. `pickle`,
`typing_extensions`, ambient `time.time()` defaults: none, and asserted absent
by the test that pins the module's import set.
