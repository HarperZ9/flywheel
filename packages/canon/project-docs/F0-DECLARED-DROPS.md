# F0 — declared drops

A backend that cannot hold a field of the canonical record must **declare** the
drop, not silently lose it. This doc fixes the drops F0 already knows about,
each cited to real code read directly in the two engines canon assembles over.
The F1 MemoryBackend Protocol carries a `declared_drops()` method; these are its
entries, and the Status section below records where F1 made them executable.
Confidence on each citation: high (verified by full read of
the cited file this session). Line numbers are from that read and may shift as
those upstream files change; the symbol names are the durable anchor.

## Drop 1 — a flywheel-backed record drops mneme's temporal history

**What is lost:** the `temporal` block. A record superseded in mneme (a
`valid_until` set, a `supersedes` pointer) cannot represent that history in the
flywheel store.

**Evidence.**
- flywheel `harness/store.py` — the schema in `_init` (store.py:47) defines
  `entities(eid, kind, project, data, sha256, created)` and
  `relations(...)` with no `valid_until`, no `superseded_by`, no temporal column
  anywhere. Rows are stamped with wall-clock `time.time()` (store.py:74, :92,
  :151), not an ordinal, so even ordering is clock-bound.
- mneme `src/mneme/store.py` — `supersede(old_id, new_id, reason="")`
  (store.py:387) sets `valid_until` (store.py:397) and `superseded_by` on the old
  memory. `memories(..., as_of=None, include_superseded=False)` (store.py:364)
  reads that history back.

**Declaration.** A flywheel-backed store holds only current records. A record
with a non-null `valid_until` is either refused or flattened to current-only;
either way the backend declares `temporal` dropped. mneme remains the backend of
record for anything whose history matters.

## Drop 2 — a mneme-backed record drops flywheel's arbitrary-kind graph

**What is lost:** arbitrary entity kinds and typed relation edges. mneme models
memory, not a general graph.

**Evidence.**
- mneme `src/mneme/schema.py` — the store's tables are `turns`, `memories`, a
  key/value `meta` table, and a hash-chained `audit` table (schema.py:13, :18,
  :28, :29); none is a relations table and none carries an arbitrary entity
  `kind`. A memory is added by `add_memory(memory_id, layer, text, source_ids,
  extractor, criterion, ...)` (store.py:323) and `layer` must be one of the four
  `LAYERS`.
- flywheel `harness/store.py` — `put_entity(kind, data, *, project="",
  eid=None)` (store.py:78) accepts any `kind` string, and `put_relation(src,
  dst, kind, *, project="")` (store.py:142) records a typed edge between two
  entities. mneme has no analogue of either.

**Declaration.** A mneme-backed store holds the memory kinds
(`episodic-memory`, `synthesized-persona-l3`) natively and declares
arbitrary-kind entities and typed relations dropped. A record whose meaning is a
graph edge belongs in the flywheel-backed store.

## Drop 3 — a plain-files backend drops the hash-chained audit

**What is lost:** chain verification. flywheel's store keeps a hash-chained
audit table; a net-new FilesBackend that writes JSON files has no equivalent
until it builds one.

**Evidence.**
- flywheel `harness/store.py` — `verify_chain()` (store.py:173) and
  `verify_records()` (store.py:192) validate a hash-chained `audit` table: each
  row commits to the prior, so tampering is detectable.
- mneme `src/mneme/store.py` — `verify_audit()` (store.py:476) is mneme's own
  analogue for its memory audit.
- The F1 FilesBackend is net-new and has neither table.

**Declaration.** A FilesBackend declares the audit chain dropped, or it adds its
own before claiming chain verification. It must not present unverifiable files
as if they carried a chain. Honest null: F0 ships no FilesBackend, so this drop
is declared in advance for the F1 slice that adds one.

## Drop 4 — a mneme-backed record drops a foreign provenance receipt

**What is lost:** a provenance receipt written by a harness other than mneme. The
`harness`, `source_hash`, `native_id`, `create_ord`, `create_time`, and
`model_slug` a foreign harness stamped cannot be held; mneme derives provenance
from its own row columns instead.

**Evidence.**
- mneme `src/mneme/schema.py` — a memory row is `id, layer, session, "user",
  text, source_ids, extractor, criterion, content_sha256, created_ord,
  valid_until, superseded_by, source_hashes`. There is no `harness` column, no
  `model_slug`, no `create_time`; `content_sha256` is mneme's own content hash
  and `created_ord` is mneme's own assigned ordinal, not a foreign harness's
  `source_hash` or `create_ord`.
- canon `src/canon/schema.py` — `Provenance(harness, source_hash, native_id,
  session_id, create_ord, create_time, model_slug)`. Only `session_id` lands in a
  real mneme column (`session`); the other six are re-derived from mneme's own row
  (`harness`, `source_hash`, `native_id`, `create_ord`) or dropped to null
  (`create_time`, `model_slug`), so a foreign harness's values for them do not
  survive.

**Declaration.** On read the MnemeBackend derives provenance from mneme's
columns: `harness="mneme"`, `source_hash=row.content_sha256`,
`native_id=f"mneme:{id}"`, `session_id=row.session`, `create_ord=row.created_ord`.
For a mneme-native record this is faithful. For a record that arrived from
another harness, the foreign receipt is normalized to this mneme-derived shape;
`source_hash` and `create_ord` come back re-derived, not as the foreign harness
wrote them. Content, scope, session, and the supersession pairing round-trip; a
foreign provenance receipt does not, and mneme's temporal handling has its own
put-time boundary (a caller-supplied `valid_until` is refused, not stored; see
F1-BACKENDS.md). Anything whose exact cross-harness provenance receipt must
survive belongs in the zero-drop SqliteBackend or a files store.

## Status — F1 made these executable

F1 shipped the `MemoryBackend` Protocol and its four adapters, so these drops are
now code, not prose. Each backend's `declared_drops()` returns its exact profile,
and `tests/test_declared_drops.py` pins the four profiles and the one
enforcement rule: a record-enforceable drop (`temporal`) refused at `put` time
when dropped, a structural drop (audit-chain, arbitrary-kind, relations,
foreign-provenance) declared but never able to block a lone `put`. The profiles:
FilesBackend drops `{audit-chain}` (Drop 3), SqliteBackend drops nothing,
FlywheelBackend drops `{temporal}` (Drop 1), MnemeBackend drops `{arbitrary-kind,
relations, foreign-provenance}` (Drops 2 and 4). See F1-BACKENDS.md.

## Why declared, not reconciled

canon is an assembly, not a superstore. The point of a declared drop is that a
record's home is chosen for what that record needs: temporal history goes to
mneme, graph edges to flywheel, and a backend never pretends to hold a field it
cannot. F1 makes `declared_drops()` executable and tests that each backend
refuses (or explicitly flattens) a record carrying a field it dropped.
