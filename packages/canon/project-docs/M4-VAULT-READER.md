# M4.2 — the vault frontend

M4.2 closes the round trip R2 opened. R2's write leg renders a pool into an
Obsidian-shaped vault of one note per record. M4.2's read leg walks that vault,
classifies every entry into an OK status or a typed refusal, and hands the
caller back a pool that is byte-identical to what R2 would have committed for
the same set. The reader raises nothing; every hostile input is a verdict.

Code: `src/canon/vault_reader.py`, `src/canon/vault_read_fidelity.py`. Tests:
`tests/test_vault_reader.py`, `tests/test_vault_reader_fidelity.py`. Everything
is stdlib-only; the vault filesystem is injected the way F1 injects a store
handle and M4.1 injects a wire handle (D-72).

## The interface

The reader ships six public entry points and one result dataclass.

| callable | contract |
|---|---|
| `read_vault(root, *, list_dir, read_text) -> VaultReadResult` | whole-vault read; classify then dedupe; `ok` is true iff every status is in `OK_STATUSES` |
| `read_vault_scope(root, scope, *, list_dir, read_text) -> VaultReadResult` | one scope's directory; `ValueError` if `scope` is not in `SCOPES` (D-87) |
| `classify_vault(root, *, list_dir, read_text) -> ReadPlan` | phase 1 only, mirrors V4 D-62 |
| `load_from_plan(plan) -> VaultReadResult` | phase 2, folds a plan into a pool + verdicts |
| `read_note_at(root, relpath, *, read_text) -> NoteVerdict` | single-entry reader, runs containment |
| `classify_vault_entry(root, relpath, text) -> NoteVerdict` | pure per-entry classifier; no IO |
| `read_exit_code(result) -> int` | 0 on `ok`, 1 on any refusal; mirrors `drift_exit_code` and `reconcile_exit_code` |

The injected IO is duck-typed. `list_dir(root)` yields POSIX relpaths under
`root`; `read_text(path)` returns `str` for a present file, `None` for a
race-loss delete, `bytes` for a caller wiring mistake (see step 4 below).

`OK_STATUSES = frozenset({LOADED, SKIPPED_HUB, SKIPPED_NOT_ALLOWED,
SKIPPED_ABSENT, SKIPPED_NOT_MARKDOWN, SKIPPED_ENCODING})`. Thirteen
`REFUSED_*` statuses fall outside the set and turn `ok` to false.

## The ingestion pipeline

Twelve steps run per relpath, in sorted `list_dir` order so a rerun on the same
filesystem returns identical verdicts (D-83). Each step is a small helper under
the 50-line function gate:

1. `is_vault_write_allowed(root, target)` runs first. One lexical containment
   gate, reused verbatim from R2's write leg (D-79). Any path the write leg
   would refuse to touch is a path the read leg refuses to source.
2. Hub short-circuit. Top-level `MEMORY.md` becomes `SKIPPED_HUB` without a
   content read (D-82). The write leg owns the hub; the reader never consults
   it.
3. `read_text(target)` returns `None` → `SKIPPED_ABSENT`. A listing raced a
   delete; the entry existed at enumeration and does not now.
4. `read_text` returns `bytes` instead of `str` → `SKIPPED_ENCODING`. A caller
   wired the wrong callable; the reader declines to guess an encoding.
5. First bytes are a UTF-16 or UTF-32 BOM → `SKIPPED_ENCODING`. A UTF-8 BOM
   at the head falls through to `REFUSED_MISSING_FENCE`; the reader never
   silently strips it.
6. `_normalize_newlines(text)` folds CRLF and bare CR to LF. Shared helper in
   `canon.textutil`, so the vault-write leg and the vault-read leg speak the
   same byte grammar.
7. `frontmatter.parse_frontmatter(text)` runs. Every `FrontmatterError`
   folds to a typed `REFUSED_*` verdict.
8. `vault.ingest_note(text)` reconstructs the record from the `canon:` JSON
   alone. Body, heading, per-kind body, and the `## canon links` trailer are
   ignored (R2 D-27).
9. `validate_record(record)` returns problems → `REFUSED_INVALID_RECORD`.
10. `normcase(derive_note_name(record))` fails to match `normcase(relpath)` →
    `REFUSED_SPOOF`. A hostile id that maps onto a legitimate note's path is
    caught here.
11. `parts[0]` (the scope directory the file lives in) fails to match
    `record.scope` under `normcase` → `REFUSED_MIS_SCOPE` (D-84, mirroring R1
    D-18).
12. Otherwise → `LOADED`.

After phase 1, `_dedupe_verdicts` runs. Two `LOADED` verdicts sharing
`record_key(record)` fold to `REFUSED_DUPLICATE_KEY` on the second (D-83
first-wins). Two `LOADED` verdicts sharing a `normcase`d relpath fold to
`REFUSED_NAME_COLLISION` on the second; an actual sha256-truncation collision
on the derived name is astronomically improbable (D-77's twin), so the branch
is a defensive backstop and gets its coverage at the `_dedupe_verdicts` unit
level.

## The refusal set

Every one of the following is a `NoteVerdict` with a `REFUSED_*` status. The
reader never raises.

| status | condition |
|---|---|
| `REFUSED_MISSING_FENCE` | no leading `---`, or a UTF-8 BOM prefix breaks the fence, or the file is empty |
| `REFUSED_UNCLOSED_FENCE` | no matching closing `---` |
| `REFUSED_NO_CANON_KEY` | fence exists, zero `canon:` lines present |
| `REFUSED_MULTIPLE_CANON_KEYS` | two `canon:` lines; refuses ambiguous authority |
| `REFUSED_MALFORMED_SCALAR` | a `canon:` value that fails the constrained single-quoted-scalar grammar |
| `REFUSED_INVALID_JSON` | `json.loads` raised on the scalar payload |
| `REFUSED_INVALID_SCHEMA` | a structural key is missing from the reconstructed record |
| `REFUSED_INVALID_RECORD` | `validate_record` returned problems |
| `REFUSED_IDENTITY_MISMATCH` | `derive_note_name(record)` fails to match the on-disk relpath |
| `REFUSED_SPOOF` | a hostile id whose spelling would forge a filename it does not own |
| `REFUSED_MIS_SCOPE` | `record.scope` fails to match the scope directory the file lives in |
| `REFUSED_DUPLICATE_KEY` | two loaded records share `(scope, id)`; first-wins |
| `REFUSED_NAME_COLLISION` | two loaded records derive to the same `normcase`d relpath |

The five `SKIPPED_*` statuses (`HUB`, `NOT_ALLOWED`, `ABSENT`,
`NOT_MARKDOWN`, `ENCODING`) name the paths the reader deliberately walks past.
`SKIPPED_NOT_ALLOWED` covers the root itself, an absolute path escape, a `..`
traversal, a top-level entry that is not `MEMORY.md`, an ad-hoc path deeper
than one scope level, a directory named for a non-canon scope, a dotfile, a
`.md.bak` or `.md.tmp` sibling, and a cross-drive `ValueError` caught inside
`is_vault_write_allowed`.

## Containment

The read leg imports `vault_mirror.is_vault_write_allowed` and calls it as its
one lexical gate. The rules the gate enforces are unchanged from R2:

- `normpath` and `normcase` on both target and root.
- Refuse the root itself.
- Refuse when `commonpath([root, target])` is not `root`.
- Admit only `{scope}/<name>.md` (scope in `SCOPES`, case-folded) or top-level
  `MEMORY.md`.
- Catch `ValueError` from a cross-drive or mixed abs-rel comparison; classify
  as `SKIPPED_NOT_ALLOWED`.

No `pathlib.Path.resolve()` runs. No `realpath` is called. Symlink-follow lives
in the caller's `list_dir`; the reader is lexical only, so a symlink that
points outside the vault does not become an escape vector on the reader side.
Junctions and MAX_PATH on Windows are the caller's problem (D-85 honest-null
neighborhood).

## The symmetric round-trip verdict

`vault_symmetric_report(records) -> VaultReadVerdict` is the whole-vault twin
of R2's `vault_fidelity` gate. R2 asserts the single-note codec is lossless;
the read-side fidelity gate lifts the same guarantee to the vault as a whole.

The report walks four steps:

1. `plan_vault(records)` writes into a `FakeFS`. Any `VaultError` on the write
   leg folds into the verdict as a `Refusal(where="write")`, and the report
   returns `ok=False` without proceeding.
2. `read_vault(root, list_dir=fs.list_dir, read_text=fs.read_text)` reads the
   vault back. Every non-OK verdict folds into the verdict as a
   `Refusal(where="read")`.
3. `_diff_pools(records, result.pool)` matches records by `record_key` and
   diffs each pair with R2's `classify_note_losses`. A record present on one
   side and absent on the other is a `Refusal(where="read")`, since the field
   diff has no side to diff against.
4. `ok = write_ok and read_ok and pool_matches and not losses and not refusals`.

`DECLARED_READ_DROPS: frozenset = frozenset()` (D-86, symmetric to
`vault_fidelity.DECLARED_NOTE_DROPS`). The write leg is lossless, the read leg
opens no side-channel that could drop a field, so every observed difference is
UNDECLARED and fails the verdict closed. A future contributor who extends one
declared-drop set without extending the other trips the shared-asymmetry
check.

`FakeFS` models the injected IO in memory. `read_text` returns `None` on
absent, `write_text` records to a `writes` list and stores the content by
`normcase`d absolute path, `list_dir` yields the POSIX relpaths of every file
under a root by prefix match. No host filesystem is touched.

## Totality

`VaultReadResult(pool, verdicts, refusals, ok, ...)` is a frozen dataclass.
`ok` is `True` iff every verdict's status is a member of `OK_STATUSES`. No
branch of the reader raises `FrontmatterError`, `VaultError`, `ValueError`,
`KeyError`, or any other exception to the caller. `read_vault_scope` raises
`ValueError` only when the caller passes a scope string outside `SCOPES`; that
is a wiring fault, distinct from runtime data (D-87).

`read_exit_code(result)` returns 0 iff `result.ok`, 1 on any refusal. The
signature and the semantics mirror `drift_exit_code` and
`reconcile_exit_code`, so a build that already keys on those two total gates
picks up the third with no bespoke wiring.

## What stays out

Query surface: no `filter_scope`, `filter_kind`, `filter_predicate`,
`find_by_predicate`. A predicate callable defines a query Protocol canon does
not have. Wave 2 lands a query layer under its own approval.

Iterator surface: no `iter_notes`, no `iter_scope_notes`. M4.2 reads
whole-vault eagerly. A caller who needs streaming for a large vault composes
`sorted(list_dir(root))` themselves and calls `read_note_at` per entry.

Vault mutation: no write, no delete, no move, no hub rewrite. The read leg is
read-only. Any mutation is R2's write leg or a caller's own.

Real-filesystem walking: no. `list_dir` and `read_text` are injected. Symlink
resolution, MAX_PATH handling, junction handling, dotfile filtering all live
in the caller.

Cross-vault merge: no. Single-root by construction. A caller merging two
vaults reads each with `read_vault` and folds the pools themselves.

File watching, incremental read, delta snapshots: none. Every call is a whole
read.

Byte-size ceilings: no per-note ceiling (D-85, honest null). A caller's
`read_text` may impose one by returning `None` or raising above threshold.

BOM-tolerant reads: no. R2's byte discipline holds; a UTF-16/UTF-32 BOM at the
head is a `SKIPPED_ENCODING`, a UTF-8 BOM is a `REFUSED_MISSING_FENCE`.

Body validation: no. The body is ignored per R2 D-27. A hand-edited body under
an intact carrier loads cleanly; the record returned is the one the carrier
declares.

`pathlib` import: none. `os.path` only.

`pickle`, `typing_extensions`, ambient `time.time()`: none.

Cross-process locks, CAS, tombstones: none. V4 D-66's non-transactional
boundary carries; two writers racing a rename can produce a moment where a
listing sees a stale name and a live name. The reader classifies each verdict
independently; a caller who needs a snapshot points `list_dir` and `read_text`
at one.
