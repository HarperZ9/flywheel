# F1 — the storage seam

F1 adds one interface, `MemoryBackend`, and four adapters that satisfy it. The
renderer, the migration legs, and the round-trip proof (R0) all speak to a store
through this single shape and never to a concrete engine. A backend holds
canonical Records and returns them field-identical, except for the fields it has
openly declared it cannot hold. That declaration is the whole contract.

Code: `src/canon/backends/`. Tests: `tests/test_backend_base.py`,
`tests/test_{files,sqlite,mneme,flywheel}_backend.py`,
`tests/test_declared_drops.py`. Everything here is stdlib-only; the two adapters
over external engines take an injected store handle and import no engine package
(see D-9 in F1-DECISIONS.md).

## The interface

`MemoryBackend` is a `runtime_checkable` Protocol with a `name` and six members:

| member | contract |
|---|---|
| `name: str` | short backend id, used in errors and the drops table |
| `supported_kinds() -> frozenset[str]` | the record kinds it holds; `put` refuses others |
| `declared_drops() -> frozenset[str]` | capability tokens a round-trip loses |
| `flatten(record) -> Record` | a copy safe to `put`, with removable dropped capabilities stripped; identity when nothing is removable |
| `put(record) -> None` | store one record; raises per `guard_put` |
| `get(key) -> Record \| None` | the record under `key` (from `record_key`), or `None` |
| `records() -> list[Record]` | every record held, order unspecified |

The store key is the `(scope, id)` pair rendered as `f"{scope}/{id}"`
(`record_key`), not `id` alone. A personality-block is deliberately present at
both `global` and `workspace` under one id (the override case, D-2), so scope is
part of the identity a backend stores under. `split_key` inverts it on the first
separator, so an id may itself contain a slash.

## The capability model

`declared_drops()` returns tokens from a fixed vocabulary of five:

| token | meaning |
|---|---|
| `temporal` | the supersede / valid_until history block |
| `audit-chain` | a re-verifiable hash-chained write ledger |
| `relations` | typed graph edges between records |
| `arbitrary-kind` | entity kinds beyond this backend's native set |
| `foreign-provenance` | a provenance receipt written by another harness |

A drop is one of two kinds, and the difference decides whether a put can refuse.

A **record-enforceable** drop is one a single record can trigger by its own
fields. F0's envelope has exactly one: `temporal`, live when a record carries a
non-null `valid_until` or `supersedes`. `guard_put` refuses such a record on a
backend that dropped `temporal`, so the loss is never silent: the caller must
`flatten()` first and thereby opt into it. `RECORD_ENFORCEABLE` is exactly
`{temporal}`.

A **structural** drop (`audit-chain`, `relations`, `arbitrary-kind`,
`foreign-provenance`) is a property of the store, not of one record's fields. It
is declared and documented but cannot be triggered by a lone record, so
`guard_put` never raises on it. Kind support is enforced on its own track: a
record whose kind is outside `supported_kinds()` raises `UnsupportedKind`
regardless of any drop.

## The four profiles

| backend | `name` | supported kinds | declared drops |
|---|---|---|---|
| FilesBackend | `files` | all five | `{audit-chain}` |
| SqliteBackend | `sqlite` | all five | `{}` (zero-drop reference) |
| FlywheelBackend | `flywheel` | all five | `{temporal}` |
| MnemeBackend | `mneme` | episodic-memory, synthesized-persona-l3 | `{arbitrary-kind, relations, foreign-provenance}` |

### FilesBackend

One JSON file per record at `{root}/{scope}/{quote(id)}.json`, written as the
record's `to_json()` and read back field-identical. It holds every kind and
loses no record field, including live temporal history. What it lacks is a
hash-chained audit, so it declares `audit-chain` dropped rather than present a
directory of files as if it carried a verifiable chain. Integrity for a files
store is the surrounding version control, kept as an honest null.

### SqliteBackend

A single SQLite file holds every record verbatim keyed by `(scope, id)`, and
every write appends to a hash-chained `audit` ledger the owner re-walks with
`verify_chain()`. It holds every kind, loses no field, and carries the audit
chain a files store drops, so its `declared_drops()` is empty. This is the
zero-drop store R0 measures the others against. The chain hash for a row is
`sha256(prev_chain + key + record_sha)`, genesis `"0" * 64`; `verify_chain`
recomputes each row from the prior and returns `{ok, length}`, `ok` false at the
first mismatch. A re-put of the same key upserts the record row and appends a new
ledger row, so the ledger is append-only while the record set stays deduplicated.

### FlywheelBackend

Authored blocks and any non-temporal kind, mapped onto an injected flywheel
store. The whole canonical envelope is stored in flywheel's opaque `data` blob,
keyed by `(scope, id)` as the entity id and namespaced by `project=canon:<scope>`
so canon's records stay isolated in a store it may share. A calm record round-
trips field-identical, provenance included.

Its one drop is `temporal`: flywheel's `entities` table has no history columns,
so it holds only current records. A record carrying live temporal history is
refused by `put`; the caller stores it current-only by calling `flatten()` first,
which strips the temporal block to null. Either way `temporal` is declared
dropped and mneme remains the home for anything whose history matters.

flywheel surface used (injected, duck-typed): `put_entity(kind, data, *,
project, eid)`, `get_entity(eid)`, `query_all_entities(*, kind, project, chunk)`.

### MnemeBackend

The two memory kinds mapped onto an injected mneme Store; the temporal home. It
keeps the supersession pairing: a supersede is recorded as mneme's `supersede()`
between two present rows and read back from each row's `valid_until` and
`superseded_by`. It does not accept a caller-supplied ordinal: mneme assigns
`valid_until` itself from its own monotonic clock, so the adapter refuses an
incoming one rather than dropping it silently (see the two refusals below).

Field mapping:

| canon | mneme | note |
|---|---|---|
| `scope` | `user` column | canon has no separate user at F1; ids are unique, so no cross-scope collision |
| `provenance.session_id` | `session` | preserved |
| `data.{layer,text,source_ids,extractor,criterion}` | the memory row columns | `source_ids` is stored by mneme as JSON text; the adapter `json.loads` it on read |
| `temporal.valid_until` | row `valid_until` | read back, but assigned by mneme on `supersede`; an incoming value is refused (see below) |
| `temporal.supersedes` | derived from the inverse `superseded_by` pointer | see below |
| `kind` | derived from `layer` | `L3` maps to synthesized-persona-l3, else episodic-memory |

The supersede pointer is inverse between the two systems. canon's `supersedes` is
the id of the record this one replaces (the older one). mneme stores the forward
pointer: an old row's `superseded_by` names the newer row. The adapter
reconstructs canon's direction with `_reverse_from(rows)`, mapping each
`superseded_by` back to `{newer_id: older_id}`, so reading the newer record
yields `supersedes = older_id`.

Two temporal put-time refusals keep the loss visible rather than silent. A record
carrying a non-null `temporal.valid_until` is refused with `DropError`: mneme owns
the ordinal clock and cannot store a caller's value, so the caller `flatten()`s
(which strips `valid_until` and keeps `supersedes`) and re-puts, storing the
record current-only. A record whose `supersedes` names a row that is not present
and current is refused with `MissingSupersedeTarget`: mneme links only between two
present rows, so the superseded record must be stored first. This second refusal
is an ordering precondition, not a dropped field, so `flatten()` does not resolve
it. Neither `temporal` refusal is a declared drop: mneme keeps the supersession
pairing, so `temporal` is not in its `declared_drops()`; these are backend-native
put-time refusals on their own track, like `UnsupportedKind` for kind.

Its drops: mneme models memory, not a graph, so it refuses every non-memory kind
(`arbitrary-kind`) and holds no typed relations (`relations`). And its rows carry
their own provenance columns (a content hash, a created ordinal), not canon's
full receipt, so a provenance written by another harness is normalized to the
mneme-derived shape on read (`foreign-provenance`). Derived on read:
`harness="mneme"`, `source_hash=row.content_sha256`, `native_id=f"mneme:{id}"`,
`create_ord=row.created_ord`. Content, scope, session, and the supersession
pairing round-trip; a foreign provenance receipt does not, and a caller-supplied
`valid_until` is refused rather than carried. See Drop 4 in F0-DECLARED-DROPS.md.

mneme surface used (injected, duck-typed): `add_memory(memory_id, layer, text,
source_ids, extractor, criterion, session, user)`, `memory(memory_id)`,
`memories(*, include_superseded)`, `supersede(old_id, new_id, reason)`.

## What F1 does not do

F1 is the seam and its adapters, nothing that renders a file. It does not decide
which backend a record lives in (that is the migration and render layer), and it
holds no live connection to the real mneme or flywheel processes: the two
external adapters are proved against fakes that mirror the source surfaces read
this session. Wiring a real engine handle in is a later phase. R0, the block
round-trip go/no-go gate, is the next band-1 sibling and lands on its own branch.
