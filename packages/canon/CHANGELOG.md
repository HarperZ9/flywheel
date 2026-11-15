# Changelog

## 0.7.0 - 2026-10-22

Canon is now AGPL-3.0-only, the client plugin starts from its own folder, and
a refused client tool call returns a fixed code.

- **Licence.** Future releases are AGPL-3.0-only. Published releases up to
  0.6.0 keep their FSL-1.1-MIT terms and still convert to MIT two years after
  each release.
- **Change.** A refused client tool call returns a fixed code and hint
  (`ARGUMENT_REFUSED`, `SCOPE_MISMATCH`, `STORE_ID_MISMATCH`, `STORE_BUSY`,
  `WRITE_NOT_GRANTED`) in place of one generic string. Codes come from the
  exception type or the client's own refusal, never from exception text.
- **Fix.** The plugin folder now carries the server source at
  `client-plugin/server/src/canon`, so a Claude plugin directory install, which
  receives only that folder, starts. `python scripts/build_client_package.py
  --sync-vendored` regenerates it from `src/canon`, and a test fails when the two
  differ. The launcher no longer falls back to the repository's `src` and exits
  with a clear message when the copy is missing.
- **Change.** Each client tool description now says what the tool does and when
  to call it. PRIVACY.md no longer points to a purge command the plugin lacks.
- **Change.** The Claude plugin manifest carries the directory listing fields:
  display name, keywords, homepage, documentation, support, privacy and terms
  links, and a 1024 px icon at `client-plugin/.claude-plugin/icon.png`.
- **Change.** The Claude plugin asks for the database path, workspace ID,
  project ID and write permission through `userConfig` and passes them as
  `${user_config.*}` launch arguments. The portable and Codex manifests keep
  the `CANON_*` placeholders.
- **Change.** The writing gate's pre-cleaner now targets Forum's
  `forum.prose.clarify` tool, which replaced `forum.prose.humanize`.
  `forum_clarify_pre_cleaner` wraps a clarify call that the caller wires and
  returns the result's `output`. Canon still imports no Forum code.
- **Compatibility.** During Forum's alias window the adapter accepts both
  `forum.prose-clarification/v1` and the deprecated
  `forum.prose-humanization/v1` schema ids. Any other schema id, or a result
  with no string `output`, raises `ValueError` before the checker runs.

## 0.6.0 - 2026-10-01

The read-only context client keeps working while other processes write to the
store or change its journal mode, and it still creates no file next to it.

- **Fix.** A read-only client no longer fails while an authorized writer is in
  a transaction or switches the store between DELETE and WAL journal mode.
  0.5.0 refused a request whenever a `-journal`, `-wal` or `-shm` file existed
  or the store was in WAL mode, so a reader running beside an active writer
  returned errors. The client now reads WAL stores by applying the committed
  frames of the `-wal` file to its in-memory copy, using SQLite's WAL recovery
  rules (salts, running checksums, last valid commit). A zeroed `-journal`
  header from a writer that has not started to commit does not block a read.
  While a writer commits, or a file changes during the copy, the read retries
  for up to 5 seconds and then reports the store busy.
- **Fix.** A running client sees records an authorized client writes later in
  either journal mode, because every request takes a fresh copy.
- **Fix.** The read path still never opens the store through SQLite, so it
  creates no `-journal`, `-wal` or `-shm` file. On Windows it opens files so
  that a writer can still delete its journal or WAL while the client reads.
- **Fix.** Each snapshot read asks for the bytes the file holds, not for the
  256 MiB bound. The larger request allocated the whole bound on every read.
  On Windows that cost about 50 ms per file, so a writer that stored records
  back to back kept the reader retrying until it reported the store busy. A
  `-wal` or `-journal` file that a writer is deleting answers "access denied"
  on Windows; the read now retries in that case instead of failing.
- **Fix.** `canon context purge` and `canon context retention` check that a
  file is a Canon store without creating sidecar files beside it. 0.5.0 opened
  the file with a SQLite read-only connection, which created `-wal` and `-shm`
  files next to a WAL-mode file with no open connection, including a file it
  then refused as not a store.
- **New.** Every MCP tool on the client, context and local servers carries a
  title and the readOnlyHint, destructiveHint, idempotentHint and openWorldHint
  annotations, matched to what the tool does. Hints describe a tool to the
  client. The launch grant still decides whether a write runs. A test fails
  if a listed tool lacks a title or a boolean hint.
- **New.** The client plugin ships a privacy policy that covers what it reads,
  stores and sends, how long data stays, and where to report problems. The
  plugin README opens with what the tool does and three example prompts.
- Limits. A copy is consistent when no file changes between the stat checks
  before and after it; the check compares size and modification time, so a
  change that keeps both within one timestamp tick is not detected. A store
  under steady write load for the whole retry window is reported busy. The
  256 MiB snapshot bound now counts the database and its WAL together.

## 0.5.0 - 2026-10-01

Canon can serve one explicitly selected context database to a local MCP client
through a launch-scoped profile. The default profile reads an existing store;
an operator launch grant adds context ingest. Tool arguments and stored text
cannot grant writes or select another workspace or project. This profile does
not expose purge, capture hooks, instruction-file export or reconcile.

Source plugin packages support Claude Code, Codex and portable stdio clients.
Windows x64 ZIP and MCPB packages include Python. MCPB setup requires the database,
workspace and project bindings and keeps context writes off by default. The
package includes no model and starts no publisher-hosted inference service.

The build records source and runtime digests and refuses release packaging unless
the clean checkout matches its version tag. Synthetic workflow checks exercise
persistence across process restarts, retrieval, provenance and permission refusals.
These checks do not establish marketplace admission or acceptance on every client.
See `docs/client-packages.md` for setup, privacy limits and release qualification.

## 0.4.2 - 2026-09-26

Fixes from a second review of the 0.4.0 purge and capture work. Items marked
**Security** or **Privacy** close gaps that 0.4.0 and 0.4.1 ship; where an
earlier release has the same gap, the item names it. Decisions D-164 to D-170
are in `project-docs/C1-DECISIONS.md`. The record and the context store's
identity version do not change.

- **Security.** Every ingest is redacted, including events sent through the
  `canon.context.ingest` MCP tool. 0.4.0 and 0.4.1 redacted the capture hook's
  events only and stored an MCP ingest as sent, secret-shaped values included;
  0.2.0 and 0.3.0 redacted neither path. An event stored raw before this
  change that is sent again with a secret-shaped value is refused as a
  collision, since its redacted form differs from what is stored.
- **Security.** Query excerpts are scrubbed whole and then cut at 2000
  characters. 0.4.0 and 0.4.1 cut first, so the part of a secret before the
  cut had lost its recognisable shape and came back over MCP. 0.2.0 and 0.3.0
  scrub no query result at all.
- **Security.** Pending references and the sources of related events are
  scrubbed before a query returns them, over MCP and in the context the hook
  hands the client, and the hook prints each pending reference on one line.
  0.2.0 to 0.4.1 returned them as stored, and a reference holding line breaks
  could add lines of its own, such as a forged source, to that context.
- **Privacy.** Recorded transcript paths are counted, not listed, in query
  results and in the context the hook returns
  (`coverage.transcript_locators_not_listed`). 0.2.0 to 0.4.1 listed each path
  as pending extraction, so it went into the next prompt the client sent to its
  model provider. The path names the project folder and often the account.
  `canon.context.get` still returns the whole record, scrubbed.
- **Privacy.** An answer is stored only while its prompt is a live event in
  the same workspace and project, checked inside the write that stores it. In
  0.4.0 and 0.4.1 a purge of the prompt that landed while the `Stop` hook ran
  left the answer, which can restate the prompt, in the store with no message,
  and `canon.context.ingest` stored an answer for a prompt that was never
  captured.
- **Privacy.** A purge report is `purged` only when its scrub finished;
  otherwise it says `scrub_incomplete`, over MCP as on the command line. In
  0.4.0 and 0.4.1 `canon.context.purge` reported `purged` beside
  `scrub_pending: true`, and the residue note said SQLite rewrote the file
  when VACUUM had not run. The note now follows what VACUUM did.
- **Privacy.** The residual scan reads a UTF-16 database in UTF-16. 0.4.0 and
  0.4.1 looked for UTF-8 forms only and reported `purged` over residue in a
  database another tool created as UTF-16.
- **Privacy, docs.** File-permission advice per platform: on Linux and macOS
  SQLite creates the database with the process umask applied, which commonly
  leaves it readable by other accounts, so set `umask 077` or run `chmod 600`.
  The 0.4.0 and 0.4.1 docs said the files take the access rules of their
  folder, which holds on Windows only. The docs now also say that an MCP
  result enters the model's context, and so leaves the machine with a hosted
  provider, and that nothing checks who set the purge tool's apply variable.
- A purge names the unsalted `source_hash` values that earlier ingest and
  query results carried as out of canon's reach: a copy a caller kept can
  confirm a guess of a purged event. This states a limit and does not remove
  it.
- `--keep-responses` with `--all` or `--before-ord` keeps every answer,
  including one whose prompt was never captured. 0.4.0 and 0.4.1 removed such
  an answer under the flag.
- A report that removed nothing still names residue and what canon cannot
  reach. The scrub reports the WAL checkpoint before VACUUM beside the one
  after.
- A dry run no longer takes a write lock and succeeds while a scrub is
  pending. An apply blocked by a reader refuses as `store_busy` with nothing
  changed.
- The capture hook reads stdin as UTF-8 whatever the locale, so non-ASCII text
  is no longer mangled on Windows.
- Docs: the pairing fields the tests supply on synthetic hook inputs, and the
  version the `Stop` fragments need.

## 0.4.1 - 2026-09-26

Fixes found by checking the 0.3.0 and 0.4.0 releases as a user gets them.
Nothing in the record, the context store or its identity version changes.

- `canon --version` (and `-V`) prints the installed version, and
  `canon --json --version` prints it as a result object. 0.4.0 answered
  `canon --version` with "FAIL canon: invalid arguments". `canon.__version__`
  holds the same number, read from one module that a test holds equal to
  pyproject.toml.
- `canon --help` describes the tool and each command. 0.4.0 showed
  "<name> placeholder" for all fifteen. Each subcommand's own `--help`
  (`canon workspace id --help`, `canon context purge --help` and the rest)
  now opens with the same one-line description.
- `python -m canon.local_mcp` and `python -m canon.context_mcp` read their
  arguments before serving: `--help` and `--version` print and exit 0, and an
  unknown argument exits 2 with a message. Before, both started a stdio server
  whatever the arguments were.
- The README loads its drawings and links from absolute GitHub URLs, so the
  PyPI project page shows the images and the walkthrough link resolves.
- The package metadata carries Homepage, Source, Changelog and Issues links.
- The sdist carries the docs the README, this changelog and the user docs name
  (`docs/switching-models.md`, `docs/shared-context.md`,
  `docs/client-capture.md`, `project-docs/W1-WORKSPACE.md`,
  `project-docs/W1-DECISIONS.md`, `project-docs/C1-DECISIONS.md`,
  `project-docs/CONTEXT-STORE-IDENTITY.md`), the hook examples, and what the
  suite imports and reads (the test helpers, the art tools and the block set),
  so the suite collects and runs from an extracted sdist. The 0.4.0 sdist
  left out all three user docs, the W1 and C1 docs and the test helpers, and
  its suite stopped with 57 collection errors. A test builds the sdist and
  checks this.
- The release workflow's smoke step runs `canon --version` from the built
  wheel and fails the release when it does not print the distribution version.
- The build requires setuptools 77 or newer. setuptools 76 rejects the SPDX
  `license` string in pyproject.toml.

## 0.4.0 - 2026-09-26

The shared context store can now remove what it holds. Decisions D-146 to
D-163 are in `project-docs/C1-DECISIONS.md`.

- BREAKING for mixed versions: the first capture or purge this version writes
  raises the context store's identity version from 1 to 2. Canon 0.3.0 and
  older refuse a version 2 database as identity invalid. Reading alone never
  raises the version.
- Adds `canon context purge` (`--event-id`, `--before-ord` or `--all`, with
  `--keep-responses`, `--dry-run`, `--confirm-plan`, `--yes` and
  `--show-preview`) and the `canon.context.purge` MCP tool, which returns a plan
  and applies it only when a second call carries the plan's
  `confirm_plan_sha256` on a server started with
  `CANON_CONTEXT_MCP_PURGE=apply`. A purge removes each selected event, the
  records derived from it at ingest and, by default, its paired answer. It
  appends one audit row and one tombstone per record, so the chain still
  verifies, and a row that reappears under a purged key without a new put fails
  integrity. A client that sends a purged event again stores it again; the
  ingest result says `stored_after_purge`.
- A purge that leaves residue, leaves its scrub unfinished or ends with a
  failing audit chain exits with a failure code (`residue_found`,
  `scrub_incomplete`, `audit_failed`). The command refuses a file that is not a
  canon context store before writing to it.
- The context store refuses a database holding a trigger, view, index or table
  canon did not create.
- A purge runs VACUUM with `secure_delete` on, scans the database, journal and
  WAL files for the purged values, and reports freed disk clusters, legacy
  fingerprints and the copies outside canon's reach. An interrupted purge
  leaves a `scrub_pending` mark, reported by `canon.context.health`, that the
  next confirmed run finishes; a rerun lists events already purged.
- New context records store a salted commitment instead of a plain sha256 of
  the envelope, so a purged record's audit row no longer confirms a guess of
  its content. Records written by 0.3.0 keep their plain digests and are
  counted in purge reports.
- Adds `canon context retention --policy <file>`, which applies the retention
  planner's `tombstone`, `purge-all`, `purge-derived` and `retain` actions as
  one purge plan.
- The capture hook gains `--capture prompts|prompts+responses` (default
  `prompts`) and handles `Stop`: with responses on it stores the last assistant
  message as an answer event linked to its prompt. It gains
  `--transcript-locator path|none` (default `path`; `none` also drops the
  working directory) and `--replay-answers off|on` (default `off`). An answer is
  stored only when its prompt is in the store. Prompt and answer text pass
  through the secret scrubber before they are stored, and returned excerpts
  before they leave. Adds `Stop` hook fragments for Claude Code and Codex.

## 0.3.0 - 2026-09-23

Canon starts to carry a project's working state between models and tools.
The walkthrough and its limits are in `docs/switching-models.md`; the
specification is `project-docs/W1-WORKSPACE.md`.

- Adds a stable project identity (`canon workspace id`). A project with a
  remote is keyed on the normalized remote URL, so two clones or a moved
  checkout stay one project; a non-default port stays in the key. A project
  with no remote is keyed on a nonce canon writes once into its git directory,
  and `git config canon.project <name>` names a project explicitly.
  Credentials in a remote URL never reach the key. A `.git` in the home
  directory or a filesystem root claims only itself, so a dotfiles repository
  does not merge every project below it.
- Adds a per-project record store (default `~/.canon/store`, or
  `CANON_STORE`). Each stored row names its project, and reading a file that
  holds another project's row fails instead of mixing the two. Another
  project's records are readable only when named.
- New records are workspace records. `canon workspace promote` is the only way
  into global scope, and `canon workspace adopt` is the only way to copy another
  project's records in; both need a reason and both are logged. A promotion
  that would replace a record global already holds is refused.
- Adds three workspace-state record kinds under their own schema tag,
  `canon.workspace-state/v1`: `workspace-focus` (goal, active areas, branch),
  `work-item` (title and status), and `environment-constraint` (a constraint or
  a quirk). Decision records gain an optional `rejected_alternatives` list, each
  entry an option and the reason it was dropped. Records of the five existing
  kinds keep the `canon.record/v1` tag and their exact bytes.
- Adds `canon workspace focus`, `task`, `set-status`, `decide` (with
  `--reject OPTION REASON`) and `constraint` (with `--quirk`) to write that
  state by hand.
- Adds `canon handoff --to <target>`, a resume brief for `claude-code`,
  `codex`, `gemini-cli`, `cursor`, `copilot` or plain `markdown`: focus, open
  work, recent decisions with their rejected alternatives, then constraints.
  The brief fits the target's budget as a strict prefix of that order and ends
  with a `Left out` report; `--receipt` writes a `canon.handoff-receipt/v1`
  receipt with digests of the brief and of the records it came from.
- Adds `canon switch --to <target>`, which writes the target's instruction file
  region with the project's blocks and the brief, through the write allow-list,
  through no symlink or junction, and only between the canon markers.
  `--dry-run` writes nothing, `--create` makes a missing file, `--receipt`
  writes the receipt, a file Codex would truncate is refused (at the limit
  Codex's own config sets), and a switch to Codex beside an
  `AGENTS.override.md` is refused. `@path` tokens in the brief are quoted for
  hosts that would import them, and the drift check and reconcile keep the
  brief.
- Adds `canon workspace import --from claude-code|codex <file>`. It reads a
  Claude Code session or a Codex rollout (0.32 or later) and proposes focus,
  work items (from the last plan tool call and `TODO` markers), decisions and
  failed approaches, each with an origin naming the file, its digest, the line
  and the rule. Proposals render nothing until `canon workspace accept`;
  `reject` needs a reason and is remembered. `accept` refuses a proposal whose
  record changed after the proposal was made, unless `--force` is given.
- Each importer declares what it drops and counts it; content it has not seen
  refuses the import unless declared with `--drop-type` (the label or the bare
  type name). Text the host wrote in the user role (slash commands, shell
  output, compaction summaries, skills, sub-agent notices), rolled-back Codex
  turns and rewound Claude Code branches are not mined, and the Claude Code
  task tools are read as the plan. A source that names a
  different repository or working directory is refused unless
  `--accept-foreign-source` is given.
- Adds a secret scrubber in front of every import. It scrubs each source string
  whole before extraction. Provider keys and tokens, JWTs, PEM, PGP and PuTTY
  private keys, webhook URLs, bearer, basic and API-key headers, cookies,
  passwords and tokens in URLs, Azure and `.npmrc` keys, password fields and
  secret-named assignments in any case are replaced with `[REDACTED:<rule>]`. The store
  also refuses any record that still matches, including one typed by hand, and
  a brief or instruction region that would carry one is refused.
- Adds three surfaces to the write allow-list: `GEMINI.md`,
  `.github/copilot-instructions.md`, and one canon-owned Cursor rule,
  `.cursor/rules/canon.mdc` (created with `alwaysApply: true` frontmatter).
  The allow-list is now seven exact paths.
- Personality blocks may carry `applies_to` glob patterns. No surface can load
  a block for some files only, so each target declares the downgrade: the block
  is written always-on with an `Applies to:` line the model reads as advice.
  Claude Code and Gemini CLI also declare that an `@path` line is a file import
  there. A per-target round-trip verdict fails on any difference a target did
  not declare; `canon workspace targets` prints the table.
- The region grammar moves to `canon.textblock/v1` for the optional `applies`
  attribute. A region with no scoped block is byte-identical to v0.
- `write_surfaces` reports a missing file as `missing` and does not create it.
- `switch` records what it wrote to each file. When the region was edited in
  place since then, each edit becomes a proposed record (a changed block, a
  ticked or added task, a new goal, a new quirk; anything else is kept as a
  note), and `switch` refuses to overwrite until every proposal is accepted or
  rejected. `canon workspace pull --from <target>` reads the edits back without
  switching.
- In-place edits inside a rendered region come back as proposals, and `switch`
  waits for them. Several checkouts of one project, and a file restored by a
  branch switch, read as stale renders rather than edits; an edit proposes only
  the fields it changed; a removed constraint, decision or goal line is
  proposed or kept; an edit of a block another project or global owns is kept
  as a note; and a rejection holds only for the render it was made against.
- Registers six new version pins: `project-id`, `project-row`,
  `workspace-state`, `handoff-receipt`, `import-report` and `render-ledger`.
- Fixes `python -m canon.cli mcp`, the command MCP host configurations use to
  start the server. In 0.1.0 and 0.2.0 it imported the module and exited 0
  without reading a request, so a host reported the server as failed with
  "Connection closed". The `canon mcp` console script and `python -m canon mcp`
  were not affected.

Limits:

- The identity reader does not follow git `include` directives or `insteadOf`
  rewrites.
- Renaming a remote changes its id, as does moving a directory that has no git
  directory. The old records are kept and can be adopted; nothing merges them
  on its own. Two repositories cloned from one starter share its remote and so
  one id; canon announces a checkout new to a project, and
  `git config canon.project <name>` splits them.
- The four storage adapters still hold only the five original kinds. The
  workspace-state kinds live in the per-project store.
- The brief budgets are canon's defaults and can be overridden with
  `--budget-bytes` and `--budget-lines`. The host file limits come from each
  host's public documentation, read on 2026-09-23, and hosts change; the Codex
  limit follows `project_doc_max_bytes` in the Codex config.
- The brief lists what was recorded. It does not know about work that happened
  in a session nobody recorded or imported.
- The importers use fixed text patterns. A decision or task phrased another
  way is not proposed, and a proposal is a candidate, not a fact.
- Neither session format is a stable public interface. The importers were
  checked against public sources on 2026-09-23 and refuse content they do not
  recognise rather than guess.
- The scrubber recognises secrets by shape. A secret with no recognisable shape
  passes through, a value shorter than four characters after a secret-named key
  is not redacted, a value that reads as code or a type name after such a key
  is left alone, and email addresses are not redacted.
- `switch` re-reads the file just before writing and refuses if it changed; the
  short window between that read and the write is not locked.
- Gemini CLI, Cursor, ChatGPT and Claude web exports have no importer yet.
- Edit back-flow reads line shapes the brief itself writes. An edit in another
  shape is kept as a note to accept, not mapped to a record.

## 0.2.0 - 2026-09-22

- Publishes to PyPI as `flywheel-canon`. The bare name `canon` belongs to an
  unrelated project, so the distribution carries the prefix while the console
  script stays `canon`.
- Adds an OIDC trusted-publishing release workflow with tag/version, artifact
  digest, clean-venv entry-point resolution, and sdist-rebuild gates.
- Adds run-lock concurrency control, and fixes POSIX run-lock descriptor release.
- Adds doctor diagnostics, retention planning, replay checks, rescue handoff, and
  an import review policy.
- Hardens Canon source reads.

## 0.1.0 - 2026-09-07

First GitHub release for Canon.

- Keeps the existing read-only MCP surface: `canon.status`, `canon.doctor`,
  `canon.blocks`, `canon.render`, `canon.validate`, and `canon.check`.
- Adds provider-neutral continuity preview and export from explicit
  `records.jsonl` and `atoms.jsonl` inputs.
- Exports Canon Markdown, capsule JSON, readiness JSON, or a three-file bundle
  containing `CANON.md`, `canon.capsule.json`, and `readiness-probe.json`.
- Records source-state hashes, artifact hashes, target tier, omissions, and
  does-not-prove limits in the generated capsule outputs.
- Uses confined bundle publication or fails closed. On Windows, the final bundle
  directory rename is parent-handle-relative and leaf-only.

Limits:

- Canon does not import ChatGPT web conversations, Codex task databases, Claude
  web history, Claude Code sessions, provider auth caches, or credentials.
- The `codex-cli` and `claude-code` targets are native-advisory. App and web
  targets remain guided until their hosts provide stronger startup evidence.
- Bundle export proves the command's publication boundary, not immutability
  after the command returns.
- New bundle creation currently requires the supported Windows native backend.
  Linux and macOS refuse new bundle creation without writing. Preview and stdout
  exports remain available there.
- Release downloads are distributed through GitHub. No PyPI publication claim
  is made.
