# R1 — decisions of record

The decisions that frame the surface renderer, continuing the log in
F0-DECISIONS.md, F1-DECISIONS.md, and R0-DECISIONS.md and recorded in the same
shape the `adr-decision` kind captures. Each is accepted unless marked otherwise.

R1 is the first band that reaches a live host file and rewrites it. It ships two
layers over the R0 legs:

- `src/canon/surface.py` — the render composition. `apply_surface` resolves the
  pool to the effective block set for a scope (F0 layering), projects that set
  onto the scope, renders it (R0 textblock), and splices it into a host file (R0
  region) with every outside byte preserved.
- `src/canon/registry.py` — the write-surface allow-list and the orchestrator.
  A fixed catalog names the managed files; `write_surface` renders one; and
  `write_surfaces` renders a harness's whole set by the authored-split rule.

## D-17 — R1 projects the resolved set onto the surface scope before rendering
**Status:** accepted (this build, 2026-08-28).
**Context:** `resolve_blocks(pool, "workspace")` returns the effective set for a
workspace render, and that set is scope-heterogeneous: a global block that no
workspace block overrides survives into it still tagged `global`. `render_region`
is scope-homogeneous by contract; it refuses a set whose records do not all carry
the region's scope. So the resolved set cannot be handed to the renderer as-is.
**Decision:** `render_surface` re-scopes every resolved record to the target
scope with `dataclasses.replace(rec, scope=scope)` before rendering. A global
block that survives into the workspace surface is emitted as a workspace-region
block. The text leg drops provenance anyway, so on ingest the block's native id
rebinds to the region's scope and the round-trip is clean.
**Consequence:** "layering at render time" is literal. The region a harness reads
is the resolved view projected onto one scope, never the raw per-scope pool, and
the renderer's homogeneity contract holds without a special case.

## D-18 — apply_surface refuses an off-limits or mis-scoped host before writing
**Status:** accepted (this build).
**Context:** A host file may carry no canon region (it never opted in), or a
region whose declared scope does not match the render's scope. Splicing a
workspace render into a `global`-marked region would write blocks that ingest
back mis-scoped, corrupting the very round-trip R0 certifies.
**Decision:** `apply_surface` extracts the region first and raises `SurfaceError`
on either fault before it renders or splices: no region present, or a region
scope that is not the target scope. The refusal is loud and precedes any byte
change.
**Consequence:** a mis-scoped write can never reach a file. Off-limits and
scope-mismatch are the two distinct front-door refusals of the write path, and
both fail closed.

## D-19 — the write-surface allow-list is path-clean; roots are injected
**Status:** accepted (this build).
**Context:** canon is a public repository. The render-scope allow-list is a fixed
set of the operator's real files, and the global engineering standard forbids a
local path on a product surface. A catalog that hard-coded `~/.claude/CLAUDE.md`
or a workspace absolute path would leak the operator's layout into public source.
**Decision:** the catalog stores only a harness, a scope, a root-kind
(`home` or `workspace`), and a path relative to that root. The absolute roots are
injected at call time through the `home` and `workspace` arguments and never
stored. Public source carries only generic filename conventions
(`.claude/CLAUDE.md`, `CLAUDE.md`, `AGENTS.md`). The confirmed surfaces are the
two CLAUDE.md files and the workspace AGENTS.md; GEMINI.md and SOUL.md at both
scopes are confirmed surfaces whose global-path conventions are not yet pinned,
and they extend the catalog once settled.
**Consequence:** the allow-list is a function of injected roots, the public repo
stays path-clean, and the same catalog serves any operator's layout.

## D-20 — the allow-list guard is a lexical path membership
**Status:** accepted (this build).
**Context:** `is_write_allowed` decides whether a path is one of the catalog
surfaces. It could resolve symlinks with `os.path.realpath`, which touches the
filesystem, or compare paths lexically, which does not.
**Decision:** the guard normalizes with `normpath` and `normcase` and tests set
membership against the catalog resolved under the injected roots. A traversal
escape collapses under `normpath` and fails to match; a case-insensitive
filesystem folds case. The guard is pure and injectable, so it is provable
without a filesystem. A symlink planted at an allow-listed path is out of scope:
canon only ever computes paths from its own fixed catalog, and a compromised home
directory is a larger failure than canon writing through it.
**Consequence:** the guard is testable with fake roots and no disk, and it
refuses every path that is not exactly a catalog surface. The threat it defends
is "canon computes a path outside its list", not "the operator's tree is hostile".

## D-21 — a two-file harness's workspace file carries only its authored blocks
**Status:** accepted (this build; operator ruling, 2026-08-28).
**Context:** Claude Code loads both `~/.claude/CLAUDE.md` and the workspace
`CLAUDE.md` into context. canon writes both. The question is what the workspace
file's region holds: the full merged set (globals overlaid by workspace) or only
the workspace-authored blocks. The global file always carries the original
globals, since it is the shared global surface. So for an overridden id, the
global block is present in the global file no matter what, and merged versus
authored-split have identical override behavior. They differ only in duplication:
a merged workspace file repeats every non-overridden global that the harness
already reads from the global file.
**Decision:** the workspace file is authored-only when the same harness also owns
a global surface in the catalog, and the full merged set when it does not. The
rule derives from the catalog, so no per-harness consumption flag is needed:
Claude Code's workspace CLAUDE.md is authored-only (a global sibling exists),
Codex's lone AGENTS.md is merged (none does), so that single file stays
self-sufficient. The operator ruled for authored-split, on the record that no
consumer is handed a workspace file alone that would need it merged.
**Consequence:** a two-file harness sees each global once, not twice, with the
override behavior unchanged. A single-file surface keeps a complete standalone
context. The choice is reversible at one function, `pool_for` (public since V2,
so the drift check and writing gate resolve the same authored-split).

## D-22 — off-limits is a reported skip; the batch fails closed before any write
**Status:** accepted (this build). The all-or-nothing guarantee was hardened
after a pre-publish adversarial check found the first cut planned only the static
faults up front and left the mis-scope refusal inside the write loop, so two
valid surfaces committed before a third mis-scoped one raised.
**Context:** On a first run the operator's real files carry no canon region.
`write_surfaces` renders the whole catalog. A host that has not opted in must stay
untouched, and a single bad surface must not commit some files before it aborts
the batch on a later one.
**Decision:** the batch plans every surface before it commits any write. The plan
pass checks each surface for catalog membership and an allow-listed path, reads
its host, and computes its render through `apply_surface`. That is where a host
with no region becomes a recorded `off-limits` skip and a host whose region is
mis-scoped raises. Only once the whole set plans clean does the commit pass write
the changed regions; an unchanged region is recorded `unchanged` and left alone.
Installing a region into a virgin file is a separate, deliberate act, deferred
past R1.
**Consequence:** a file that did not opt in stays untouched, and a mis-scoped host
at any position aborts the plan before the first byte is written, so the batch is
all-or-nothing. Each surface's outcome is reported back to the caller. The
renderer is safe to point at the real allow-list before every file has a region.
The guarantee covers canon's own refusals: catalog membership, an allow-listed
path, an off-limits host, and a mis-scoped region all resolve in the plan pass,
before any write. It does not extend to a filesystem fault during the commit
pass. Should a `write_text` fail on one file after earlier files have written,
those writes stand and the error propagates unrolled. Disk-level multi-file
atomicity is out of R1's scope, and a later band owns it if a real deployment
needs it.
