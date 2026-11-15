# M4 - Expanded Scope Proposal

## Framing

M4 is the fifth band on top of the F0-through-V4 spine. It carries three legs that all wear the shape F1 already proved: a runtime-checkable Protocol, injected duck-typed handles, capability tokens, refuse-not-flatten discipline, and typed refusals rooted at a single band-local exception. Leg one is a transport Protocol seam so any adapter (in-tree fake, out-of-tree relay client, future stdio pipe) can dispatch records across a process boundary without canon owning a socket. Leg two is a whole-vault reader that closes the round trip R2's write leg opened. Leg three is a pin registry that names every seam canon exposes and gates any future migration through an explicit refusal.

"Expanded" here means breadth inside the ceiling the operator approved on 2026-08-30. Every leg stays a Protocol-only seam, stdlib-only, no CLI, no publish, no deploy. The Wave 1 schemas (`canon.atom/v1`, `canon.capsule/v1`, `canon.omission/v1`, `canon.transform-receipt/v1`, `canon.readiness-probe/v1`, `canon.bootstrap-witness/v1`, `canon.adapter/v1`) all stay out. The verbatim standing constraint from `project-docs/APPROVAL-CANON-CONTINUITY-20260830.md:14`: "The approval does not authorize edits to the user-owned I0 worktree, raw protected-history ingestion, new runtime dependencies, package or name registration, publishing, deployment, provider outreach, telemetry, paid/live model benchmarks, or 14B/32B release claims." This proposal asks for a build-go on top of that ceiling. Push, PR, and deploy remain separate asks.

## Standing constraints (ceiling)

- No live server, no socket, no HTTP, no OAuth. The live cross-provider tunnel stays in the sibling relay repo behind its own deploy-go.
- No new runtime dependencies. Stdlib only. No `requests`, `httpx`, `websockets`, `authlib`, `pyyaml`, `pydantic`, `pickle` anywhere under `src/canon/`.
- No CLI entrypoint. No `console_scripts` in pyproject.toml, no argparse `main`, no `__main__` module, no `python -m canon.<leg>` runnable module.
- No Wave 1 schema artifacts. Any pin whose short-name would land a Wave 1 schema is refused at pin_for.
- No package or name registration on PyPI, npm, or crates. The audit confirmed `canon` is taken on all three and `canon-memory` is a same-name competitor.
- No publishing, no deployment.
- No provider outreach, no telemetry emission.
- No edits to the user-owned I0 worktree (path held privately by the operator; the audit README carries the scope).
- No raw protected-history ingestion.
- No paid or live model benchmarks. No 14B/32B release claim.
- 300 lines per file. 50 lines per function.
- Python 3.11+. TDD (RED test before implementation).
- Branch only. No push, no PR, no default-branch commit.
- Public repo cleanliness. No `C:\`, no `/c/dev`, no absolute host paths in any file that lands.
- V2's D-58 fix and the V2/V3/V4 push are prerequisites in the resume plan. M4 lands after them.

---

## M4.1 - Transport Protocol seam

### Purpose

A typed Protocol that any transport adapter satisfies. Canon imports no engine. The seam gives a caller one refusal surface, one canonical envelope, one idempotency-key derivation. Push_many, fetch_many, streaming, and every batch verb stay out of M4 and defer to a later band with their own approval.

### Files added

| Path | Role |
|---|---|
| `src/canon/transport/__init__.py` | Public re-exports of the seam surface. |
| `src/canon/transport/base.py` | `Transport` Protocol, `guard_push` free function, refusal hierarchy, envelope + receipt + descriptor dataclasses. |
| `src/canon/transport/capabilities.py` | `CAP_*` module constants, `TRANSPORT_CAPABILITIES` frozenset, `RECORD_ENFORCEABLE_TRANSPORT` frozenset. |
| `src/canon/textutil.py` | Shared `_normalize_newlines(text)` extracted from `vault_mirror.py:164` and `frontmatter.py:103`, plus `domain_prefix(name)` helper. This ships in the same commit as M4.1 because transport uses `domain_prefix("canon-transport")` and the vault-reader in M4.2 will reuse `_normalize_newlines`. |
| `tests/_fakes.py` (extended) | `FakeRelayHandle` with hostile-input knobs. |
| `tests/test_transport_base.py` | Protocol conformance, guard_push refusals, error hierarchy, idempotency-key determinism. |
| `tests/test_transport_conformance.py` | Reusable fixture pool any concrete Transport can run. |
| `project-docs/M4-TRANSPORT.md` | Prose contract mirroring `F1-BACKENDS.md`. |
| `project-docs/M4-TRANSPORT-DECISIONS.md` | D-69 through D-78. |

### Protocol methods

| Method | Signature | Purpose | Refusal path | Test |
|---|---|---|---|---|
| `name` | `str` (attribute) | Identity used in error messages, descriptor, drops-profile table. | Empty string caught at first use. | `test_transport_name_non_empty` |
| `supported_kinds()` | `-> frozenset[str]` | Which of the five record kinds this transport carries. | Mismatch raises `UnsupportedKind` inside `guard_push`. | `test_guard_push_raises_unsupported_kind` |
| `caps()` | `-> frozenset[str]` | Positive advertisement of what this transport CAN do. | Members outside `TRANSPORT_CAPABILITIES` raise at post-init. | `test_every_advertised_token_is_a_known_capability` |
| `declared_drops()` | `-> frozenset[str]` | What a round trip through this transport loses. | Members outside `TRANSPORT_CAPABILITIES` raise at post-init. | `test_every_declared_drop_is_a_known_capability` |
| `pin()` | `-> str` | Schema pin the transport speaks. Defaults to `canon.schema.SCHEMA`. | Mismatch on send raises `SchemaMismatch`. | `test_schema_pin_mismatch_refused_before_send` |
| `describe()` | `-> TransportDescriptor` | Machine-readable adapter summary. Not a Wave 1 schema. | Frozen dataclass; construction refuses bad fields. | `test_descriptor_serialization_is_byte_stable` |
| `flatten(record)` | `-> Record` | Strip record-enforceable dropped capabilities. Identity when nothing removable. | Never mutates source (Record is frozen). | `test_flatten_does_not_mutate_source` |
| `push(record)` | `-> TransportReceipt` | Single-record dispatch. Runs `guard_push` at the top. | See guard_push refusal matrix. | `conformance_case_push_get_round_trip_per_kind` |
| `fetch(scope, id)` | `-> Record \| None` | Single-record read. None on miss, never raises on miss. | Decode-time refusals raise the matched `TransportError` subclass. | `conformance_case_fetch_missing_returns_none` |
| `list_keys(scope)` | `-> list[str]` | Scope-scoped enumeration. Order unspecified. Empty list on empty scope. | Handle failure wraps as `Unreachable`. | `conformance_case_list_keys_on_empty_scope_returns_empty_list` |
| `list_all()` | `-> list[str]` | Cross-scope enumeration. Iterates `canon.schema.SCOPES`. | Same as `list_keys`. | `test_list_all_iterates_scopes_not_hardcoded_pair` |

Deferred out of M4 (folded from adversarial critique on runtime-policy drift and batch semantics): `push_many`, `fetch_many`, `iter_incremental`, `exists`, `delete`, `health`, `close`. Each deferred verb becomes an honest null below.

### Capability tokens

Every token lives as a module-level string constant. Every token is a member of `TRANSPORT_CAPABILITIES`.

| Token | Class | Meaning |
|---|---|---|
| `CAP_TEMPORAL_PRESERVING` | record-enforceable | A record carrying `valid_until` or `supersedes` exercises this. Twin of F1's `CAP_TEMPORAL`, renamed here to name the preservation contract on the wire. The rename is an explicit decision. |
| `CAP_PROVENANCE_PRESERVING` | record-enforceable | A record with caller-supplied provenance beyond the two required fields exercises this. |
| `CAP_SIZED_PAYLOAD_LIMIT` | record-enforceable | A record whose canonical envelope bytes exceed the transport's declared size limit exercises this. Flatten cannot shrink a payload; caller must reshape the record. |
| `CAP_REMOTE_READ` | structural | Transport supports `fetch` and `list_keys`. Absence means write-only mirror. |
| `CAP_REMOTE_WRITE` | structural | Transport supports `push`. Absence means read-only mirror. |
| `CAP_AT_MOST_ONCE` | structural | Transport guarantees no duplicate delivery. Mutually exclusive with `CAP_AT_LEAST_ONCE`. |
| `CAP_AT_LEAST_ONCE` | structural | Transport may deliver twice; caller dedupes by idempotency key. |
| `CAP_IDEMPOTENT_PUSH` | structural | Duplicate push with matching idempotency key returns the same receipt. |
| `CAP_ORDERING_PRESERVING` | structural | Transport preserves `create_ord` ordering across a batch. |
| `CAP_REPLAY_SAFE` | structural | Transport rejects a matching idempotency key that carries different bytes. |
| `CAP_OFFLINE_SAFE` | structural | Transport degrades to local-only when remote is unreachable. |
| `CAP_AUDIT_CHAIN` | structural | Transport preserves a hash chain across dispatches. Twin of F1's `CAP_AUDIT_CHAIN`. |
| `CAP_FOREIGN_ENVELOPE` | structural | Transport preserves the exact canonical JSON bytes end-to-end. |
| `CAP_SCHEMA_PIN_VERIFIED` | structural | Transport surfaces its pin via `pin()` and refuses a mismatched envelope pin before send. Every M4 transport must advertise this. |

Reserved tokens (present in the frozenset but never carried by any M4 adapter): `CAP_TOMBSTONES`, `CAP_STREAMABLE`, `CAP_REMOTE_BATCH`. Reserving them means a Wave 2 band adding them does not have to renumber the vocabulary.

Post-init invariant: `caps().isdisjoint(declared_drops())`. Enforced by `test_caps_and_declared_drops_are_disjoint`.

### Refusal hierarchy

```
Exception
  TransportError
    UnsupportedKind          (guard_push: kind not in supported_kinds)
    DropError                (guard_push: record exercises a record-enforceable dropped cap)
    SchemaMismatch           (guard_push: pin mismatch on send; wire decoder: pin mismatch on fetch)
    ContentTooLarge          (guard_push: envelope over size_limit_bytes; wire decoder: fetched payload over limit)
    PayloadCorrupt           (wire decoder: json.loads / Record.from_dict / canonicalization roundtrip failed)
    IdentityMismatch         (wire decoder: derived record_key != asked key)
    DuplicatePush            (replay-safe transport: matching idempotency key with different bytes)
    Unreachable              (WRAPPED: handle-side OSError / ConnectionError / TimeoutError)
    AuthRefused              (WRAPPED: handle-side 401/403/OAuth-refused)
    RateLimited              (WRAPPED: handle-side 429; carries advisory retry_after)
    RemoteRefused            (WRAPPED: handle-side catch-all with cause_text)
```

Every subclass roots at `TransportError`. Single inheritance throughout. No `TransportError` subclass multi-inherits `ValueError` or anything else. This matches every prior band.

### Wire envelope

`TransportEnvelope` is a frozen dataclass with slots. Fields:
- `record_json: str` (the output of `record.to_json()`, which is `json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":"))`)
- `pin: str` (the transport's declared pin at send time)
- `idempotency_key: str` (sha256 hex; derivation below)
- `create_ord: int | None` (echoed from record for ordering reconstruction under reorder)

The envelope's canonical form is `json.dumps({"pin": pin, "idempotency_key": key, "create_ord": ord, "record": record_json}, sort_keys=True, separators=(",", ":"))`. Two sends of the same record produce byte-identical envelope bytes. No wall clock, no random, no host-path leak.

`TransportEnvelope` is NOT `canon.capsule/v1`. It is a runtime dataclass. Capsule schema stays a Wave 1 concern.

### Idempotency key

Derivation:
```
def idempotency_key(record: Record) -> str:
    prefix = domain_prefix("canon-transport")  # "canon-transport/v1\n"
    payload = record.to_json()
    return sha256((prefix + payload).encode("utf-8")).hexdigest()
```

Domain-separated from vault's `canon-vault/v1\n` (R2 D-29). A vault note-name digest and a transport idempotency key cannot collide even by construction.

Collision analysis (honest null): sha256-truncation collisions are astronomically implausible and canon does not detect them. Named as D-77 alongside R2's parallel silence. A caller who needs cryptographic collision defense pairs the key with `record.canon_schema + record_key`.

### guard_push refusal matrix

`guard_push(transport, record)`. First arg is the transport, matching `guard_put(backend, record)` at `src/canon/backends/base.py:115`. One guard shape across the codebase.

Order of checks, cheap first, so an adversary-crafted record cannot OOM the guard before the size gate fires:

1. `record.kind not in transport.supported_kinds()` -> `UnsupportedKind`.
2. `validate_record(record)` returns any problems -> `SchemaMismatch(problems[0])`. Closes the audit-found `FilesBackend.put` gap where `guard_put` ran but `validate_record` did not.
3. `record.canon_schema != transport.pin()` -> `SchemaMismatch`.
4. Record exercises a record-enforceable cap the transport dropped -> `DropError`. Cheap check via `capabilities_required(record)`.
5. `len(record.data.get(k, "")) + len(record.id)` cheap-size heuristic against `transport.describe().size_limit_bytes` -> `ContentTooLarge` if the heuristic already exceeds the limit. Skips the full `to_json()` allocation on obvious oversize.
6. Full canonical size check via `len(record.to_json().encode("utf-8"))` -> `ContentTooLarge` if over the limit.

`guard_push` splits into `_check_kind`, `_check_validator`, `_check_pin`, `_check_drops`, `_check_size_cheap`, `_check_size_full`. Every helper stays under 20 lines. The top-level `guard_push` stays under 30 lines.

### Fake transport (`FakeRelayHandle`)

Every knob wires to one refusal-branch test. Every knob is a boolean or int on `__init__`.

| Knob | Behavior | Test |
|---|---|---|
| `unreachable=True` | Every method raises `ConnectionError`. | `test_unreachable_handle_wrapped_as_transport_error` |
| `corrupt_on_fetch=True` | Fetch returns bytes that fail `json.loads`. | `test_corrupt_bytes_on_fetch_raise_payload_corrupt` |
| `wrong_pin=<str>` | Fetched payload carries a mismatched `canon_schema`. | `test_schema_pin_mismatch_on_fetch_raises` |
| `oversize_after=<int>` | After N pushes, returned payload exceeds size limit. | `test_oversize_returned_refused_by_wire_decoder` |
| `auth_refused=True` | Every push raises the handle's 401. | `test_auth_refused_wrapped` |
| `rate_limited_every=<int>` | Every kth push raises 429. | `test_rate_limited_wrapped_with_advisory_retry_after` |
| `replay_returns_stale=True` | Fetch after push returns older bytes. | `conformance_case_replay_safe_refuses_tampered_key` |
| `duplicate_push_tampered=True` | Second push with same key gets different bytes. | `test_replay_safe_transport_refuses_tampered_idempotency_key` |
| `spoof_wrong_key=True` | Fetch returns a Record whose derived key does not match. | `test_wrong_key_delivery_raises_identity_mismatch` |

Characterization tests lock the fake's mirror of the relay's actual surface. Same D-11 discipline F1 used.

### Conformance test suite

Fixture-driven, parametrized over a `TransportFactory`. Reusable by any future in-tree adapter and by an out-of-tree adapter that vendors the fixture pool.

1. `conformance_case_push_get_round_trip_per_kind` (parametrized over 5 kinds)
2. `conformance_case_fetch_missing_returns_none`
3. `conformance_case_list_keys_on_empty_scope_returns_empty_list`
4. `conformance_case_capability_drop_refusal`
5. `conformance_case_pin_mismatch_refused_before_send`
6. `conformance_case_pin_mismatch_on_fetch_raises`
7. `conformance_case_oversize_refused`
8. `conformance_case_idempotent_replay`
9. `conformance_case_replay_safe_refuses_tampered_key`
10. `conformance_case_ordering_invariance_under_retry`
11. `conformance_case_unicode_safe_keys`
12. `conformance_case_crlf_in_body_survives_round_trip`
13. `conformance_case_wrong_key_delivery_raises_identity_mismatch`
14. `conformance_case_handle_unreachable_wrapped`
15. `conformance_case_auth_refused_wrapped`
16. `conformance_case_rate_limited_wrapped`
17. `conformance_case_structural_drop_does_not_block_lone_push`
18. `conformance_case_two_scopes_one_id_do_not_collide`

### Adapter descriptor

```python
@dataclass(frozen=True, slots=True)
class TransportDescriptor:
    name: str
    pin: str
    caps: frozenset[str]
    declared_drops: frozenset[str]
    size_limit_bytes: int
    notes: str = ""
```

`notes` is an advisory free-form string. Support-tier vocabulary (`Enforced`, `Native advisory`, `Guided`, `Unsupported`) belongs on `canon.adapter/v1` per V-C1. M4 does not label above fixture proof.

`describe()` returns a fresh descriptor each call from live attributes. `json.dumps(asdict(descriptor), sort_keys=True)` is byte-stable across runs.

### Honest nulls

- No live wire. Socket, TLS, HTTP, WebSocket, gRPC, stdio pipe, MCP wire all stay in the relay repo.
- No OAuth, no cert pinning, no JWK rotation.
- No real auth handling. `AuthRefused` wraps what the handle raised; canon evaluates no credential.
- No retry policy, no exponential backoff, no circuit breaker. Caller's or handle's job.
- No connection pooling, no keepalive.
- No rate-limit token bucket. Canon does not sleep.
- No DNS discovery, no service mesh.
- No `delete`, no tombstone. Wave 2; would need `canon.tombstone/v1`.
- No `exists`. Composes as `fetch(...) is not None`.
- No `health`. Reachability is live behavior.
- No `close`, no `__exit__`. Handle owns lifecycle.
- No streaming, no chunking, no multipart.
- No `push_many`, `fetch_many`. Deferred to Wave 2 with an explicit `CAP_REMOTE_BATCH` design.
- No cross-provider routing across (Claude, Codex, ChatGPT). Wave 2.
- No `ClockSkew`. Canon has no wall-clock authority.
- No signature verification. `notes` may cite a signing key; canon does not verify.
- No trust labels enforced. Wave 2 with `canon.adapter/v1`.
- No freshness enum enforced. Wave 2.
- No disclosure profiles. Wave 2.
- No prompt-injection sanitizer, no auto-summary. Records pass through verbatim.
- No secret-quarantine detector, no PII redaction. Separate skills.
- No compression.
- No wire encryption at rest.
- No sha256 collision detection on idempotency key. Astronomically implausible; named as D-77.
- No `pickle` anywhere. Test asserts `pickle` not imported.
- No `typing_extensions`. Test asserts not imported. Protocols avoid default values so `runtime_checkable` behaves consistently on 3.11.
- No ambient `time.time()` default anywhere. Test asserts no `time.time` in default args.
- No `pathlib.Path.rglob`. Test asserts `pathlib` not imported by transport.
- No package name reservation. Audit V-C2 says defer.

### Line budget

| File | New/Edit | Est LOC | Under 300 | Max fn under 50 |
|---|---|---|---|---|
| `src/canon/transport/__init__.py` | new | 25 | yes | n/a |
| `src/canon/transport/base.py` | new | 190 | yes | yes (guard_push splits into 6 helpers) |
| `src/canon/transport/capabilities.py` | new | 70 | yes | n/a |
| `src/canon/textutil.py` | new | 45 | yes | yes |
| `tests/_fakes.py` | edit +150 | ~280 total | yes | yes |
| `tests/test_transport_base.py` | new | 270 | yes | yes |
| `tests/test_transport_conformance.py` | new | 240 | yes | yes |

Transport split saves the file gate. Original 220-line estimate for a single `base.py` was too tight against 16 capability constants, 11 error classes, 4 dataclasses, a Protocol with 11 methods, and `guard_push` with 6 sub-checks.

### Acceptance tests

Twenty unit tests plus the 18 conformance cases above.

1. `test_transport_protocol_shape`
2. `test_transport_error_hierarchy`
3. `test_record_key_reused_verbatim_from_backends`
4. `test_split_key_keeps_slash_in_id_across_transport`
5. `test_two_scopes_one_id_are_distinct_dispatch_keys`
6. `test_pin_default_is_canon_record_v1`
7. `test_schema_pin_mismatch_refused_before_send`
8. `test_schema_pin_mismatch_on_fetch_raises`
9. `test_guard_push_raises_unsupported_kind`
10. `test_guard_push_raises_drop_error_on_temporal_preserving_dropped`
11. `test_guard_push_raises_drop_error_on_provenance_preserving_dropped`
12. `test_guard_push_runs_validate_record`
13. `test_oversize_record_refused_at_guard_push`
14. `test_oversize_record_caught_by_cheap_check_before_full_serialize`
15. `test_flatten_strips_only_removable`
16. `test_flatten_does_not_mutate_source`
17. `test_idempotency_key_is_domain_separated_from_vault`
18. `test_idempotency_key_is_deterministic_across_runs`
19. `test_descriptor_serialization_is_byte_stable`
20. `test_caps_and_declared_drops_are_disjoint`
21. `test_every_advertised_token_is_a_known_capability`
22. `test_transport_imports_only_stdlib_data_modules` (grep-shape: no socket, no http, no urllib.request, no ssl, no requests, no httpx, no pickle, no typing_extensions)
23. `test_list_all_iterates_scopes_not_hardcoded_pair`
24. `test_handle_native_value_error_wrapped_as_transport_error`

### Decisions to record

- D-69 - transport is a Protocol seam. Every wire stays in relay.
- D-70 - three record-enforceable tokens (`CAP_TEMPORAL_PRESERVING`, `CAP_PROVENANCE_PRESERVING`, `CAP_SIZED_PAYLOAD_LIMIT`); structural tokens declare-but-never-block.
- D-71 - refuse-not-flatten holds on the transport side (mirrors F1 D-8).
- D-72 - external transport engines reached through injected duck-typed handle; canon imports no relay package, no socket module, no HTTP client.
- D-73 - `TransportEnvelope`, `TransportReceipt`, `TransportDescriptor` are runtime frozen dataclasses, not Wave 1 schemas. Names carry `Transport` prefix so a future `canon.transform-receipt/v1` does not collide.
- D-74 - idempotency key = sha256("canon-transport/v1\n" + record.to_json()); domain-separated from vault.
- D-75 - `fetch(missing)` returns None; never raises on miss.
- D-76 - `list_keys` / `list_all` return unordered lists; determinism is caller's job.
- D-77 - sha256 idempotency-key collisions are astronomically implausible and not detected. Honest null.
- D-78 - `CAP_TEMPORAL_PRESERVING` is a deliberate rename of F1's `CAP_TEMPORAL` because the transport carries a preservation contract, not a storage contract. Named explicitly so a reader is not surprised to see two token names for what looks like one concept.

---

## M4.2 - Vault frontend

### Purpose

Close the round trip R2 opened. R2 writes; M4.2 reads. Every rule R2 enforces on the write leg has a symmetric read verdict. Every hostile input the write leg refuses gets a verdict on the read leg. The reader is TOTAL: every refusal is a `NoteVerdict`, never a raise.

### Files added

| Path | Role |
|---|---|
| `src/canon/vault_reader.py` | Whole-vault reader. `classify_vault`, `load_from_plan`, `read_vault`, `read_vault_scope`, `read_note_at`, `classify_vault_entry`. |
| `src/canon/vault_read_fidelity.py` | Symmetric round-trip verdict. `DECLARED_READ_DROPS = frozenset()`. `vault_symmetric_report(pool)`. |
| `tests/test_vault_reader.py` | Containment + hostile-input verdicts. |
| `tests/test_vault_reader_fidelity.py` | Round-trip + Kleene-star fixed-point + declared-drop pin. |
| `tests/fixtures/vault_reader/` | Well-formed and hostile fixture notes. |
| `project-docs/M4-VAULT-READER.md` | Prose contract mirroring `R2-BACKENDS.md` shape. |
| `project-docs/M4-VAULT-READER-DECISIONS.md` | D-79 through D-88. |

### Read entry points

- `read_vault(root, *, list_dir, read_text) -> VaultReadResult`. Whole-vault read; runs classify then dedupe; `ok` iff no refusals.
- `read_vault_scope(root, scope, *, list_dir, read_text) -> VaultReadResult`. One scope's directory. Raises `ValueError` if the scope string is not a member of `canon.schema.SCOPES` (API contract violation, distinct from runtime data).
- `classify_vault(root, *, list_dir, read_text) -> ReadPlan`. Phase 1 only. Caller inspects before phase 2 assembles a pool. Mirrors V4 `reconcile_run` two-phase D-62.
- `load_from_plan(plan) -> VaultReadResult`. Phase 2. Fold verdicts into pool, refusals, skipped, counts.
- `read_note_at(root, relpath, *, read_text) -> NoteVerdict`. Single-note reader.
- `classify_vault_entry(root, relpath, text) -> NoteVerdict`. Pure per-entry classifier. No IO. Dispatch table maps every REFUSED_* / SKIPPED_* status to a small handler under 20 lines.

Deferred out of M4.2 (folded from cross-band critique on query-language surface): `iter_notes`, `iter_scope_notes`, `find_by_predicate`, `filter_scope`, `filter_kind`, `filter_predicate`. Query surface waits for a Wave 2 query Protocol.

### Ingestion pipeline

For every relpath the injected `list_dir` yields, in sorted order:

1. Containment check via `is_vault_write_allowed(root, target)`. One gate. Same lexical rule the write leg uses. Symlink follow policy is the caller's; canon does no realpath.
2. Hub short-circuit. Top-level `MEMORY.md` becomes `SKIPPED_HUB` without content check.
3. `read_text(target)` returns `None` -> `SKIPPED_ABSENT`. Listing raced a delete.
4. `read_text` returns `bytes` instead of `str` -> `SKIPPED_ENCODING` (caller injected the wrong callable).
5. First byte is a UTF-16 or UTF-32 BOM (`\xff\xfe`, `\xfe\xff`, `\x00\x00\xfe\xff`) -> `SKIPPED_ENCODING`. UTF-8 BOM at the head falls through to REFUSED_MISSING_FENCE (never silently stripped).
6. `_normalize_newlines(text)` folds CRLF and bare CR to LF (from the shared `canon.textutil` helper).
7. `frontmatter.parse_frontmatter(text)` runs. Every FrontmatterError folds to a typed REFUSED_* verdict.
8. `vault.ingest_note(text)` reconstructs the Record from the `canon:` JSON alone. Body, heading, per-kind body, `## canon links` trailer, aliases are ignored (D-27 rule).
9. `validate_record(record)` returns problems -> `REFUSED_INVALID_RECORD`.
10. `normcase(derive_note_name(record))` != `normcase(relpath)` -> `REFUSED_SPOOF`.
11. `record.scope != parts[0]` (the scope directory the file lives in) -> `REFUSED_MIS_SCOPE`.
12. Otherwise -> `LOADED`.

After phase 1: aggregate check. Two loaded records sharing `record_key(record)` -> `REFUSED_DUPLICATE_KEY` on both, first-wins reason.

### Hostile-input refusals (verdicts)

Every one of the following is a `NoteVerdict` with a `REFUSED_*` or `SKIPPED_*` status. The reader never raises.

- `REFUSED_MISSING_FENCE` (no leading `---`, UTF-8 BOM prefix breaks fence, empty file)
- `REFUSED_UNCLOSED_FENCE` (no matching closing `---`)
- `REFUSED_NO_CANON_KEY` (fence exists but zero `canon:` lines)
- `REFUSED_MULTIPLE_CANON_KEYS` (two `canon:` lines; prevents ambiguous authority)
- `REFUSED_MALFORMED_SCALAR` (`canon:` value not single-quoted scalar)
- `REFUSED_INVALID_JSON` (json.loads raised on unescaped payload)
- `REFUSED_INVALID_SCHEMA` (missing `canon_schema`, missing structural key)
- `REFUSED_INVALID_RECORD` (`validate_record` returned problems, including research-artifact-ref carrying temporal)
- `REFUSED_SPOOF` (derived name mismatches on-disk relpath)
- `REFUSED_MIS_SCOPE` (`record.scope` mismatches scope directory; mirrors R1 D-18)
- `REFUSED_DUPLICATE_KEY` (two loaded records share record_key)
- `REFUSED_NAME_COLLISION` (two records derive to the same relpath via sha256 truncation collision; astronomically implausible)
- `SKIPPED_HUB` (top-level MEMORY.md is a projection per D-27/D-32/D-34)
- `SKIPPED_NOT_ALLOWED` (root itself, absolute path escape, `..` traversal, top-level non-MEMORY.md file, ad-hoc deeper-than-scope path, unknown scope directory, cross-drive/mixed-abs-rel ValueError caught, dotfile, `.md.bak`, `.md.tmp`)
- `SKIPPED_ABSENT` (read_text returned None between listing and read)
- `SKIPPED_NOT_MARKDOWN` (scope-level entry lacking `.md` suffix)
- `SKIPPED_ENCODING` (UTF-16/UTF-32 BOM, bytes returned instead of str)

Case-only path variants on case-insensitive filesystems (`Foo-<digest>.md` vs `foo-<digest>.md`) fold to the same target via `normcase`. Not a spoof.

NFC vs NFD unicode filename variants: `derive_note_name` uses NFKD-then-ASCII-drop in `_slugify`, so both normalizations produce the same derived name. `normcase(on_disk) == normcase(derive_note_name(record))` matches both. A hostile writer's fullwidth-char attempt on a legitimate slug diverges under NFKD and gets REFUSED_SPOOF.

Hand-edited body under an intact carrier loads cleanly per D-27. The record returned is the one the carrier declares.

Wikilink-hostile ids (`topic#v2`, `bad]id`), all-punctuation ids, Windows reserved names (CON, NUL) all load correctly. The derived name uses the fallback `{slug}-{digest}` shape and the spoof check re-derives via the same domain-tagged digest.

Oversized frontmatter is an honest null. No per-note byte-size ceiling ships in M4.2. A caller's `read_text` may impose a ceiling by returning None or raising above threshold. Named as D-85.

Windows MAX_PATH (paths over 260 chars on non-`\\?\` prefixed paths) is an honest null. The injected `list_dir` is responsible for handling OS-specific path limits.

Windows junctions (predate NTFS symlinks) are an honest null. The lexical-only containment rule declines to follow them same as symlinks.

### Containment (mirroring vault_mirror)

Read leg reuses `vault_mirror.is_vault_write_allowed` verbatim as the ONE lexical gate. Any path the write leg would refuse to touch is a path the read leg refuses to source. Two legs cannot disagree.

Lexical rules:
- `normpath` + `normcase` on both target and root.
- Refuse the root itself.
- Refuse when `commonpath([root, target]) != root`.
- Admit only `{scope}/<name>.md` (scope in `SCOPES`, case-folded) or top-level `MEMORY.md`.
- Catch `ValueError` from cross-drive / mixed abs-rel comparisons; treat as SKIPPED_NOT_ALLOWED.

No `pathlib.Path.resolve()`. No realpath. Symlink-follow is the caller's `list_dir`.

### Symmetry proofs

`vault_read_fidelity.vault_symmetric_report(pool, *, initial_fs=None) -> VaultReadVerdict`:

1. Run `plan_vault(pool)` into an in-memory `FakeFS`. Capture write-leg refusals.
2. Run `read_vault(root, list_dir=fake.list_dir, read_text=fake.read_text)`. Capture read-leg refusals.
3. Assert the loaded pool equals the input pool (order-independent set equality on `record_key`).
4. Re-run `plan_vault(loaded_pool)` into a fresh `FakeFS`. Assert the byte set matches the first write.
5. Verdict: `ok=True` when both round trips match and both leg refusal counts are zero.

Kleene-star fixed-point: applying plan_vault + read_vault twice produces the second read byte-identical to the first read.

`DECLARED_READ_DROPS: frozenset = frozenset()`. Symmetric to `DECLARED_NOTE_DROPS` on the write leg. Any diff is UNDECLARED and fails closed. Test `test_declared_drops_are_both_literally_frozenset_empty` reads both source files and asserts both constants are literally `frozenset()`. A future contributor extending one but not the other trips the shared-asymmetry test.

### Totality rule

`VaultReadResult(pool, refusals, skipped, ok, counts)`. Frozen dataclass. `ok` is `True` iff every entry is in `OK_STATUSES = frozenset({LOADED, SKIPPED_HUB, SKIPPED_NOT_ALLOWED, SKIPPED_ABSENT, SKIPPED_NOT_MARKDOWN, SKIPPED_ENCODING})`. `read_exit_code(result) -> int` returns 0 iff `result.ok`, 1 on any refusal. Mirrors `drift_exit_code` and `reconcile_exit_code`.

No branch of the reader raises `FrontmatterError`, `VaultError`, `ValueError`, `KeyError`, or any other exception to the caller. Every hostile input becomes a verdict. `test_read_vault_never_raises` parametrizes over every hostile fixture.

### Iterator variant

Deferred to Wave 2. No `iter_notes`, no `iter_scope_notes`. The M4.2 leg reads whole-vault eagerly. A caller who needs streaming for a large vault can compose over `sorted(list_dir(root))` themselves and call `read_note_at` per entry. The Protocol shape does not gain iterator methods.

### Filter surface

Deferred to Wave 2. No `filter_scope`, `filter_kind`, `filter_predicate`, `find_by_predicate`. Predicate callables define a query Protocol canon does not have. Wave 2 lands the query layer with its own approval.

### vault_read_fidelity decision

Yes. Ships as a separate module. Reason: the round-trip proof needs an in-memory `FakeFS` that would bloat `test_vault_reader.py` past the 300-line gate if inlined. The `DECLARED_READ_DROPS` pin is a symmetric constant to `vault_fidelity.DECLARED_NOTE_DROPS` and belongs with the fidelity leg, not the reader.

### Injected IO shape

```python
class ListDir(Protocol):
    def __call__(self, path: str) -> Iterable[str]: ...  # POSIX relpaths under path

class ReadText(Protocol):
    def __call__(self, path: str) -> str | None: ...  # None for absent file
```

No default values in Protocol methods (avoids the 3.11 `runtime_checkable` bug). Symlink-follow, MAX_PATH handling, junction handling all live in the caller.

### Honest nulls

- No real-filesystem walking. Injected `list_dir`.
- No symlink resolution or realpath. Lexical containment only.
- No cross-process locks or CAS. V4 D-66 disclosed non-transactional boundary carries.
- No file watcher, no inotify, no FSEvents.
- No remote-vault transport (that is M4.1).
- No vault mutation (writing, deleting, moving). Read leg is read-only.
- No git integration.
- No editor integration.
- No per-note byte-size ceiling. Named as D-85. Caller's `read_text` imposes it.
- No BOM-tolerant read mode. R2 byte-discipline holds.
- No MEMORY.md content validation. Hub is a projection; write leg owns hub ownership.
- No merge across two vault roots. Single-root by construction.
- No character-set validation of note bodies. Body ignored per D-27.
- No concurrency snapshot. Injected IO can point at a snapshot copy.
- No hub-orphan cross-check. Reader does not consult hub.
- No delta / incremental read. No persistent snapshot store.
- No bootstrap witness or receipt emission from the reader. Wave 1 schemas.
- No trust-label decoration. Wave 1 vocabulary.
- No `pathlib` import. `os.path` only. Test asserts.
- No `pickle`, no `typing_extensions`, no ambient `time.time()`. Tests assert.
- Windows MAX_PATH: honest null, caller's job.
- Windows junctions: honest null, same as symlinks.
- sha256 name collision: astronomically implausible; verdict path exists (REFUSED_NAME_COLLISION) but no cryptographic collision defense.

### Line budget

| File | New/Edit | Est LOC | Under 300 | Max fn under 50 |
|---|---|---|---|---|
| `src/canon/vault_reader.py` | new | 240 | yes | yes (classify_vault_entry is a dispatch table + tiny handlers) |
| `src/canon/vault_read_fidelity.py` | new | 120 | yes | yes |
| `tests/test_vault_reader.py` | new | 280 | yes | yes |
| `tests/test_vault_reader_fidelity.py` | new | 90 | yes | yes |
| `tests/fixtures/vault_reader/*.md` | new | ~30 fixtures | n/a | n/a |

If `test_vault_reader.py` overshoots 280 during implementation, split into `test_vault_reader_containment.py` (containment + skipped) and `test_vault_reader_hostile.py` (refused verdicts).

### Acceptance tests

At least 25 tests.

1. `test_read_vault_returns_all_five_kinds_across_both_scopes`
2. `test_read_vault_full_round_trip_symmetric_bytes`
3. `test_read_vault_hand_edited_body_ingests_carrier_unchanged`
4. `test_read_vault_skips_hub_without_reading_body`
5. `test_read_vault_skips_hub_when_foreign_head`
6. `test_read_vault_refuses_spoofed_filename`
7. `test_read_vault_refuses_mis_scope_placement`
8. `test_read_vault_refuses_duplicate_key`
9. `test_read_vault_refuses_missing_fence_on_utf8_bom_prefix`
10. `test_read_vault_refuses_unclosed_fence`
11. `test_read_vault_refuses_zero_canon_keys`
12. `test_read_vault_refuses_two_canon_keys`
13. `test_read_vault_refuses_invalid_json_payload`
14. `test_read_vault_refuses_wrong_canon_schema`
15. `test_read_vault_refuses_invalid_record_semantics`
16. `test_read_vault_yaml_python_object_trap_is_inert`
17. `test_read_vault_containment_rejects_absolute_path_listing`
18. `test_read_vault_containment_rejects_parent_escape`
19. `test_read_vault_containment_rejects_root_itself`
20. `test_read_vault_containment_rejects_ad_hoc_deeper_than_scope`
21. `test_read_vault_containment_rejects_unknown_scope_directory`
22. `test_read_vault_containment_rejects_dotfile_and_bak_variants`
23. `test_read_vault_containment_rejects_top_level_non_hub`
24. `test_read_vault_skipped_absent_when_read_text_returns_none`
25. `test_read_vault_skipped_encoding_on_bytes_returned`
26. `test_read_vault_skipped_encoding_on_utf16_bom`
27. `test_read_vault_skipped_encoding_on_utf32_bom`
28. `test_read_vault_crlf_note_reconstructs_byte_identically_to_lf_twin`
29. `test_read_vault_bare_cr_normalized_before_parse`
30. `test_read_vault_case_only_path_variant_recognized_not_spoofed`
31. `test_read_vault_nfc_nfd_id_variants_produce_identical_derived_name`
32. `test_read_vault_sort_stable_output`
33. `test_read_vault_result_ok_false_on_any_refusal`
34. `test_read_vault_result_counts_tally`
35. `test_read_vault_never_raises`
36. `test_read_vault_scope_filters_directory_only`
37. `test_read_vault_scope_rejects_unknown_scope`
38. `test_read_note_at_runs_containment`
39. `test_read_note_at_returns_absent_for_missing`
40. `test_classify_vault_entry_pure_no_io`
41. `test_backwards_compat_no_change_to_r2_modules`
42. `test_vault_symmetric_report_declared_drops_empty`
43. `test_vault_symmetric_report_kleene_star_fixed_point`
44. `test_vault_symmetric_report_carries_write_leg_refusals`
45. `test_no_pathlib_import_in_vault_reader_module`
46. `test_declared_drops_are_both_literally_frozenset_empty`

### Decisions to record

- D-79 - read leg mirrors write leg containment via `is_vault_write_allowed`. One gate, no divergent rule.
- D-80 - read leg is total. Every refusal is a `NoteVerdict`, never raised. Mirrors V2 D-42 and V4 D-56.
- D-81 - two-phase `classify_vault` + `load_from_plan` mirrors V4 D-62.
- D-82 - hub file is skipped with no content check.
- D-83 - dedupe by (scope, id) first-wins via `sorted(list_dir)` iteration. Deterministic, no wall-clock heuristic.
- D-84 - scope-directory match refusal is `REFUSED_MIS_SCOPE`. Mirrors R1 D-18.
- D-85 - no per-note byte-size ceiling in M4.2. Honest null. Caller's `read_text` imposes it.
- D-86 - `DECLARED_READ_DROPS = frozenset()`. Symmetric to `DECLARED_NOTE_DROPS`.
- D-87 - `read_vault_scope` on an unknown scope string raises `ValueError` (wiring fault); a missing scope directory is a `SKIPPED_NOT_ALLOWED` verdict (runtime data). The split is explicit.
- D-88 - backwards-compat additive-only. No edit to `vault.py`, `vault_mirror.py`, `vault_fidelity.py`, `frontmatter.py`, `schema.py`, `backends/base.py`, `validator.py`.

---

## M4.3 - Version pins

### Purpose

Name every version-tagged seam canon owns. Give each a stable handle. Refuse loud on drift. Wire a Protocol-only migration seam that ships zero migrators because no cross-version records exist yet.

### Files added

| Path | Role |
|---|---|
| `src/canon/versions.py` | `SchemaPin` dataclass, `SEAM_PINS` frozenset, `PIN_*` constants, `PIN_REGISTRY`, pin_for/is_compatible/describe/all_pins/pin_from_schema_field, `pin_registry_scope` contextmanager, refusal hierarchy. |
| `src/canon/versions_migrate.py` | `MigrationFn` Protocol, `_MIGRATORS` dict, `register_migrator`, `unregister_migrator`, `migrate`, `MigrationError` refusal. Split from `versions.py` to keep both files under the 200-line comfort zone. |
| `tests/test_versions.py` | Pin lookup, refusal, scope isolation, backwards-compat. |
| `tests/test_versions_migrate.py` | Migration seam, duplicate refusal, wrap-and-rethrow. |
| `project-docs/M4-VERSIONS.md` | Pin table, semver-lite policy, per-seam formalize-or-defer table. |
| `project-docs/M4-VERSIONS-DECISIONS.md` | D-89 through D-99. |

### Full pin table

Every seam canon owns, one row per pin.

| Short-name | Kind tag | ADR | Lives at | Formalize now |
|---|---|---|---|---|
| `record` | `canon.record/v1` | F0 D-1 | `schema.py:33` (`SCHEMA`) | yes |
| `backend-seam` | `canon.backend-seam/v0` | F1 D-9 | `backends/base.py:130` (`MemoryBackend` Protocol) | yes |
| `textblock-grammar` | `canon.textblock/v0` | R0 D-13 | `textblock.py` | yes |
| `region-marker` | `canon.region-marker/v0` | R0 D-12 | `region.py:35` (BEGIN/END literals) | yes |
| `frontmatter` | `canon.frontmatter/v0` | R2 D-28 | `frontmatter.py` | yes |
| `vault-note` | `canon.vault-note/v0` | R2 D-24 | `vault.py` (render_note/ingest_note codec) | yes |
| `vault-identity-digest` | `canon.vault-identity-digest/v1` | R2 D-29 | `vault.py:41` (`_DIGEST_DOMAIN`) | yes; separate pin from `vault-note` because renaming this rewrites every filename |
| `vault-hub-marker` | `canon.vault-hub-marker/v1` | R2 D-34 | `vault_mirror.py:57` (`_HUB_HEAD`) | yes |
| `drift-verdict` | `canon.drift-verdict/v0` | V2 D-41 | `drift.py:47,61` | yes |
| `writing-gate-register` | `canon.writing-gate-register/v0` | V2 D-37 | `writing_gate.py` | yes |
| `persona-thesis-payload` | `canon.persona-thesis-payload/v0` | V3 D-44 | `persona_thesis.py:151` | yes |
| `reconcile-gate-policy` | `canon.reconcile-gate-policy/v0` | V4 D-59 | `reconcile_gate.py:57` | yes |
| `run-witness` | `canon.run-witness/v0` | V4 D-64 | `reconcile_run.py:46` (`WITNESS_KIND`) | yes |
| `transport-seam` | `canon.transport-seam/v0` | M4.1 D-69 | `transport/base.py` | yes (declared here so M4.1 wires against it) |
| `vault-frontend` | `canon.vault-frontend/v0` | M4.2 D-79 | `vault_reader.py` | yes |
| `textutil` | `canon.textutil/v0` | M4.1 (new) | `textutil.py` | yes |

Kind-string constants in `schema.py` (`KIND_PERSONALITY_BLOCK`, `KIND_EPISODIC_MEMORY`, `KIND_SYNTHESIZED_PERSONA_L3`, `KIND_ADR_DECISION`, `KIND_RESEARCH_ARTIFACT_REF`, `TEMPORAL_KINDS`) are NOT separate pins. They live under the `record` pin. A change to the kind vocabulary is a `canon.record/v2` migration.

### Semver-lite policy

Version format regex: `^v(0|[1-9]\d*)(\.(0|[1-9]\d*))?$`. Rejects leading zeros (`v01`, `v0.01`), rejects pre-release suffixes (`v0-rc.1`), rejects build metadata (`v0+build.1`), rejects `V1` (uppercase).

`v0` and `v0.0` are distinct. The regex accepts both; a decision (D-91) pins `v0` as canonical and `pin_for` refuses `v0.0` on construction. A caller who wants minor precision uses `v0.1`, `v0.2`, etc.

`is_compatible(theirs, ours)` returns True iff `theirs == ours` (name, version, kind_tag all equal). Widening rules for v2+ are documented but unimplemented. No cross-version compatibility ships at M4.

### Registry shape

```python
@dataclass(frozen=True, slots=True)
class SchemaPin:
    name: str          # must be in SEAM_PINS
    version: str       # must match semver-lite regex, must not be "v0.0"
    kind_tag: str      # must be "canon.<slug>/v<n>" shape
    adr_ref: str       # must be non-empty

    def __post_init__(self) -> None:
        # validate name in SEAM_PINS
        # validate version regex
        # validate version != "v0.0"
        # validate kind_tag has exactly one "/"
        # validate kind_tag starts with "canon."
        # validate kind_tag version suffix matches self.version
        # validate adr_ref non-empty
```

`__post_init__` splits into `_validate_name`, `_validate_version`, `_validate_kind_tag`, `_validate_adr_ref`. Each under 15 lines. Same edge-guard discipline as `ConflictGatePolicy.__post_init__`.

`PIN_REGISTRY: MappingProxyType[str, SchemaPin]` is a read-only view over a module-level dict populated once at import. Direct assignment raises `TypeError`. `pin_registry_scope` is the only write path outside module init.

### Public API

```python
def pin_for(name: str) -> SchemaPin
def all_pins() -> tuple[SchemaPin, ...]  # sorted by name, byte-stable
def describe(pin: SchemaPin, *, form: str = "human") -> str  # "human" or "json"
def is_compatible(theirs: SchemaPin, ours: SchemaPin) -> bool
def pin_from_schema_field(schema_str: str) -> SchemaPin
# in versions_migrate.py:
def register_migrator(from_pin: SchemaPin, to_pin: SchemaPin, fn: MigrationFn) -> None
def unregister_migrator(from_pin: SchemaPin, to_pin: SchemaPin) -> None
def migrate(record: Record, from_pin: SchemaPin, to_pin: SchemaPin) -> Record

# contextmanager:
@contextmanager
def pin_registry_scope() -> Iterator[dict[str, SchemaPin]]:
    # uses contextvars.ContextVar for per-context override, not threading.Lock
```

`describe(pin, form="json")` returns `json.dumps({"name": pin.name, "version": pin.version, "kind_tag": pin.kind_tag, "adr_ref": pin.adr_ref}, sort_keys=True)`. Downstream drift tests and reports get a stable machine form.

### Refusal set

```
Exception
  VersionError
    UnknownPin           (pin_for on name not in SEAM_PINS; pin_from_schema_field on unmatched kind_tag)
    IncompatiblePin      (migrate cross-pin with no registered migrator)
    MalformedPin         (is_compatible on non-SchemaPin; pin_from_schema_field on bad-shape input)
  MigrationError
    MigratorConflict     (register_migrator on duplicate (from,to) pair)
    MigratorRaised       (wraps any exception a migrator raises)
```

Two roots (`VersionError`, `MigrationError`), single inheritance throughout. Absorbed the cross-band note that five subclasses under one root is unusually flat.

`SchemaPin.__post_init__` raises `ValueError` on bad fields. Bad construction is a wiring fault, not a runtime version error.

### Every-seam survey audit

Files that get a NEW line pinning to a `SchemaPin` (no edits to existing behavior):

| File | Line added | Rationale |
|---|---|---|
| `schema.py` (bottom) | `from canon.versions import PIN_RECORD; assert SCHEMA == PIN_RECORD.kind_tag` | Build-time crash on drift. |
| No other file. | | The cross-band critique warned against sprinkling `SEAM_VERSION = pin_for(...)` into every module. Withdrawn. Pins live centrally in `versions.py`. |

The "sprinkle SEAM_VERSION into every module" proposal is withdrawn (folded from cross-band critique). Editing R0, R1, R2, V2, V3, V4 modules to add lookup lines is outside the M4 build-go's ceiling. Callers who need a pin call `pin_for("<name>")`.

### Migration seam (Protocol only)

```python
class MigrationFn(Protocol):
    def __call__(self, record: Record) -> Record: ...
```

Zero migrators ship. `_MIGRATORS: dict[tuple[SchemaPin, SchemaPin], MigrationFn]` is empty at M4 close. `migrate(rec, pin, pin)` is identity (fast path, no lookup). `migrate(rec, pin_a, pin_b)` with no migrator raises `IncompatiblePin`.

`register_migrator` refuses `MigratorConflict` on duplicate registration. `unregister_migrator` is idempotent (missing entry is no-op, not a refusal). Any exception a registered migrator raises wraps as `MigratorRaised(cause=original)`. Never a bare exception leak.

### Scoped-registry pattern for tests

`pin_registry_scope` uses `contextvars.ContextVar` (folded from cross-band critique on threading.Lock). Snapshots `PIN_REGISTRY` and `_MIGRATORS` at `__enter__`. Restores on `__exit__` via try/finally, including on exception. A fake pin resolves inside the `with` block. Outside the block, `pin_for(fake)` raises `UnknownPin`. Mirrors F1 D-11 fake-mirror discipline.

### Backward compat

`canon.schema.SCHEMA` stays as a module-level string. The literal `"canon.record/v1"` lives in `versions.py` (`PIN_RECORD.kind_tag`). At the bottom of `schema.py`:

```python
from canon.versions import PIN_RECORD  # noqa: E402
SCHEMA = PIN_RECORD.kind_tag
assert SCHEMA == "canon.record/v1", "PIN_RECORD drifted from wire literal"
```

No external caller breaks. `frontmatter.py`, `vault.py`, and every other module that reads `SCHEMA` reads the same string. Fixture JSON files under `tests/fixtures/records/*.json` and `tests/fixtures/layering_pool.json` carry the same literal at rest and are not rewritten.

### Non-goals (Wave 1 stays out)

`SEAM_PINS.isdisjoint({"atom", "capsule", "omission", "transform-receipt", "readiness-probe", "bootstrap-witness", "adapter"})`. Test-enforced. A future band landing `canon.atom/v1` must add the short-name to `SEAM_PINS` explicitly, not silently.

### Honest nulls

- No semver policy negotiation between peers. Local pin registry only.
- No JSON Schema files on disk. Pins are Python literals.
- No RFC-style public spec publication.
- No conformance CLI (approval bar).
- No docs site.
- No migrators registered at M4 close. Verified by `test_no_migrators_registered_at_m4_close`.
- No v2+ pins at M4 close.
- No cross-pin migration runtime beyond the Protocol.
- No Wave 1 schema pins.
- No production transport wire (that is relay).
- No PyPI/npm/crates registration.
- No CLI entrypoint speaking pins.
- No wire format for pins over a network.
- No deprecation dates, no sunset schedules on pins.
- No trust or signature on pins.
- No adapter tier vocabulary in the pin registry.
- No cross-repo pin discovery.
- No auto-inference of pin from a raw Record object.
- No on-disk fixture rewriter.
- No capability-token machinery on pins.
- No persistence, no DB, no file-backed registry.
- No thread-safety guarantee (contextvars.ContextVar gives per-context isolation, not concurrent-mutation safety).

### Line budget

| File | New/Edit | Est LOC | Under 300 | Max fn under 50 |
|---|---|---|---|---|
| `src/canon/versions.py` | new | 165 | yes | yes (`__post_init__` splits) |
| `src/canon/versions_migrate.py` | new | 90 | yes | yes |
| `src/canon/__init__.py` | edit +25 | ~120 total | yes | n/a |
| `src/canon/schema.py` | edit +5 | ~208 total | yes | n/a |
| `tests/test_versions.py` | new | 220 | yes | yes |
| `tests/test_versions_migrate.py` | new | 110 | yes | yes |

Split from a single `versions.py` (folded from adversarial critique on realistic 160-190 line estimate) into `versions.py` + `versions_migrate.py`. Keeps each file well under 200 lines and each function under 20.

### Acceptance tests

At least 12 tests; the enumeration surfaces more.

1. `test_pin_for_returns_schemapin`
2. `test_pin_for_unknown_name_refuses`
3. `test_pin_for_wave_one_names_all_refuse` (parametrized over 7 Wave 1 short-names)
4. `test_every_registry_key_is_in_seam_pins`
5. `test_seam_pins_covers_every_current_seam` (parametrized over 16 short-names)
6. `test_seam_pins_excludes_wave_one`
7. `test_all_pins_is_sorted_and_stable`
8. `test_pin_registry_is_immutable_from_outside_scope`
9. `test_pin_registry_populated_once_at_import`
10. `test_is_compatible_exact_match`
11. `test_is_compatible_refuses_cross_version`
12. `test_is_compatible_refuses_cross_name`
13. `test_is_compatible_refuses_non_pin`
14. `test_pin_from_schema_field_round_trips_every_pin`
15. `test_pin_from_schema_field_unknown_refuses`
16. `test_pin_from_schema_field_malformed_refuses` (parametrized)
17. `test_describe_human_form`
18. `test_describe_json_form_is_byte_stable`
19. `test_schemapin_is_frozen_and_hashable`
20. `test_schemapin_rejects_bad_version` (parametrized over leading-zero, uppercase, pre-release, build-metadata)
21. `test_schemapin_rejects_v0_dot_0`
22. `test_schemapin_rejects_bad_kind_tag`
23. `test_schemapin_rejects_bad_name`
24. `test_schemapin_rejects_kind_tag_version_mismatch`
25. `test_migrate_same_pin_is_identity`
26. `test_migrate_cross_pin_without_migrator_refuses`
27. `test_register_migrator_installs_and_migrates`
28. `test_register_migrator_duplicate_refuses`
29. `test_unregister_migrator_idempotent`
30. `test_migrator_raised_wraps_original`
31. `test_no_migrators_registered_at_m4_close`
32. `test_pin_registry_scope_is_isolated`
33. `test_pin_registry_scope_restores_on_exception`
34. `test_pin_registry_scope_isolates_migrators`
35. `test_pin_registry_scope_uses_contextvars_not_threading`
36. `test_schema_module_pins_to_pin_record`
37. `test_kinds_vocabulary_is_stable`
38. `test_scopes_vocabulary_is_stable`
39. `test_vault_note_pin_and_vault_identity_digest_are_distinct`
40. `test_versions_module_imports_only_stdlib`

### Decisions to record

- D-89 - pin-per-seam, not package-wide.
- D-90 - semver-lite exact match at v0/v1. Widening deferred.
- D-91 - `v0` is canonical; `v0.0` refused at construction.
- D-92 - `SEAM_PINS` is a closed vocabulary. Wave 1 short-names refused.
- D-93 - pin drift is loud, not silent.
- D-94 - backward compat by aliasing. Literal `"canon.record/v1"` lives in `versions.py`; `schema.SCHEMA` aliases via bottom-of-module import + assert.
- D-95 - migration is explicit-migrator-or-refuse. Any exception from a migrator wraps as `MigratorRaised`.
- D-96 - `pin_registry_scope` uses `contextvars.ContextVar`, not `threading.Lock`. Canon carries no concurrency primitives elsewhere.
- D-97 - `SchemaPin` is frozen and constructor-validated.
- D-98 - `transport-seam` and `vault-frontend` pins ship at M4.3 close so M4.1 and M4.2 wire against them.
- D-99 - `vault-identity-digest` (`canon.vault-identity-digest/v1`) is a separate pin from `vault-note`. Renaming the digest domain rewrites every filename on disk; the two concerns need independent bumps.

---

## M4.4 - Optional composition module (canon_check)

Decision: include as an optional light leg. Scope tight. Function only, not a script.

### Rationale

A composition function that runs `drift.surface_drift` + `reconcile.reconcile` (roundtrip check) + `vault_fidelity.vault_roundtrip_report` + `persona_thesis.assess_thesis` + `vault_read_fidelity.vault_symmetric_report` and returns one `CanonCheckReport` verdict gives a caller one place to gate a build on. The composition adds zero new schema, zero new capability, zero new refusal type. It reads existing verdict-returning functions and folds their `ok` bits into one aggregate.

The line budget is small (composition module ~90 lines, test file ~80 lines). It stays under both gates. It ships no CLI. It respects every ceiling.

### Alternative (why not defer)

Deferring canon_check to a later band leaves callers to compose the five verdicts themselves. Each existing report is total and returns an `ok` bit; a caller who wants one gate writes a five-line function. The value canon_check adds is a stable name and a stable aggregate report shape that any downstream tool (a CI job, a future MCP resource) can key on. That value is real but small. If the operator wants M4 narrower, drop this leg first.

### Files added

| Path | Role |
|---|---|
| `src/canon/canon_check.py` | `CanonCheckReport` dataclass, `canon_check(...)` function. |
| `tests/test_canon_check.py` | Aggregate ok/refused, per-report path present. |
| `project-docs/M4-CANON-CHECK.md` | Short prose contract. |

### API

```python
@dataclass(frozen=True, slots=True)
class CanonCheckReport:
    drift: DriftReport | None
    roundtrip: ReconcileReport | None
    vault: VaultVerdict | None
    persona: DriftVerdict | None
    vault_symmetric: VaultReadVerdict | None
    ok: bool
    reasons: tuple[str, ...]  # short label per failed leg
    exit_code: int  # 0 iff ok

def canon_check(
    pool: list[Record],
    *,
    read_text=None,        # injected; None disables drift + vault checks
    list_dir=None,         # injected; None disables vault_symmetric
    assess=None,           # injected persona assessor; None disables persona
) -> CanonCheckReport:
    ...
```

Each leg is opt-in via its injected seam. A caller running headless with only pool state gets a report over `roundtrip` alone. A caller with a filesystem gets `drift`, `vault`, `vault_symmetric` too. A caller with a Crucible seam gets `persona`. Missing seams surface as `None` in the report, not as failures.

### Honest nulls

- No CLI. No `python -m canon.canon_check`. No console script.
- No parallelism across legs. Sequential composition.
- No cache. Each call re-runs every enabled leg.
- No config file, no ambient discovery.
- No telemetry.

### Line budget

| File | New/Edit | Est LOC | Under 300 | Max fn under 50 |
|---|---|---|---|---|
| `src/canon/canon_check.py` | new | 90 | yes | yes |
| `tests/test_canon_check.py` | new | 100 | yes | yes |

### Acceptance tests

1. `test_canon_check_all_ok_with_all_seams_injected`
2. `test_canon_check_ok_with_only_pool_and_roundtrip`
3. `test_canon_check_reports_none_for_disabled_legs`
4. `test_canon_check_ok_false_on_drift_report_ok_false`
5. `test_canon_check_ok_false_on_vault_verdict_ok_false`
6. `test_canon_check_ok_false_on_persona_thesis_refused`
7. `test_canon_check_ok_false_on_symmetric_report_refused`
8. `test_canon_check_reasons_names_each_failed_leg`
9. `test_canon_check_exit_code_is_0_iff_ok`
10. `test_canon_check_never_raises` (parametrized over every hostile input the underlying legs handle)

### Decision to record

- D-100 - `canon_check` is a composition function over existing total-verdict reports. No new schema, no new refusal type. Each leg opt-in via injected seam. Adds a stable aggregate for build gating.

---

## Line-budget totals

| File | New/Edit | Est LOC | Under 300 | Max fn under 50 |
|---|---|---|---|---|
| `src/canon/transport/__init__.py` | new | 25 | yes | n/a |
| `src/canon/transport/base.py` | new | 190 | yes | yes |
| `src/canon/transport/capabilities.py` | new | 70 | yes | n/a |
| `src/canon/textutil.py` | new | 45 | yes | yes |
| `src/canon/vault_reader.py` | new | 240 | yes | yes |
| `src/canon/vault_read_fidelity.py` | new | 120 | yes | yes |
| `src/canon/versions.py` | new | 165 | yes | yes |
| `src/canon/versions_migrate.py` | new | 90 | yes | yes |
| `src/canon/canon_check.py` | new (optional M4.4) | 90 | yes | yes |
| `src/canon/__init__.py` | edit +25 | ~120 | yes | n/a |
| `src/canon/schema.py` | edit +5 | ~208 | yes | n/a |
| `tests/_fakes.py` | edit +150 | ~280 | yes | yes |
| `tests/test_transport_base.py` | new | 270 | yes | yes |
| `tests/test_transport_conformance.py` | new | 240 | yes | yes |
| `tests/test_vault_reader.py` | new | 280 | yes | yes |
| `tests/test_vault_reader_fidelity.py` | new | 90 | yes | yes |
| `tests/test_versions.py` | new | 220 | yes | yes |
| `tests/test_versions_migrate.py` | new | 110 | yes | yes |
| `tests/test_canon_check.py` | new (optional M4.4) | 100 | yes | yes |
| `tests/fixtures/vault_reader/*.md` | new | ~30 fixture files | n/a | n/a |
| `project-docs/M4-TRANSPORT.md` | new | ~180 | n/a | n/a |
| `project-docs/M4-TRANSPORT-DECISIONS.md` | new | ~220 | n/a | n/a |
| `project-docs/M4-VAULT-READER.md` | new | ~180 | n/a | n/a |
| `project-docs/M4-VAULT-READER-DECISIONS.md` | new | ~200 | n/a | n/a |
| `project-docs/M4-VERSIONS.md` | new | ~200 | n/a | n/a |
| `project-docs/M4-VERSIONS-DECISIONS.md` | new | ~220 | n/a | n/a |
| `project-docs/M4-CANON-CHECK.md` | new (optional M4.4) | ~80 | n/a | n/a |

Every source and test file lands under 300 lines. Every function stays under 50 lines by construction of the splits called out per module.

## Acceptance-test totals

Baseline: 409 passing tests at HEAD `bf5945d` on `feat/v4-reconcile-loop`.

New tests by leg:
- M4.1 transport: 24 unit tests + 18 conformance cases = 42 tests
- M4.2 vault frontend: 46 tests
- M4.3 versions: 40 tests
- M4.4 canon_check (optional): 10 tests

M4 close (all legs): 409 + 42 + 46 + 40 + 10 = 547 tests. The 409 baseline stays green.

If canon_check is dropped: M4 close at 537 tests.

## Decision log

Every D-number M4 will record. One line each. Targeted at `project-docs/M4-TRANSPORT-DECISIONS.md`, `project-docs/M4-VAULT-READER-DECISIONS.md`, `project-docs/M4-VERSIONS-DECISIONS.md`, and (if M4.4 ships) a short note in the vault-reader log or its own tiny log.

- D-69 - transport is a Protocol seam; wire stays in relay.
- D-70 - three record-enforceable transport tokens.
- D-71 - transport refuse-not-flatten mirrors F1 D-8.
- D-72 - transport engines reached through injected handle.
- D-73 - transport envelope, receipt, descriptor are runtime dataclasses.
- D-74 - transport idempotency key derived with `canon-transport/v1\n` domain prefix.
- D-75 - transport `fetch(missing)` returns None.
- D-76 - transport `list_*` unordered.
- D-77 - sha256 idempotency collisions astronomically implausible; honest null.
- D-78 - `CAP_TEMPORAL_PRESERVING` renamed from `CAP_TEMPORAL`; the split is deliberate.
- D-79 - vault reader containment reuses `is_vault_write_allowed`.
- D-80 - vault reader is total.
- D-81 - two-phase classify + load.
- D-82 - hub skipped without content check.
- D-83 - dedupe by (scope, id) first-wins via sorted list_dir.
- D-84 - `REFUSED_MIS_SCOPE` mirrors R1 D-18.
- D-85 - no per-note byte-size ceiling; honest null.
- D-86 - `DECLARED_READ_DROPS = frozenset()`.
- D-87 - `read_vault_scope` on unknown scope string raises `ValueError`; missing scope directory is a verdict.
- D-88 - vault reader backwards-compat additive-only.
- D-89 - pin-per-seam.
- D-90 - semver-lite exact match at v0/v1.
- D-91 - `v0` canonical; `v0.0` refused.
- D-92 - `SEAM_PINS` closed vocabulary excludes Wave 1.
- D-93 - pin drift is loud.
- D-94 - `schema.SCHEMA` aliases `PIN_RECORD.kind_tag` via bottom-of-module import.
- D-95 - explicit-migrator-or-refuse; migrator exceptions wrap as `MigratorRaised`.
- D-96 - `pin_registry_scope` uses `contextvars.ContextVar`.
- D-97 - `SchemaPin` frozen + constructor-validated.
- D-98 - transport-seam and vault-frontend pins ship at M4.3 close.
- D-99 - `vault-identity-digest` is a distinct pin from `vault-note`.
- D-100 - `canon_check` composition function; opt-in seams; no new schema (only if M4.4 lands).

## Commit shape

Argument: stay on `feat/v4-reconcile-loop` and stack `feat/m4-*` branches on top of it, one per leg. Reasons:
- V2 D-58 fix is already on `feat/v4-reconcile-loop` (@dddb304, D-68). M4 depends on that fix.
- V2, V3, V4 pushes remain a prerequisite from the resume plan. Stacking keeps the M4 branches ready to rebase once those pushes clear.
- One-branch-per-leg lets the operator narrow M4 by dropping a branch, not by rewriting a monolith.

Ordered commits, top of `feat/v4-reconcile-loop`:

Branch `feat/m4-textutil`:
1. `textutil: extract _normalize_newlines and domain_prefix helpers`. Files: `src/canon/textutil.py`, `tests/test_textutil.py`. No edits to `vault_mirror.py` or `frontmatter.py` yet (edits come in M4.2's branch where the reader can be tested against the shared helper).

Branch `feat/m4-transport` (stacked on `feat/m4-textutil`):
2. `transport: Protocol seam base + capabilities`. Files: `src/canon/transport/__init__.py`, `src/canon/transport/base.py`, `src/canon/transport/capabilities.py`, `tests/_fakes.py` (edited), `tests/test_transport_base.py`, `tests/test_transport_conformance.py`, `src/canon/__init__.py` (re-exports).
3. `transport: prose contract + decision log`. Files: `project-docs/M4-TRANSPORT.md`, `project-docs/M4-TRANSPORT-DECISIONS.md`.

Branch `feat/m4-vault-reader` (stacked on `feat/m4-transport`; the two legs are independent but stacking keeps the tree linear):
4. `vault-reader: whole-vault reader + fidelity`. Files: `src/canon/vault_reader.py`, `src/canon/vault_read_fidelity.py`, `tests/test_vault_reader.py`, `tests/test_vault_reader_fidelity.py`, `tests/fixtures/vault_reader/*.md`, `src/canon/__init__.py` (re-exports). Also switches `vault_mirror.py` and `frontmatter.py` to import from `canon.textutil` (behavior-preserving refactor with existing test coverage).
5. `vault-reader: prose contract + decision log`. Files: `project-docs/M4-VAULT-READER.md`, `project-docs/M4-VAULT-READER-DECISIONS.md`.

Branch `feat/m4-versions` (stacked on `feat/m4-vault-reader`):
6. `versions: pin registry + refusal hierarchy`. Files: `src/canon/versions.py`, `tests/test_versions.py`, `src/canon/__init__.py` (re-exports).
7. `versions: migration seam`. Files: `src/canon/versions_migrate.py`, `tests/test_versions_migrate.py`.
8. `schema: alias SCHEMA to PIN_RECORD.kind_tag`. Files: `src/canon/schema.py`. Behavior-preserving.
9. `versions: prose contract + decision log`. Files: `project-docs/M4-VERSIONS.md`, `project-docs/M4-VERSIONS-DECISIONS.md`.

Branch `feat/m4-canon-check` (stacked on `feat/m4-versions`, optional):
10. `canon_check: composition report`. Files: `src/canon/canon_check.py`, `tests/test_canon_check.py`, `src/canon/__init__.py` (re-exports), `project-docs/M4-CANON-CHECK.md`.

Each commit message names the D-numbers it records. Each branch stays green on the full suite before the next stacks on top.

## Adversarial findings folded

- Versions D-numbers colliding with vault-frontend D-numbers: FOLDED (transport takes D-69..D-78, vault-frontend takes D-79..D-88, versions takes D-89..D-99, canon_check takes D-100).
- Transport `Receipt` naming collision with Wave 1 `canon.transform-receipt/v1`: FOLDED (renamed `TransportReceipt`).
- Transport `guard_push` size check calling `record.to_json()` before size gate: FOLDED (cheap-size heuristic added first, D-73 records the split).
- Vault-reader query language surface via `iter_notes` + `find_by_predicate`: FOLDED (deferred to Wave 2 with an explicit query Protocol).
- Versions "sprinkle SEAM_VERSION into every module" refactor: FOLDED (withdrawn; pins live centrally, callers use `pin_for`).
- Vault-reader `plan_read` using arbitrary directory traversal: FOLDED (reuses `is_vault_write_allowed` verbatim as ONE lexical gate).
- Transport at-least-once intra-batch duplicate: FOLDED (batch verbs deferred; single-record dispatch has no intra-batch case).
- Transport sha256 collision honest null: FOLDED (D-77).
- Transport `fetch_many` duplicate keys collapse: FOLDED (deferred with batch verbs).
- Transport partial-batch failure semantics: FOLDED (deferred with batch verbs).
- Vault-reader Windows MAX_PATH: FOLDED as honest null (D-85 caller's job).
- Vault-reader Windows junction cycle: FOLDED as honest null (lexical containment declines).
- Vault-reader UTF-16/UTF-32 BOM: FOLDED (`SKIPPED_ENCODING` verdict).
- Vault-reader `read_text` returning bytes: FOLDED (`SKIPPED_ENCODING` verdict).
- Vault-reader iterator-mid-delete: FOLDED (deferred with iterator surface; `read_vault` reads eagerly).
- Vault-reader NFC/NFD collision via `_slugify` NFKD: FOLDED (both normalizations produce the same derived name; test 31).
- Versions SchemaPin regex accepting `v01`: FOLDED (D-91; regex rejects leading zeros).
- Versions `v0` vs `v0.0` equality: FOLDED (D-91 pins `v0` canonical, refuses `v0.0`).
- Versions pre-release/build metadata: FOLDED (regex refuses; loud typed error, not bare `ValueError`).
- Versions `pin_registry_scope` under threaded caller: FOLDED (switched to `contextvars.ContextVar`, D-96).
- Versions migrator raising bare Exception: FOLDED (D-95 wraps as `MigratorRaised`).
- Versions `describe(pin)` unparseable: FOLDED (`describe(pin, form="json")` returns byte-stable JSON).
- Transport 220-line file gate risk: FOLDED (split into `base.py` + `capabilities.py`).
- Vault-reader 240-line file gate risk: FOLDED (dispatch-table structure keeps functions under 50; if tests overshoot, split into two test files).
- Versions 130-line estimate optimistic: FOLDED (split into `versions.py` + `versions_migrate.py`).
- `guard_push` 50-line function gate risk: FOLDED (splits into 6 helpers).
- `_normalize` duplication across vault_mirror + frontmatter + vault-reader: FOLDED (extracted to `canon.textutil` in commit 1).
- `guard_push(record)` vs `guard_put(backend, record)` signature drift: FOLDED (transport uses `guard_push(transport, record)`, D-69 records the shape match).
- Transport typed errors vs prior-band `ValueError` inconsistency: FOLDED (typed for structural refusals matching F1; `ValueError` for constructor/vocabulary faults matching `ConflictGatePolicy`).
- `MigratorConflict(ValueError, VersionError)` multi-inheritance: FOLDED (single inheritance under `MigrationError` root).
- Transport `list_all()` hardcoded scope pair: FOLDED (D-89 iterate `SCOPES`).
- Vault-reader totality: FOLDED (D-80; every refusal is a `NoteVerdict`, never a raise).
- Transport `CAP_TEMPORAL_PRESERVING` rename decision: FOLDED (D-78).
- Read-vault-scope raise vs verdict split: FOLDED (D-87).
- Transport `Receipt` name collision: already folded as `TransportReceipt`.
- Cross-band suggestion to add every kind-string constant to `SEAM_PINS`: DEFERRED (kind constants live under `PIN_RECORD`; a change is a `canon.record/v2` migration event, not a separate pin). Rationale in D-99's neighbor decision.
- Cross-band suggestion `WITNESS_KIND` in `SEAM_PINS`: FOLDED (added as `run-witness` pin in the pin table).
- Cross-band suggestion three separate decision logs: FOLDED (`M4-TRANSPORT-DECISIONS.md`, `M4-VAULT-READER-DECISIONS.md`, `M4-VERSIONS-DECISIONS.md`).
- Cross-band suggestion shared symmetric-report frozenset check: FOLDED (`test_declared_drops_are_both_literally_frozenset_empty`).
- Cross-band suggestion `contextvars.ContextVar` over `threading.Lock`: FOLDED (D-96).
- Cross-band suggestion `os.path` only in vault-reader (no `pathlib`): FOLDED (test asserts no pathlib import).
- Cross-band suggestion Protocol default-value 3.11 bug: FOLDED (Protocol methods carry no defaults; tests parametrize inputs).
- Cross-band suggestion `pickle` ban: FOLDED (`test_transport_imports_only_stdlib_data_modules`).
- Cross-band suggestion `typing_extensions` ban: FOLDED (same import test).
- Cross-band suggestion `time.time` ambient default ban: FOLDED (same import test extends to no `time.time` in default kwargs).
- Cross-band suggestion `collections.abc.Iterable` over deprecated `typing.Iterable`: FOLDED (Protocol shape uses `collections.abc.Iterable`).

## Standing gates (repeated)

- Path-leak scrub. Before any push-go, a separate commit runs a grep for `C:\`, `C:/`, `/c/dev`, and every operator-local absolute path across every file M4 touched. The scrub matches the discipline the audit named on 13 files / 206 lines. This commit lands on the same branch stack but is distinct from any M4 code commit so it can be reviewed on its own.
- No push-go authorized by this proposal. Push remains a separate operator ask on each M4 branch.
- No PR-go authorized by this proposal. PR remains a separate operator ask.
- No deploy-go authorized by this proposal. Deploy (the live cross-provider tunnel in the relay repo) remains a separate operator ask on top of any transport push-go.
- V2 D-58 fix has landed on this session (commit @dddb304, D-68). The V2/V3/V4 push prerequisite in the resume plan still owes; M4 branches stack ready to rebase.

## What the operator is being asked

Explicit build-go on the M4 scope as written above. Three options:

1. **Build as scoped.** Ship M4.1 transport + M4.2 vault frontend + M4.3 versions + optional M4.4 canon_check. Ten commits across five stacked branches on top of `feat/v4-reconcile-loop`. Full suite reaches 547 tests. Every leg stays a Protocol-only seam. No push, no PR, no deploy.

2. **Build narrower.** Drop one or more legs. Recommended drop order if narrowing:
   - Drop M4.4 canon_check first. Value is small; callers can compose the five verdict-returning functions in a five-line helper.
   - Drop M4.3 versions second if narrowing further. The pin registry is prep for a future migration event that has no caller yet.
   - Keep M4.1 transport and M4.2 vault frontend as the minimum viable M4. The transport Protocol seam is the shape a future relay integration will wire against. The vault reader closes the round trip R2 opened and is a standalone win.

3. **Hold.** Wait until the V2/V3/V4 pushes clear before opening M4 branches. This proposal's scope stays valid; the branches stack against whatever `main` looks like post-push.

Return with the option chosen. If narrower, name which legs to drop. If hold, name any change to scope the wait should absorb.