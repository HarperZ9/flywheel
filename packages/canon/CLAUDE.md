# CLAUDE.md — canon

> Model-facing, self-contained. This repo is cloned and operated on its own; it
> does not inherit a workspace-level canon. Anything from the workspace or
> global standards this repo needs is copied here in this repo's own register.

## What canon is
A provider-neutral memory-bank and personality container. One canonical record
envelope that every harness (Claude Code, Claude CLI, ChatGPT, Codex, web
surfaces) and every store draws from and writes to. It unifies the scattered
instruction+personality files (CLAUDE.md / AGENTS.md / SOUL.md / GEMINI.md) and
session memories under a single typed record, then renders each surface's file
from that record deterministically.

canon is an assembly over existing engines, not a rewrite: mneme is the memory
fact-engine of record, flywheel's store holds authored blocks, relay is the
cross-provider transport. canon adds the one envelope they aim at, the per-scope
layering that resolves the block set, and the deterministic renderer.

## Build state
F0 ships the record of record and nothing that writes a file:
- `src/canon/schema.py` — the canonical envelope, five kinds, provenance,
  temporal block, `to_dict`/`from_dict` (field-identical round-trip).
- `src/canon/validator.py` — `validate_record(rec) -> list[str]`, semantic rules.
- `src/canon/layering.py` — `resolve_blocks(pool, scope)`, per-scope override.
- `project-docs/` — the F0 specs: schema, layering, section-ownership,
  declared-drops (cited to real code), decisions.

F1 adds the storage seam and nothing that renders a file:
- `src/canon/backends/base.py` — the `MemoryBackend` Protocol, the five
  capability tokens, `record_key`/`split_key`, and `guard_put` (refuse on kind
  mismatch or a record-enforceable dropped capability).
- `src/canon/backends/{files,sqlite,mneme,flywheel}.py` — the four adapters.
  sqlite is the zero-drop reference with a re-verifiable audit chain; mneme and
  flywheel map onto an injected, duck-typed store handle and import no engine.
- `project-docs/F1-BACKENDS.md`, `F1-DECISIONS.md` (D-7 encryption-at-rest null,
  D-8 refuse-not-flatten, D-9 injected handle, D-10 mneme's temporal boundary as a
  loud put-time refusal, D-11 the fake mirrors mneme's INSERT OR REPLACE); Drop 4
  and the Status note in `F0-DECLARED-DROPS.md`.

R0 is the block round-trip go/no-go gate, the first band that turns a record into
bytes and reads it back:
- `src/canon/region.py` — the byte boundary. `extract_region`/`splice_region`
  partition a managed file into `prefix + inner + suffix` with a byte-exact
  identity; only `inner` is canon's to rewrite, and a file with no marker is
  off-limits, not an error.
- `src/canon/textblock.py` — the record-to-text layer. `render_region` projects a
  scope-homogeneous block set into the region interior and refuses any record it
  cannot represent; `ingest_region` reads records back and speaks the same
  grammar. render's refusal set is a strict superset of ingest's constraints.
- `src/canon/fidelity.py` — `roundtrip_report`, the go/no-go verdict: round-trip
  to canonical form, render idempotence, outside-byte preservation across the
  host encoding matrix, and a structural drop ledger that fails closed on any
  undeclared loss. The gate returns a verdict for any constructible record and
  never propagates an exception.
- `project-docs/R0-DECISIONS.md` — D-12 one-LF line model, D-13 render-superset
  invariant, D-14 total gate, D-15 diff-against-raw ledger, D-16 the audit-driven
  refusal of constructible-but-malformed records, and the recorded audit (six
  findings checked, five confirmed and folded in TDD-style, one refuted).

R1 is the surface renderer, the first band that reaches a live host file and
rewrites it:
- `src/canon/surface.py` — the render composition. `render_surface` resolves the
  pool for a scope, projects the effective (mixed-origin) set onto that scope,
  and renders the region interior; `apply_surface` splices it into a host file
  and refuses before writing if the host has no canon region (off-limits) or its
  region's declared scope does not match the target scope.
- `src/canon/registry.py` — the write-surface allow-list and the orchestrator. A
  fixed, path-clean catalog binds each `(harness, scope)` to a root-kind and a
  relative path, with the absolute roots injected at call time. `write_surface`
  renders one surface through injected IO and writes only a changed region;
  `write_surfaces` renders a harness's whole set by the authored-split rule and
  fails closed on a non-catalog surface or a disallowed path before any write.
- `project-docs/R1-DECISIONS.md` — D-17 project-before-render, D-18 the
  off-limits and mis-scope refusals, D-19 the path-clean injected-root catalog,
  D-20 the lexical allow-list guard, D-21 the authored-split rule for a two-file
  harness (operator ruling), D-22 off-limits as a reported skip with a
  fail-closed batch.

R2 is the vault band. R1 splices a scope's blocks into a shared instruction file;
R2 mirrors the whole pool into an Obsidian vault of one note per record, plus a
MEMORY.md index, and adds the SOUL.md instruction surface:
- `src/canon/frontmatter.py` — a constrained frontmatter codec. It emits a fixed
  set of single-quoted scalars and one authoritative `canon:` key carrying
  `record.to_json()` verbatim, and it reads only that key back. No YAML loader
  runs on ingest, so the `!!python/object` trap is inert.
- `src/canon/vault.py` — the one-record note codec. `render_note` projects a
  record to a whole markdown file (frontmatter carrier, heading, per-kind body,
  `## canon links` trailer) and refuses any record it cannot faithfully project;
  `ingest_note` reconstructs the record from the carrier JSON alone, so a
  hand-edited body never changes the record. Identity, not content, names the
  file: the path digests the `(scope, id)` key, so a hostile id cannot forge one.
- `src/canon/vault_mirror.py` — the whole-vault orchestrator. `plan_vault`
  renders the pool into contained note paths plus the hub, plans the whole set
  against what is on disk, and commits only once nothing refuses. A file that is
  not a canon note is off-limits and never clobbered; a stale note is reported as
  an orphan and never deleted.
- `src/canon/vault_fidelity.py` — the vault round-trip verdict. The note carrier
  is lossless, so its declared-drop ledger is empty and any field difference is
  an undeclared loss that fails the verdict closed.
- `src/canon/registry.py` — extended with the SOUL.md surface (a fourth catalog
  row, harness `hermes`), a lone workspace surface that renders the merged set
  through the R1 authored-split renderer unchanged, with no banner.
- `project-docs/R2-DECISIONS.md` — D-23 the constrained codec (no YAML loader),
  D-24 the whole-file note carried by one JSON line, D-25 links from relations not
  body prose, D-26 the hub reuses the surface sort key, D-27 the authoritative
  carrier and one-way body, D-28 the fixed frontmatter key order, D-29
  identity-not-content names the file, D-30 the off-limits and spoof refusals,
  D-31 the lexical vault containment, D-32 orphan reported never deleted, D-33 the
  render-superset invariant carried to the vault leg, D-34 the non-durable hub
  marker, D-35 the vault is not a registry root-kind, D-36 SOUL reuses the R0
  grammar with no banner.

V2 is the first verify band over the render legs. It writes nothing; it ships two
read-only gates a build keys on:
- `src/canon/drift.py` — the rendered-surface drift check. `surface_drift`
  re-derives a managed surface from the pool (R1's clock-free render composition,
  so byte-stable) and compares the derived region interior to what is on disk, a
  sha256-keyed verdict per surface (match, drift, off-limits, refused, missing).
  It scores canon-owned bytes (the interior between the markers), so an edit to
  the host's own prose outside the markers is never drift, and it mirrors the
  batch writer `write_surfaces` through `pool_for`, so a merged workspace file is
  flagged. `drift_report` maps the catalog and `drift_exit_code` gates a build.
- `src/canon/writing_gate.py` — the injected STE seam. canon is stdlib-only and
  the linter (`check_writing.py`) lives outside this repo, so the caller wires
  the checker; canon owns the `WritingChecker` shape, the per-surface profile
  register, and the `gate_text` pipeline. A file passes iff the checker reports
  an empty `hard` list, the exact signal `check_writing --gate` keys on. The
  register binds each surface to a profile (instruction files `readme`, SOUL.md
  `chat`); the strict `procedure` profile is unused here (an honest null).
  `forum_clarify_pre_cleaner` adapts a caller-wired Forum `forum.prose.clarify`
  call into the optional pre-cleaner. It accepts `forum.prose-clarification/v1`
  and the deprecated `forum.prose-humanization/v1` while Forum keeps the
  humanize alias, and raises on any other schema.
- `project-docs/V2-DECISIONS.md` — D-37 the profile-per-surface register, D-38
  the injected gate seam, D-39 the empty-hard-list pass signal, D-40 drift scores
  the interior and mirrors the batch writer (and why `pool_for` went public),
  D-41 the sha256-keyed verdict with the catalog as manifest, D-42 both gates
  total and read-only.

V3 is the second verify band. It writes nothing; it ships one read-only adapter
that hands a persona's basis to the external crucible engine for a witnessed
drift verdict:
- `src/canon/persona_thesis.py` — the persona-as-crucible-thesis drift adapter. A
  `synthesized-persona-l3` record is a synthesis claim (this text faithfully
  summarizes these source memories), and canon has no model to re-run that
  synthesis, so it measures drift structurally from the pool on two clock-free
  axes: basis-present (every source id still resolves to a record) and
  basis-current (no source id is superseded by a newer record). `persona_thesis`
  frames the two axes as falsifiable claims carrying model-free measurements,
  `thesis_payload` serializes the thesis for the injected assessor, and
  `assess_persona` runs the assessor and folds crucible's counts into a headline
  `DriftVerdict` (any drift reads DRIFT, else any unverifiable reads UNVERIFIABLE,
  else MATCH), read by direct index so a malformed assessment is a wiring fault,
  not a silent MATCH. The assessor is an injected seam, so canon imports no
  engine; the basis is a set, so a repeated source id is one source.
- `project-docs/V3-DECISIONS.md` — D-43 persona drift measured from the basis
  model-free (never re-synthesized), D-44 the injected crucible-assessor seam,
  D-45 the strict basis tolerance encodes integer-zero as 0.5, D-46 a proven
  drift outranks an honest null (counts read fail-closed), D-47 an empty basis is
  UNVERIFIABLE not MATCH, D-48 the surface-drift-as-thesis bridge scoped out
  (honest null), D-49 the basis is a set (duplicate source ids deduped), D-50 the
  documented caller-wiring corrected and verified out-of-suite, plus the recorded
  audit.

V4 is the reconcile band. It is the first band that decides, per surface, whether
a byte-drift is a safe mechanical fast-forward or a conflict a human must
adjudicate, then acts: it writes the fast-forwards and raises a durable human gate
for the conflicts. The fast-forward-vs-conflict call consumes the external
crucible persona verdict from V3, not a self-report:
- `src/canon/reconcile_gate.py` — the pure gate/deadline kernel, clock-free and
  IO-free. `ConflictGatePolicy` configures how a conflict gate lapses;
  `resolve_with_deadline` folds a frozen absolute deadline against an injected
  clock (now == deadline expires; the default on_expiry is reject, so a gate no one
  answered lapses closed); `reconcile_action` maps a resolution to the one commit
  bit and raises on an out-of-vocabulary resolution.
- `src/canon/reconcile.py` — the pure per-surface decision. `persona_fold` lifts
  V3's single-persona fold to a set (any proven drift outranks any honest null);
  `classify` is the total lattice over (drift verdict, persona fold) and fails
  closed to REFUSED on any out-of-vocabulary input; `classify_surface` scores the
  drift against the personality-block subset (which keeps `surface_drift` total),
  folds the crucible persona verdict in only on a byte-drift (the sole fork where
  it changes the write decision), and overlays any gate on file, reading a durable
  deadline frozen at raise time. Read-only.
- `src/canon/reconcile_run.py` — the two-phase orchestrator. `reconcile`
  classifies every surface (reads only), then commits: it batch-writes the
  fast-forwards and approved overrides through the exact writer the drift check
  mirrors, raises a fresh durable gate for each surface that still needs a human,
  and witnesses the run once (even all-clean). `run_witness_payload` is the
  path-clean receipt (a pool_digest binding the inputs, per-surface region hashes
  binding each decision to content, no absolute host path emitted);
  `reconcile_exit_code` gates a build.
- `project-docs/V4-DECISIONS.md` — D-51 drift against on-disk (no recorded base),
  D-52 the four catalog surfaces as target (vault reconcile scoped out), D-53
  scope-coarse persona-to-surface coupling, D-54 the classification lattice and
  which classifications gate, D-55 an unverifiable basis holds like a conflict,
  D-56 classify fails closed to REFUSED, D-57 the assessor fires only on a
  byte-drift, D-58 the block filter (and the disclosed latent V2 mixed-pool
  defect), D-59 the pure gate/deadline kernel, D-60 the deadline and on_expiry
  frozen at raise (the read side takes no policy; a materialized reply missing a
  frozen field is a loud wiring fault), D-61 the path-clean gate identity, D-62
  two-phase then witness once, D-63 per-surface independence, D-64 the path-clean
  pool-bound run witness, D-65 the commit writes through the writer the drift
  check mirrors, D-66 the commit is not transactional across seams (disclosed
  boundary), D-67 the classify/raise gate double-read is a benign staleness window
  (disclosed boundary), plus the recorded audit (0 critical, 1 warning folded, 2
  info disclosed).

MCP is the door band. Every band before it faced inward, so a harness holding
the files canon writes had no way to ask canon what it believes. This band adds
that door and still writes nothing:
- `src/canon/blocks.py` loads an authored block set from a directory of JSON
  records. It reads `*.json` only, and a file that does not parse or does not
  validate comes back as a problem string rather than being skipped, so a pool
  never quietly drops the record someone just wrote.
- `src/canon/local_mcp.py` serves six read-only tools over zero-dependency stdio
  JSON-RPC. `canon.status` is liveness and stays true whatever the directory
  holds; `canon.doctor` is readiness and reads false when the block directory is
  missing or holds a file that will not load. `canon.blocks`, `canon.render`,
  `canon.validate` and `canon.check` are the rest. Those first two names are the
  ones a lane probe calls, so a rename leaves the lane unprobed. The drift roots
  come from `CANON_HOME` and `CANON_WORKSPACE`, never from a tool argument, so
  the door is not a general file-read surface with a schema on top.
- `src/canon/cli.py` and `[project.scripts]` give `canon mcp`, `canon check` and
  `canon blocks`. Reconcile is absent on purpose: it rewrites instruction files
  and raises durable gates.
- `src/canon/_version.py` holds the one version number. `canon.__version__`,
  `canon --version` and the serverInfo of both MCP servers read it, and
  `tests/test_local_mcp.py` holds it equal to pyproject.toml.
  `src/canon/mcp_entry.py` parses argv for `python -m canon.local_mcp` and
  `python -m canon.context_mcp`, so `--help` and `--version` exit without
  serving and an unknown argument exits 2.
- `project-docs/MCP-DECISIONS.md` records D-68 the door reads and never writes
  (with the byte-digest control behind that claim), D-69 the probe vocabulary,
  D-70 the status/doctor split and how doctor can be false, D-71 the roots come
  from the environment, D-72 the check folds the block load so a vacuous pass
  fails, D-73 a bad file is reported not skipped, D-74 three read verbs, D-75 no
  `blocks/` directory in this repository (an honest null).

W1 is the workspace band: per-project state that survives a change of model or
tool. It keeps the record envelope unchanged and binds records to a project one
level up, in the stored row:
- `src/canon/workspace/identity.py` derives a `prj_` id from a `canon.project`
  git config name, else the normalized remote URL (credentials, a default port,
  scheme and `.git` dropped, host lowercased, path case kept), else a nonce in
  the git directory (`gitconfig.py` reads the config and keeps the nonce), else
  the root path. A `.git` in the home directory or a filesystem root claims
  only itself. The store keeps a digest per checkout root and announces a
  checkout new to a project.
- `src/canon/workspace/rows.py` is the `canon.project-row/v1` row that wraps an
  unchanged record with its `project_id`, `state` (accepted or proposed),
  `origin` and `promoted_from`.
- `src/canon/workspace/store.py` is one store per project under a root
  (`~/.canon/store`, `CANON_STORE`, `--store`). A read refuses a whole file when
  any row names another project; writes are sorted, atomic and under the run
  lock. `put` refuses a global record.
- `src/canon/workspace/pool.py` assembles what a render may read: global rows,
  this project's accepted rows, and named projects' rows, each tagged.
  `src/canon/workspace/moves.py` holds `promote` and `adopt`, the only two
  cross-boundary moves, both logged with a reason.
- `src/canon/schema.py` adds three workspace-state kinds (`workspace-focus`,
  `work-item`, `environment-constraint`) stamped `canon.workspace-state/v1` via
  `schema_tag_for(kind)`; `KINDS` stays the five v1 kinds and `ALL_KINDS` is
  what the validator admits. `src/canon/validator_workspace.py` holds their rules
  and the optional `rejected_alternatives` list on `adr-decision`.
  `src/canon/workspace/authoring.py` builds them for the CLI. The pin type moved
  to `src/canon/versions_pin.py` (re-exported by `versions.py`).
- `src/canon/cli_workspace*.py` add `canon workspace
  id|list|promote|adopt|focus|task|set-status|decide|constraint`.
- `src/canon/workspace/targets.py` is the target catalog with sourced size
  budgets; `brief_items.py` picks and orders what a brief shows (excluded
  records are named with the rule); `brief.py` fits the brief as a strict
  prefix of the priority order with a `Left out` report and a
  `canon.handoff-receipt/v1` receipt; `switch.py` renders the target's
  workspace region with the brief as the reserved block
  `canon-workspace-brief`, through the allow-list, refusing a file Codex would
  truncate; `switch_host.py` holds the host checks (links, the region, line
  endings, the Codex override and budget chain); `hosts.py` is the text of a
  file `--create` makes. `src/canon/cli_handoff.py` adds `canon handoff` and
  `canon switch`; `src/canon/cli_files.py` is their file IO with named
  failures.
- `src/canon/workspace/scrub.py` redacts secret-shaped values by the rules in
  `scrub_rules.py` (value shapes in `scrub_shape.py`) and counts hits (no
  values, no digests); importers scrub each source string whole before
  extraction; the store refuses a record that still
  matches (`SecretRefused`), and `brief.refuse_secrets` guards the brief and the
  switch region. `extract.py` holds the fixed text rules; `import_source.py` the
  JSONL reader; `import_project.py` the identity-based project check;
  `import_common.py` the declared-loss `Ledger` and the `Collector` (with
  turn rollback); `import_claude_chain.py` the live branch and the task list; `import_claude.py` and `import_codex.py` the two importers with
  their `DECLARED_DROPS`; `import_write.py` turns candidates into scrubbed,
  proposed rows with an origin and a `canon.import-report/v1` report.
  `src/canon/cli_import.py` adds `canon workspace import|accept|reject`.
- `src/canon/registry.py` carries seven surfaces: W1 adds `GEMINI.md`,
  `.github/copilot-instructions.md` and `.cursor/rules/canon.mdc`, each a lone
  workspace surface; `write_surfaces` reports a missing file as `missing`.
  `src/canon/textblock_scope.py` is the v1 grammar's optional `applies`
  attribute and its generated `Applies to:` line (`textblock-grammar` pin v1).
  `src/canon/workspace/target_fidelity.py` declares per-target downgrades
  (`activation.glob`, `text.at-import`) and `target_roundtrip` fails on an
  undeclared one; `hosts.py` checks the Cursor frontmatter.
- `src/canon/workspace/ledger.py` is the render ledger (`renders.json`,
  `canon.render-ledger/v1`): what `switch` last wrote per checkout and surface,
  the recent renders per surface, the block owners and a render number.
  `backflow.py` compares the region on disk with it and turns block edits into
  proposals; `backflow_brief.py` maps edited brief lines (goal, work status,
  new work, new constraint, removed work) and keeps anything else as a memory
  proposal. `switch` refuses with `edits_pending` while any such proposal is
  undecided; `canon workspace pull --from <target>` runs the read alone.
  Fixtures in `tests/fixtures/transcripts/` use placeholders; tests plant
  canaries built at run time.
- `docs/switching-models.md` is the user-facing walkthrough with run-it-now
  commands and the limits; keep it in step with the commands.
- `project-docs/W1-WORKSPACE.md` is the spec (identity, collisions, renames,
  store layout, isolation); `project-docs/W1-DECISIONS.md` records D-101 the
  binding lives in the row, D-102 remote-keyed identity that splits on doubt,
  D-103 the ceiling directories, D-104 isolation checked on read, D-105 named
  foreign reads never merge by id, D-106 global by promotion only, D-107 the
  store outside the repository, D-108 adoption answers a rename, D-109 the
  workspace-state tag, D-110 rejected alternatives as an additive field, D-111
  the adapters keep the five v1 kinds, D-112 the pin type split, D-113 the
  strict-prefix brief with a report, D-114 the brief as a reserved region
  block, D-115 sourced budgets and the Codex refusal, D-116 `--create` for a
  missing file only, D-117 importers propose and a person accepts, D-118
  declared loss at the import boundary, D-119 scrub then check at store and
  render, D-120 the source must name this project, D-121 public-format fixtures
  with run-time canaries, D-122 scope in the sentinel plus a visible line,
  D-123 exact paths for the three new surfaces, D-124 declared per-target
  downgrades held by a verdict, D-125 a missing file is reported, D-126 the
  render ledger, D-127 in-place edits become proposals and switch waits,
  D-128 the review findings folded in (tagged removals, the anchor ceiling,
  re-read before write, four-character minimum for name-based secret rules),
  D-129 promote refuses a global id clash and accept refuses a stale base,
  D-130 a non-default port splits, a nonce keys a repository with no remote,
  and a new checkout is announced, D-131 the scrubber covers the everyday
  forms, scrubs before extraction, and anchors placeholders, D-132 the
  importers read what the host wrote as the host's and compare projects by
  identity, D-133 back-flow reads a checkout against its own render and keeps
  every edit, D-134 switch checks the host as it is (links, override, budget
  chain, line endings) and the brief is measured as it lands, D-135 the
  project check resolves a working directory to its checkout first, D-136 a
  value after a secret-named key is judged by its shape, D-137 a markdown
  brief says on the command line what it left out, D-138 a URL user part is
  redacted by its shape, not by a length floor, D-139 the Codex budget is
  read where Codex reads its config (`CODEX_HOME`, else `~/.codex`), D-140
  the scrubber runs in time linear in its input, D-141 a value looks random by
  its runs, not by its character classes, D-142 the last secret word decides a
  name, and a password keeps its suffix, D-143 a URL query parameter ends at
  the next `&` or `#`, D-144 a header value is judged by its shape and read on
  its own line, D-145 a Codex URL that names this checkout's own remote defers
  to the directory under `--remote`.

C1 is the context-ownership band: the shared context store can remove what it
holds and the capture hook can store answers on request.
- `src/canon/context_audit.py` reconciles records with the op-aware audit chain
  (`put` and `purge` rows; the latest row per key decides) and holds the salted
  put commitment; `src/canon/context_migrate.py` holds the identity marker
  (version 1 or 2) and the `ALTER TABLE` migration at the first write.
  `SqliteBackend.verify_chain` walks the same op-aware chain, and
  `SqliteBackend.put` still writes plain puts, so blocks databases stay
  readable by 0.3.0. `context_selection.py` resolves a selection and applies
  `keep_responses` to the bulk selectors; `context_access.py` reports from the
  POSIX mode bits whether the database file is shared with other accounts, and
  `not_checked` on Windows. `context_redact.py` redacts every ingest, and
  `ContextStore.ingest` refuses an answer whose prompt is not live
  (`ContextPairingError`) inside the write.
- `src/canon/context_purge.py` plans and applies a purge (event, derived
  records, paired answer; `keep_responses`), bound by a plan digest;
  `context_purge_report.py` states residue and out-of-reach copies;
  `context_scrub.py` runs `secure_delete`, VACUUM, the WAL checkpoints, the
  scrub-pending mark and the residual scan; `context_retention.py` maps the
  retention planner onto a purge. `cli_context_purge.py` and
  `cli_context_text.py` add `canon context purge|retention`; `context_mcp.py`
  adds `canon.context.purge`.
- `src/canon/client_capture_stop.py` stores a `Stop` delivery's last assistant
  message as an answer event when `--capture prompts+responses` is set;
  `client_capture_input.py` reads the hook's stdin as UTF-8 bytes.
- `project-docs/C1-DECISIONS.md` records D-146 to D-170. Tests plant canaries
  built at run time and scan the database files for every 16-byte window.

Later phases (verifier, migration legs, region installation into an existing
file, the global SOUL.md and the global GEMINI.md surfaces) aim at this same
envelope. Each lands on its own branch.

## Working rules
- Python 3.11+. Standard library only in F0; no runtime dependencies.
- TDD. Every change lands with a test that asserts something meaningful.
- Quality gates: no source file over 300 lines, no function over 50 lines.
- Run the slice with `python -m pytest`. The full F0 suite runs in well under a
  second; run it on every change.
- Never commit `.env`. Secrets go in `.env`, template in `.env.example`.
- Branch before committing. Do not push, open a PR, or deploy without an
  explicit go.
- Release: bump the version in pyproject.toml and `src/canon/_version.py`
  together, add a dated CHANGELOG entry, then push a `v*` tag. release.yml
  runs on the tag push and again on a published GitHub release; the publish
  step skips files PyPI already has, so the second run uploads nothing. Its
  smoke step checks that `canon --version` from the built wheel prints the
  distribution version. `tests/test_packaging.py` builds the sdist
  and checks what PyPI and the sdist carry: absolute README image and link
  URLs, the project URLs, the named docs, the test helpers, and that the suite
  collects from the extracted sdist. A new doc the README or CHANGELOG names
  needs a MANIFEST.in rule.

## The one envelope (F0 contract)
A record is `{canon_schema, kind, id, scope, data, provenance, temporal}`.
- `kind` is one of: personality-block, episodic-memory, synthesized-persona-l3,
  adr-decision, research-artifact-ref (`canon.record/v1`), or one of the W1
  workspace-state kinds workspace-focus, work-item, environment-constraint
  (`canon.workspace-state/v1`). `canon_schema` is a function of the kind.
- `scope` is `global` or `workspace`. There is no `repo` scope: the ~90 per-repo
  instruction files stay hand-authored (the self-contained-repo invariant).
- `provenance` carries `harness` + `source_hash` (both required) and a clock-free
  `create_ord` used for deterministic ordering; wall-clock `create_time` is
  nullable and never authoritative.
- `temporal` (supersede / valid_until) is present only on the four temporal
  kinds; a research-artifact-ref must not carry one.
