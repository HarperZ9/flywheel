# R2 — decisions of record

The decisions that frame the vault band, continuing the log in F0-DECISIONS.md,
F1-DECISIONS.md, R0-DECISIONS.md, and R1-DECISIONS.md and recorded in the same
shape the `adr-decision` kind captures. Each is accepted unless marked otherwise.

R2 is the second render band. R1 splices a scope's blocks into a shared
instruction file; R2 mirrors the whole pool into an Obsidian vault of one note
per record, plus a MEMORY.md index, and adds the SOUL.md instruction surface. It
ships four layers:

- `src/canon/frontmatter.py` — a constrained frontmatter codec. It emits a fixed
  set of single-quoted scalars and one authoritative `canon:` key that carries
  the whole record as verbatim JSON, and it reads only that key back.
- `src/canon/vault.py` — the one-record note codec. `render_note` projects a
  record to a whole markdown file (frontmatter carrier, heading, per-kind body,
  links trailer) and refuses any record it cannot faithfully project;
  `ingest_note` reconstructs the record from the carrier alone.
- `src/canon/vault_mirror.py` — the whole-vault orchestrator. `plan_vault`
  renders the pool into contained note paths plus the hub, plans the whole set
  against what is on disk, and commits only once nothing refuses.
- `src/canon/vault_fidelity.py` — the vault round-trip verdict. Because the note
  carrier is lossless, its declared-drop ledger is empty and any field difference
  fails the verdict closed.
- `src/canon/registry.py` — extended with the SOUL.md surface (a fourth catalog
  row), which reuses the R1 authored-split renderer unchanged.

## D-23 — the frontmatter codec is a constrained writer, not a YAML library
**Status:** accepted (this build, 2026-08-28).
**Context:** A note needs a frontmatter block a human and Obsidian both read, and
canon needs to read one field of it back reliably. A general YAML loader would
parse the block, but `yaml.load` on untrusted text is a known remote-code-execution
surface (`!!python/object/apply`), and a full loader's type coercion makes the
round trip depend on the loader's version and settings rather than on canon's own
rules.
**Decision:** canon hand-rolls a minimal codec. It emits exactly one value shape,
a single-quoted YAML scalar with every `'` doubled, which is the sole escape a
single-quoted scalar defines, so the emitted block is valid YAML for any reader.
On read it runs no loader at all: it normalizes line endings, anchors to the
leading `---` fence, takes the block up to the next bare `---`, finds the one line
that begins `canon: '`, undoes the escape, and hands the inner text to
`json.loads`. Every other scalar and the body are ignored on read.
**Consequence:** the `!!python/object` trap is inert, the read path has no
third-party dependency, and the field canon reconstructs from is fixed by canon's
own grammar, not a loader's. The cost is that the writer covers only the shapes
canon emits; it is not a general YAML serializer, and it is not meant to be.

## D-24 — a note is a whole-file projection of one record, carried by one JSON line
**Status:** accepted (this build).
**Context:** R0 splices a scope's blocks into a region inside a shared host file,
preserving every byte outside the region. A vault note is a different container:
it is a file that belongs entirely to canon, holding one record. The question is
what in that file is authoritative. The visible markdown is what a human edits in
Obsidian, but markdown is lossy against the record envelope (provenance, temporal,
the clock-free ordinal do not survive a prose round trip).
**Decision:** the frontmatter `canon:` key carries `record.to_json()`
(`json.dumps(sort_keys=True)`) verbatim as the single authoritative carrier. That
call is single-line even with embedded quotes, newlines, and unicode, so the whole
envelope rides one physical line inside the frontmatter. The heading, the per-kind
body, and the flat scalars are regenerated from the record on every render. The
note is a whole-file projection: canon owns the file, the carrier owns the record.
**Consequence:** the `render_note` → `ingest_note` round trip is byte-lossless on
every field, which is what D-33 and the R2 fidelity gate rely on. A note is never
merged into foreign bytes, so there is no outside-byte-preservation leg here the
way R0 has one. A record too large for a practical single line is out of scope for
this band; no current kind approaches that bound.

## D-25 — the links trailer projects record relations, never body prose
**Status:** accepted (this build).
**Context:** Obsidian's value is the `[[wikilink]]` graph. A note could grow its
links by scanning the rendered body for `[[...]]` tokens, or by reading the
record's own declared relations. Body prose is opaque content: a personality
block that quotes `[[some example]]` is not asserting a canon relation, and a
codec that treated it as one would invent edges the record never declared.
**Decision:** the `## canon links` trailer is built only from the record's own
relations: `temporal.supersedes` and `data.source_ids`. Body prose is never
parsed for links. An id that carries a wikilink-hostile character (`[`, `]`, `|`,
`#`, `^`, or a line break) cannot ride inside `[[...]]` without corrupting the
link, so it falls back to a safe `{slug}-{digest}` token that resolves through the
target note's `aliases`.
**Consequence:** the vault graph reflects exactly the relations records declare,
and a hand-edited body cannot forge or drop an edge. The trailer is absent when a
record holds no relation, which is an honest null rather than an empty header.

## D-26 — the hub reuses the surface renderer's sort key
**Status:** accepted (this build).
**Context:** MEMORY.md indexes every note. Its entry order is a presentation
choice, and the R1 surface renderer already fixed an order for a scope's blocks:
clock-free `create_ord` ascending, id as the tie-break, an absent ordinal last
(`layering._sort_key`). If the hub sorted by its own rule, the two orders would
drift, so the same records would list in one order inside CLAUDE.md and another in
MEMORY.md.
**Decision:** `render_hub` sorts each scope's records with `layering._sort_key`,
the exact key the surface renderer uses. The hub groups by scope (global before
workspace) and omits the H2 of an empty scope.
**Consequence:** vault order and surface order are locked to one definition and
cannot diverge. A change to canon's ordering rule moves both surfaces together,
because both call the one key.

## D-27 — the carrier is authoritative; the body is a one-way projection
**Status:** accepted (this build).
**Context:** A human opens a note in Obsidian and edits the visible body. On the
next mirror, canon must decide whether that edit feeds back into the record or is
overwritten. Feeding it back means parsing prose into a typed envelope, which is
lossy and ambiguous; overwriting it means the human's edit to the projection does
not survive.
**Decision:** the `canon:` carrier is authoritative and the body is a one-way
projection. `ingest_note` reconstructs the record from the carrier JSON alone and
never reads the heading, body, flat scalars, or links. A note whose visible body
was hand-edited but whose carrier is intact re-renders to the canon body and the
edit is discarded on the next mirror.
**Consequence:** the record has one source of truth, and the round trip is exact
because it never depends on prose. The honest cost, stated plainly in the note and
the hub marker (D-34): editing a note's body in Obsidian is not a durable way to
change a record. Durable edits go through the record, and the projection follows.

## D-28 — a fixed frontmatter key order
**Status:** accepted (this build).
**Context:** The flat scalars (`canon_schema`, `kind`, `id`, `scope`, `title`,
`aliases`) are a convenience for a human reading the note and for Obsidian's
property view. If their order varied between renders, a byte comparison of an
unchanged note would report a spurious change and the mirror would rewrite files
that did not actually change.
**Decision:** `FRONTMATTER_KEYS` fixes the emission order, and `emit_frontmatter`
always writes the block in that sequence with the `canon:` carrier last.
**Consequence:** an unchanged record renders to byte-identical frontmatter, so the
mirror's unchanged-detection holds and idempotence is provable.

## D-29 — identity, not content, names the file
**Status:** accepted (this build).
**Context:** A note needs a stable filename. Using the raw record id as the path
is unsafe: an id is operator or model text, and an id like `../../.ssh/authorized_keys`
would let a record escape the vault. Using a body hash would rename the file
whenever a human edited the projection.
**Decision:** `derive_note_name` returns `{scope}/{slug}-{16hex}.md`, where the
digest is `sha256` over the record's `(scope, id)` key under a fixed domain string
and the slug is a casefolded, ASCII-only, dash-collapsed, 60-char-capped rendering
of the id used only for human readability. The raw id never becomes a path
segment, so a traversal or absolute-path escape cannot form, and the name is
stable and case-fold-portable because it derives from identity, not from content.
**Consequence:** a hostile id cannot forge a path, the filename does not move when
a body is edited, and two records with the same key collide by construction (the
mirror refuses that collision in `_render_targets`). The domain string carries a
`v1` tag so a future scheme change is a distinct namespace.

## D-30 — an off-limits or spoofed file at a target fails the plan closed
**Status:** accepted (this build).
**Context:** The mirror writes into a directory a human also uses. A file may
already sit at a note's target path. It could be a hand-authored file the human
put there, or a canon note from an earlier mirror, or a file planted under a
canon-looking name to smuggle a record the pool did not choose.
**Decision:** before any write, the plan classifies every existing file at a
target. A file that does not parse as a canon note is off-limits and aborts the
whole plan, so the mirror never clobbers a hand-authored file. A file that parses
as a canon note but whose on-disk name does not re-derive from its own content is
a spoof and is refused. Only a file whose name re-derives from its carrier is
treated as canon's to overwrite. The same ownership rule guards the hub: an
existing MEMORY.md that does not open with the generated head (the H1 plus the
D-34 marker) is a hand-authored file, not canon's, and aborts the plan; a hub
that opens with it is canon's own and is overwritten when it differs, skipped when
it matches.
**Consequence:** the mirror overwrites only files it demonstrably wrote, refuses
to overwrite anything else, and cannot be tricked into adopting a record under a
name the pool did not choose. The hub has no `canon:` carrier to key on, so its
generated head is the ownership token; without that check the mirror would clobber
a MEMORY.md a human wrote by hand at the vault root. Installing the mirror into a
directory that already holds a non-canon file of the same name is a deliberate act
a human resolves, not something the mirror does silently.

## D-31 — vault containment is a lexical allow-list
**Status:** accepted (this build).
**Context:** Every vault write must land under the injected vault root. The guard
could resolve symlinks with `realpath`, which touches the filesystem, or compare
paths lexically, which does not. This mirrors the R1 registry guard (D-20).
**Decision:** `is_vault_write_allowed` normalizes both sides with `normpath` and
`normcase`, refuses the root itself, requires `os.path.commonpath([root, target])`
to equal the root so a traversal that escapes fails, and then checks the relative
tail's shape: a top-level `MEMORY.md`, or `{scope}/<name>.md` for a known scope,
and nothing else. The guard is pure and injectable, so it is provable without a
filesystem.
**Consequence:** every planned path is contained before a byte moves, the guard is
testable with fake roots and no disk, and the threat it defends is "canon computes
a path outside the vault", not "the human's tree is hostile". A symlink planted at
an allow-listed path is out of scope for the same reason it is in R1. Orphan
discovery reuses the same predicate as its read-side gate: an on-disk entry that
is outside the root or off the note-target shape is skipped before it is read, so
a traversal in the listing cannot pull canon into reading foreign bytes. Because
the predicate case-folds, and discovery folds case on its hub, target-membership,
and spoof comparisons too, a case-only variant of a target on a case-insensitive
filesystem is recognized as that target rather than misfiled as a spoof.

## D-32 — an orphan is reported, never deleted
**Status:** accepted (this build).
**Context:** A record dropped from the pool leaves its note on disk with no record
behind it. The mirror could delete that stale note to keep the vault in exact
correspondence with the pool, or leave it and report it.
**Decision:** `_discover_orphans` finds every canon note under the mirror whose
key is absent from the pool and reports each as an `orphan` result. The mirror
never deletes it. Deletion is a human's call.
**Consequence:** the mirror never destroys a note, so a pool computed wrong (a
backend that returned a short read, a filter that dropped records) cannot cascade
into data loss. The vault can carry stale notes until a human prunes them, which
is the safe default for a directory a human owns. A spoofed orphan (a canon note
whose name does not re-derive) is still refused, because a name mismatch is a
different fault from a stale-but-honest note.

## D-33 — R0's render-superset invariant is carried to the vault leg
**Status:** accepted (this build).
**Context:** R0 established (D-13) that a surface renderer must refuse any record
the ingest leg would later reject, so a rendered file always reads back. The vault
codec has the same two legs, `render_note` and `ingest_note`, and the same
obligation: it must never emit a note `ingest_note` would then refuse.
**Decision:** `render_note` refuses up front any record it cannot faithfully
project: an invalid record (every `validate_record` problem, which covers an
unknown scope, an empty id, and a research-artifact-ref carrying a temporal
block); a bare CR anywhere in the record's content (D-12 ported, since a CR would
not survive the codec's line model); a bare LF in a single-line scalar (the id or
the derived title), which would otherwise split the frontmatter scalar and escape
as a raw `FrontmatterError`; and data the `canon:` carrier cannot encode, which
would otherwise escape as a raw `TypeError` from `record.to_json()`. The last two
are folded into `NoteRefused` by `_refuse_unprojectable` before a byte is emitted.
`derive_note_name`, which the mirror calls before render, carries the matching
guard for a non-string or empty id, so the derive leg fails closed as a
`VaultError` rather than crashing the slugifier. The refusal set on render is a
strict superset of what ingest constrains.
**Consequence:** a note that exists on disk always ingests back to a valid record.
The vault fidelity gate (`vault_fidelity.py`) relies on this: a faithful pool
returns zero losses and zero refusals, and any field difference is an undeclared
loss that fails the verdict closed, because the carrier is lossless and there is
nothing legitimate for a field to drop to. An audit of the vault leg found three
constructible records that slipped the earlier guard and crashed the emitter with
the wrong exception type; folding them into `NoteRefused`/`VaultError` restored
the invariant, one regression test per case.

## D-34 — the hub carries a generated marker declaring edits non-durable
**Status:** accepted (this build).
**Context:** MEMORY.md is a file a human will open and may edit, but the mirror
regenerates it wholesale on every run. A human editing the hub directly would lose
that edit on the next mirror, the same hazard D-27 names for a note body, and the
hub has no `canon:` carrier to make the boundary self-evident.
**Decision:** `render_hub` writes a fixed marker line under the H1,
`<!-- canon:vault-hub v1 -- generated; edits here are not durable -->`, on every
render. The marker states in the file itself that the hub is generated and that
edits to it do not survive.
**Consequence:** the non-durable boundary is visible where a human would edit, not
only in the docs. The marker carries a `v1` tag so a future hub format is a
distinct generation, and its presence is part of the byte-identity an unchanged
hub compares against.

## D-35 — the vault is not a registry root-kind
**Status:** accepted (this build).
**Context:** R1's registry binds each managed instruction file to a root-kind
(`home` or `workspace`) and a relative path, and resolves an absolute path at call
time. The vault is also a set of managed files under an injected root, so it was
plausible to add a `ROOT_VAULT` root-kind and model the vault through the same
`Surface` machinery.
**Decision:** the vault is deliberately not a registry root-kind. A `Surface` is a
single file with a region spliced into foreign bytes; the vault is a
whole-directory mirror of files canon owns entirely, with its own containment
(`vault_mirror.is_vault_write_allowed`) and its own plan-then-commit orchestrator.
Adding `ROOT_VAULT` would create a root-kind no `Surface` references, which is
dead code. The vault keeps its own allow-list, parallel to the registry's, rather
than being forced through it.
**Consequence:** the two write paths stay distinct where they genuinely differ: a
region splice into a shared file versus a whole-directory mirror. Neither carries
machinery for the other's model, and the registry catalog stays exactly the set of
region-splice surfaces.

## D-36 — SOUL.md reuses the R0 block grammar with no banner
**Status:** accepted (this build).
**Context:** SOUL.md is the fourth confirmed instruction surface, a personality
file a harness ("hermes") reads. It has no global sibling in the catalog, so under
the authored-split rule (D-21) it renders the full merged set, exactly like
Codex's lone AGENTS.md. The open question was whether SOUL, as a personality
surface, should carry a distinguishing banner or header ahead of its region.
**Decision:** SOUL.md reuses the R0 block-region grammar byte-for-byte, the same
`<!-- canon:begin ... -->` region a CLAUDE.md carries, with no SOUL-specific banner
or header. The production change is a single catalog row; no new rendering code.
A test asserts the rendered region interior is byte-identical to AGENTS.md's for
the same pool, which proves the reuse and the absence of a banner.
**Consequence:** SOUL costs one row and inherits every R0 and R1 guarantee
unchanged. The absent banner is an honest null: canon adds no ornament a surface
does not need. The global SOUL.md path convention is not yet pinned, so only the
workspace surface is cataloged; the global one extends the catalog once that
convention settles, alongside GEMINI.md at both scopes.
