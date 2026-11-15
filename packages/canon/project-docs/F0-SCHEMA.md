# F0 — the canonical record

The record every backend and every render target aims at. One envelope, five
kinds. This is the F0 contract; a downstream slice may add optional fields to a
kind's `data`, but changing the envelope or a kind's required fields means
editing this doc, `src/canon/schema.py`, `src/canon/validator.py`, and the
fixtures together.

## Envelope

```
{
  "canon_schema": "canon.record/v1",
  "kind":  <one of the five kinds>,
  "id":    <non-empty string, stable across rewrites of the same entry>,
  "scope": "global" | "workspace",
  "data":  { ... kind-specific typed payload ... },
  "provenance": { ... receipt, see below ... },
  "temporal":   { ... supersede block ... } | null
}
```

`id` is the identity used by layering: a workspace record overrides a global
record with the same id. It is stable across a rewrite of the same entry, so
editing a block keeps its id and supersedes the prior version.

`scope` has exactly two values. There is no `repo` scope. The ~90 per-repo
instruction files stay hand-authored so each repo stays self-contained; no
record is ever scoped to a repo.

## Provenance (on every record)

```
{
  "harness":      <required, non-empty: who produced this, e.g. "mneme", "claude-code">,
  "source_hash":  <required, lowercase 64-hex sha256 of the source>,
  "native_id":    <the id in the source system, or null>,
  "session_id":   <originating session, or null>,
  "create_ord":   <clock-free ordinal for deterministic ordering, or null>,
  "create_time":  <wall-clock string, nullable, NEVER authoritative>,
  "model_slug":   <model that produced it, or null>
}
```

`create_ord` is the ordering key. It is an integer ordinal, not a timestamp, so
a rebuild from the same inputs orders identically regardless of when it runs.
`create_time` exists only as a human convenience and is never used for ordering,
supersede, or equality.

## Temporal (only on the four temporal kinds)

```
{ "valid_until": <ordinal at which this stopped being current, or null>,
  "supersedes":  <id of the record this replaces, or null> }
```

A record is **current** when it has no temporal block, or its `valid_until` is
null. A non-null `valid_until` means the record was superseded and is excluded
from a live render. `supersedes` names the prior record by id.

`research-artifact-ref` is the one kind that must not carry a temporal block: an
artifact is content-addressed and immutable, so a new artifact is a new ref, not
a supersede-in-place. The validator rejects a temporal block on that kind.

## The five kinds

| kind | `data` required fields | temporal? | source of record |
|---|---|:---:|---|
| `personality-block` | `title`, `body` | yes | authored block store (flywheel) |
| `episodic-memory` | `layer` (L0/L1/L2), `text`, `source_ids` | yes | mneme L0–L2 |
| `synthesized-persona-l3` | `layer` (=L3), `text`, `source_ids` | yes | mneme L3 |
| `adr-decision` | `title`, `status`, `context`, `decision` | yes | decision log (F3) |
| `research-artifact-ref` | `artifact_hash` (sha256), `locator` | **no** | gather corpus |

`adr-decision.status` is one of `proposed`, `accepted`, `superseded`,
`rejected`. `episodic-memory.layer` is one of `L0`, `L1`, `L2`.
`synthesized-persona-l3.layer` is exactly `L3`. `research-artifact-ref.artifact_hash`
is a lowercase 64-hex sha256.

## W1 addendum: the workspace-state kinds

W1 adds three kinds on the same envelope. They are stamped
`"canon_schema": "canon.workspace-state/v1"` instead of `canon.record/v1`, so a
reader that knows only the five kinds above refuses them by tag, and every
record of the five kinds keeps its tag and its bytes. `schema_tag_for(kind)` is
the one place the tag is chosen, and `Record.from_dict` refuses a record whose
tag does not match its kind in either direction.

| kind | `data` required fields | optional fields | temporal? |
|---|---|---|:---:|
| `workspace-focus` | `goal` | `areas` (list of text), `branch`, `notes` | yes |
| `work-item` | `title`, `status` | `detail` | yes |
| `environment-constraint` | `statement`, `category` | `reason`, `applies_to` (list of text) | yes |

`work-item.status` is one of `open`, `in-progress`, `blocked`, `done`,
`dropped`. `environment-constraint.category` is `constraint` or `quirk`.

`adr-decision` gains one optional field, `rejected_alternatives`: a list of
objects each carrying exactly a non-empty `option` and a non-empty `reason`.
The field is additive, so a decision record keeps the `canon.record/v1` tag, a
decision without the field stays valid, and a 0.2.0 reader ignores the field
rather than refusing the record.

`personality-block` gains one optional field, `applies_to`: a non-empty list of
glob patterns naming the files the block is meant for. It is additive and the
block keeps `canon.record/v1`. See `W1-WORKSPACE.md` for how each target
handles it.

`KINDS` stays the five `canon.record/v1` kinds; `ALL_KINDS` is what the
validator admits. The four storage adapters still hold `KINDS` only; the
workspace-state kinds live in the per-project store described in
`W1-WORKSPACE.md`.

## Round-trip guarantee

`Record.from_dict(rec.to_dict()) == rec` for every kind, field-identical, with
no field lost, added, or coerced. Proved in `tests/test_schema_roundtrip.py`
against the five on-disk fixtures. `to_json`/`from_json` are stable across
repeated round-trips.

## What F0 deliberately does not do

- No storage. The MemoryBackend Protocol and its adapters are F1.
- No rendering. The deterministic renderer and its scope-guard are R-family.
- No id minting, no hashing of sources, no clock. A record arrives with its
  provenance already filled; F0 validates and layers it, nothing more.
