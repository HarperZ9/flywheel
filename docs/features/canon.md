# Canon (native Flywheel lane)

> Feature documentation for the `canon` lane as it lives inside Flywheel. Every
> claim below is bound to a file in the canon repo (`public/canon`) or in
> Flywheel (`public/flywheel`). Canon is an independent, source-available
> project (FSL-1.1-MIT); Flywheel composes it as one lane among several.

## Description

**One sentence.** Canon is the continuity lane: one typed record for a memory
bank and an authored personality that every model and tool draws from, rendered
deterministically into a marked region of each instruction file.

**One paragraph.** Working relationships today scatter across a dozen files with
a dozen shapes (`CLAUDE.md`, `AGENTS.md`, `SOUL.md`, `GEMINI.md`) plus per-tool
memory stores that do not talk to each other. Canon gives all of them one record
envelope with five kinds and two layering scopes, a validator that refuses a
record it cannot vouch for, storage adapters that each declare in advance what a
round-trip loses, a renderer that rewrites only the span between canon's own
markers and preserves every byte outside it, and a set of read-only gates that
check a rendered file back against the record. Inside Flywheel it is registered
as the `continuity` organ lane, probed over MCP like the other lanes, reachable
through the generic lane caller, and shown on the Lanes view with its own
identity card. It imports no engine of its own for memory or block storage:
`mneme` is the memory fact-engine it maps onto, Flywheel's entity store holds its
authored blocks, and both are reached through injected, duck-typed handles.

## Feature list (each item bound to code)

- **One record envelope, five kinds.** `src/canon/schema.py` defines the record
  `{canon_schema, kind, id, scope, data, provenance, temporal}`. The kinds are
  `personality-block`, `episodic-memory`, `synthesized-persona-l3`,
  `adr-decision`, `research-artifact-ref`, with a field-identical
  `to_dict`/`from_dict` round-trip.
- **Two scopes that layer.** `src/canon/layering.py::resolve_blocks(pool, scope)`
  resolves a `workspace` block over a `global` block carrying the same id, keeps
  current entries only, and orders by a clock-free `create_ord` so a rebuild is
  byte-identical. There is no `repo` scope: per-repo instruction files stay
  hand-authored.
- **A validator that refuses.** `src/canon/validator.py::validate_record(rec)`
  returns a list of problems; an empty list means valid. It enforces the semantic
  rules the envelope cannot express in its shape alone (for example, a
  `research-artifact-ref` must not carry a temporal block).
- **A storage seam with declared drops.** `src/canon/backends/base.py` fixes the
  `MemoryBackend` protocol and five capability tokens (`temporal`, `audit-chain`,
  `relations`, `arbitrary-kind`, `foreign-provenance`). `guard_put` refuses a
  record that would silently lose a record-enforceable capability, so a caller
  must `flatten()` to opt into a loss.
- **Four storage adapters.** `backends/sqlite.py` is the zero-drop reference with
  a re-verifiable audit chain; `backends/files.py` is a plain file store;
  `backends/mneme.py` maps the two memory kinds onto an injected mneme store
  handle and keeps temporal history; `backends/flywheel.py` maps every kind onto
  Flywheel's entity store and declares `temporal` dropped. The two engine
  adapters import no engine package.
- **A byte-exact region boundary.** `src/canon/region.py` partitions a managed
  file into `prefix + inner + suffix`; canon rewrites only `inner`, and a file
  with no canon marker is off-limits, and canon skips it and raises no error.
- **A record-to-text codec and its inverse.** `src/canon/textblock.py`
  (`render_region`, `ingest_region`) projects a scope-homogeneous block set into
  the region interior and reads records back; render's refusal set is a strict
  superset of ingest's constraints.
- **A round-trip go/no-go verdict.** `src/canon/fidelity.py::roundtrip_report`
  proves a block set round-trips to canonical form, that render is idempotent,
  that bytes outside the region are preserved across a host encoding matrix, and
  that every dropped field was declared. It returns a verdict for any
  constructible record and never propagates an exception.
- **A surface renderer with a fixed write allow-list.** `src/canon/surface.py`
  and `src/canon/registry.py` render a scope's blocks and write only a changed
  region, and only to four allow-listed surfaces: a global and a workspace file
  for Claude Code, an `AGENTS.md` for Codex, and a workspace `SOUL.md` for Hermes.
  A non-catalog surface or a disallowed path fails closed before any write.
- **A whole-record Obsidian vault mirror.** `src/canon/vault.py`,
  `vault_mirror.py`, `frontmatter.py`, `vault_fidelity.py` mirror the pool into
  one markdown note per record plus a `MEMORY.md` index. The full record rides in
  a single authoritative JSON frontmatter key, so a hand-edited note body never
  changes the record, and no YAML loader runs on ingest.
- **A rendered-surface drift check.** `src/canon/drift.py::surface_drift`
  re-derives each managed surface from the pool and compares only the canon-owned
  interior, keyed by sha256, so an edit to the host's own prose outside the
  markers is never flagged as drift.
- **An injected writing gate.** `src/canon/writing_gate.py` owns the
  per-surface profile register and the `gate_text` pipeline; canon is stdlib-only,
  so the caller wires in the external writing linter and canon imports no linter package.
- **A persona basis check.** `src/canon/persona_thesis.py` measures whether the
  source memories behind a `synthesized-persona-l3` record still resolve and are
  current, framed as falsifiable claims handed to an injected assessor.
- **A reconcile decision and durable gate.** `src/canon/reconcile.py`,
  `reconcile_gate.py`, `reconcile_run.py` classify each surface as a mechanical
  fast-forward or a conflict a human must adjudicate, write the fast-forwards, and
  raise a durable gate for the conflicts. This is a library call, not exposed over
  the lane surface.
- **An aggregate verdict a build keys on.** `src/canon/canon_check.py::canon_check`
  folds four legs (drift, vault round-trip, vault symmetric round-trip, persona
  basis) into one `ok` and an exit code; a leg whose seam is not wired reports
  `None` and does not affect the result.
- **A read-only MCP door.** `src/canon/local_mcp.py` serves six tools over
  zero-dependency stdio JSON-RPC and writes nothing.

## Stepwise usage (running the lane)

Canon runs both as a standalone tool and as a Flywheel lane.

**As a standalone tool.**

1. Install it with `pip install flywheel-canon`. The bare name `canon` on PyPI
   belongs to another project, so the distribution carries the prefix while the
   console script stays `canon`. A source checkout also works.
2. Point canon at your records with `CANON_BLOCKS_DIR`, and at your files with
   `CANON_HOME` and `CANON_WORKSPACE`.
3. Ask canon what it believes, no transport in the way:
   ```bash
   canon blocks    # list the authored block set
   canon check     # aggregate verdict; exits non-zero when a wired leg fails
   ```
4. Serve the record set to a harness over MCP:
   ```bash
   canon mcp
   ```
   These verbs are defined in `src/canon/cli.py` and wired by
   `[project.scripts]` in `pyproject.toml` (`canon = "canon.cli:main"`).
   Reconcile is deliberately absent from the CLI, because it rewrites instruction
   files and raises durable gates.

**As a Flywheel lane.**

1. Start the Flywheel engine. The Lanes view reports canon under install-presence
   status from the ambient poll; "Probe now" runs the real MCP handshake.
2. Install from source when the card offers it, or ahead of time:
   `flywheel install --lanes canon --profile source` (source profile, since the
   package is not distributable). The lane resolves its checkout from
   `public/canon` relative to the workspace root.
3. Probe or call the lane. A probe spawns `canon mcp` and calls `canon.status` or
   `canon.doctor` (the probe vocabulary in `harness/lanes.py`). A tool call goes
   through the gateway route `/api/lane/canon/<tool>`, handled by
   `harness/lane_caller.py::call_lane_tool`, which spawns the lane's MCP server,
   calls the named tool, and returns its JSON verbatim.

## Piecewise reference (each capability)

**Lane registration.** `harness/lanes_registry.py` declares
`LANES["canon"]` as a `pip` lane, command `canon`, args `("mcp",)`, organ
`continuity`, module `canon.cli`, source repo `public/canon`, install name
`flywheel-canon`, version `0.2.0` (read from the registry and from
`pyproject.toml`, which agree). The role text records that the MCP surface is
read-only and that reconcile stays a library call. `package_disabled_reason` is
empty: the distribution is published, so the package install profile is live and
a source checkout is the fallback.

**Lane roster and probe.** `harness/lanes.py` computes each lane's status
(`live`, `stale`, `declared`, `missing`). For canon it selects the runtime,
optionally spawns `canon mcp`, and looks for a `canon.status` or `canon.doctor`
health tool. A missing canon never crashes the roster.

**Generic lane caller.** `harness/lane_caller.py::call_lane_tool` spawns any
registered lane and calls one tool, gated by the governance tier. Canon is not
listed in `LANE_MIN_TIERS`, so it defaults to tier T1 (open), which fits a
read-only door. `list_available_lanes` returns canon with organ `continuity` and
its min tier.

**Desktop identity card.** `desktop/lib/models/lane_identity.dart` holds
`laneIdentities['canon']` with title "Canon", a one-line identity taken from
canon's own README, and the surface label "authored blocks + rendered surfaces".
`desktop/lib/views/lanes_view.dart::LaneCard` renders that card with live health.
Canon has no dedicated deep-view; the desktop reaches it through the card and the
generic caller.

**Expected-set test.** `tests/test_lanes.py::test_registry_covers_the_expected_lanes`
asserts that `set(LANES)` includes `canon`, so removing the lane fails the suite.

**The six MCP tools** (`src/canon/local_mcp.py`), all read-only:

- `canon.status` - liveness and identity (name, version, protocol). Reads
  nothing. This is the fast health probe.
- `canon.doctor` - readiness: the block directory, how many records loaded, any
  that failed, the four writable surfaces, and whether the drift roots are set.
  Reads the block directory only. `ok` here is readiness, so it can read false
  while `canon.status` stays true.
- `canon.blocks` - the authored record set (id, kind, scope, title; `full=true`
  for whole records).
- `canon.render` - the region interior for a scope, the same text canon would
  splice into that scope's instruction files. Writes no file.
- `canon.validate` - validate one supplied record, or the whole block directory.
- `canon.check` - the aggregate verdict, naming which legs ran and which are
  unwired, so a two-leg pass is not read as a whole-repo pass.

**The CLI verbs** (`src/canon/cli.py`): `canon mcp`, `canon check`, `canon
blocks`. `canon check` and the `canon.check` tool call the same `_check`, so a
build gate and a harness question cannot disagree.

## Composition tutorial (the seam, what it consumes and emits)

**Which lane/seam it is.** Canon is the `continuity` organ in Flywheel's lane
layer. Structurally it is a standard MCP lane: a registry entry, an
install/probe/roster path, a desktop card, and a governance-gated generic caller.
Flywheel keeps two other lane shapes that canon does not use. Relay alone takes
the bundled/frozen gateway shape. Chorus runs as a bridged satellite, driven by
`harness/chorus_bridge.py`, exposed at `/api/discourse`, and rendered by a
dedicated `DiscourseView`. Canon uses the fuller lane pattern and is reached
through the shared lane machinery.

**What it consumes from peers.**

- The Flywheel entity store. `backends/flywheel.py` binds to an injected handle
  matching `put_entity` / `get_entity` / `query_all_entities`. Flywheel's
  `harness/store.py` exposes exactly that surface, so canon's authored blocks and
  non-temporal kinds can live in Flywheel's store, namespaced `project=canon:<scope>`.
  Canon imports no Flywheel package; the handle is duck-typed and proved against a
  fake that mirrors the store.
- The mneme memory engine. `backends/mneme.py` maps `episodic-memory` and
  `synthesized-persona-l3` onto an injected mneme store handle, keeping temporal
  history (a supersede is recorded between two present rows). mneme is a peer lane
  in the same registry (organ `memory`).
- An external verification assessor for the persona leg, and an external writing
  linter for the writing gate. The caller injects both, and canon imports neither.

**What it emits for peers.**

- Rendered instruction-file region text (`canon.render`), ready for a harness to
  splice, or written directly by the reconcile library call.
- The authored block set (`canon.blocks`) and per-record validation
  (`canon.validate`).
- An aggregate pass/fail verdict with an exit code (`canon.check`,
  `canon_check.py`), shaped so a build already keying on `drift_exit_code` or
  `reconcile_exit_code` picks it up with no bespoke wiring.
- Readiness and liveness signals (`canon.doctor`, `canon.status`) that the lane
  probe and the desktop card read.

**Worked example: canon plus mneme, surfaced through Flywheel.**

1. A session writes an episodic memory. It lands in mneme (organ `memory`), which
   owns the ordinal clock and the supersession history.
2. Canon's `MnemeBackend`, holding an injected mneme store handle, reads those
   memory records back as canon records, normalizing mneme's provenance to canon's
   envelope (a declared `foreign-provenance` drop).
3. The operator's authored personality blocks live in Flywheel's entity store via
   `FlywheelBackend`. `layering.resolve_blocks` resolves the effective set for a
   scope: workspace over global, current only, clock-free order.
4. `canon.render` returns the region text for that scope. A harness splices it
   into the marked region of its instruction file, or the reconcile library call
   writes the four allow-listed surfaces directly.
5. Later, `canon.check` (through the gateway at `/api/lane/canon/check`, or the
   CLI in a build) folds drift, vault, and persona legs into one verdict. The
   persona leg uses the injected assessor to ask whether the source memories
   behind a synthesized persona still resolve. If a memory was superseded in
   mneme, the persona leg reports DRIFT and the aggregate fails closed.

In this path canon is the seam that turns peer state (mneme's memories,
Flywheel's blocks) into the one record each surface reads, and turns a rendered
surface back into a checkable verdict. It adds the shared envelope, the per-scope
layering, and the deterministic renderer; it does not replace the memory engine or
the block store.

## Integration status and honest nulls

Canon is a native lane, wired across three of the four surfaces the integration
checklist names, with the fourth correctly absent:

1. **lanes_registry entry** - present (`harness/lanes_registry.py`, organ
   `continuity`).
2. **desktop app card** - present (`desktop/lib/models/lane_identity.dart`,
   rendered by `LaneCard`).
3. **expected-set test** - present
   (`tests/test_lanes.py::test_registry_covers_the_expected_lanes`).
4. **payload manifest** - absent by design. The bundled-lane descriptor under
   `packaging/bundled-lanes/` exists only for relay (the one lane frozen into the
   gateway executable), and `scripts/check_bundled_lane_descriptors.py` supports
   lane `relay` alone. Canon is a source-checkout pip lane, so it has no such
   manifest and needs none.

Remaining honest nulls, none of which are lane-wiring defects:

- Canon is absent from `LANE_MIN_TIERS`, so it takes the T1 default tier with no
  explicit entry. This fits a read-only door but is implicit.
- No dedicated desktop deep-view. Chorus has a `DiscourseView` destination; canon
  is reached through the lane card and the generic `/api/lane` caller only.
- The reconcile write-path is intentionally not exposed over MCP or the lane
  caller. The lane surface is read-only, and rewriting instruction files stays a
  library call with a human gate behind it.

## Reference layout

- Lane wiring in Flywheel: `harness/lanes_registry.py`, `harness/lanes.py`,
  `harness/lane_caller.py`, `harness/gateway.py` (route `/api/lane/`),
  `desktop/lib/models/lane_identity.dart`, `desktop/lib/views/lanes_view.dart`,
  `tests/test_lanes.py`.
- Canon internals: `src/canon/schema.py`, `validator.py`, `layering.py`,
  `backends/`, `region.py`, `textblock.py`, `fidelity.py`, `surface.py`,
  `registry.py`, `frontmatter.py`, `vault*.py`, `drift.py`, `writing_gate.py`,
  `persona_thesis.py`, `reconcile*.py`, `canon_check.py`, `blocks.py`,
  `local_mcp.py`, `cli.py`. Design records in `project-docs/` (F0, F1, R0, R1,
  R2, V2, V3, V4, MCP decisions).