<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/HarperZ9/canon/main/docs/art/hero-dark.svg">
  <img src="https://raw.githubusercontent.com/HarperZ9/canon/main/docs/art/hero-light.svg" alt="canon: One local record of your agent instructions and project state, written into each coding agent's own file. Layered rings drawn in fine lines, each slightly deformed, tighten around a bright core." width="100%">
</picture>

# canon

One local record of your agent instructions and project state, written into
each coding agent's own file.

canon is for people who move one repository between coding agents: Claude Code,
Codex CLI, Gemini CLI, GitHub Copilot and Cursor. You record what the project is
doing, the open work, and each decision with the alternatives you dropped and
why. canon keeps that as typed records on your machine and writes a resume brief
into the file the next agent reads at startup (`CLAUDE.md`, `AGENTS.md`,
`GEMINI.md`, `.github/copilot-instructions.md` or `.cursor/rules/canon.mdc`). It
writes only between its own markers in that file. When you or an agent edit
inside those markers, the next switch turns each edit into a proposal for you to
accept or reject.

It runs no model and makes no network call. Records live in `~/.canon/store`,
outside the repository, and each project's records stay apart from every other
project's.

## Install and first run

Python 3.11 or newer. No runtime dependencies.

```bash
python -m pip install flywheel-canon
cd your-repo
canon workspace focus --goal "Ship the JSON export" --area src/export
canon workspace decide --title "Keep the CSV writer" --decision "Add JSON beside CSV" \
    --context "Downstream scripts parse CSV" --reject "Replace CSV" "breaks three scripts"
canon handoff --to codex
canon switch --to codex --create
```

The handoff prints the brief the next agent gets:

```text
## Focus
Goal: Ship the JSON export
Branch: main
Areas: src/export

## Decisions
- Keep the CSV writer [accepted] (decision-2): Add JSON beside CSV
  Why: Downstream scripts parse CSV
  Rejected: Replace CSV. Reason: breaks three scripts
```

The switch creates `AGENTS.md` with that brief between
`<!-- canon:begin scope=workspace -->` and `<!-- canon:end -->`, and prints
`Codex CLI: created AGENTS.md`. To pick up where a Claude Code or Codex session
left off, `canon workspace import` proposes records from its transcript, and
nothing reaches a brief until you accept it.

`canon mcp` serves six read-only tools over MCP on stdio (status, doctor, blocks,
render, validate, check). Nothing on that server writes a file.

## How it compares

[Ruler](https://github.com/intellectronica/ruler) and
[rulesync](https://github.com/dyoshikawa/rulesync) keep one set of rule files and
generate each agent's configuration from it. canon covers that case and adds
project state: focus, work items, decisions with their rejected alternatives,
and constraints, held as records with a source hash on each. It fits the brief to
each agent's size budget and names what it left out. It refuses to store
secret-shaped values in workspace records.

[Mem0](https://github.com/mem0ai/mem0) and
[Basic Memory](https://github.com/basicmachines-co/basic-memory) are memory
services an agent queries while it works. canon writes the file the agent reads
before it starts, so it works with agents that have no memory integration.

## Limits

- The session importers use fixed patterns, and the Claude Code and Codex
  transcript formats they read are not stable interfaces.
- The secret scrubber finds secrets by shape. A secret with no recognisable shape
  gets through.
- A brief holds only what was recorded or imported, never the whole history of
  earlier sessions.
- The store is plaintext on disk. Purged text can stay in freed disk space until
  it is reused.
- No agent file can load a block for some files only. canon writes such a block
  for every file with an `Applies to:` line and declares that downgrade.

## The record

**Local client packages.** The [client package guide](https://github.com/HarperZ9/canon/blob/main/docs/client-packages.md)
connects an explicit context database to Claude Code, Codex or another local stdio
MCP client. Reads are the default; storing new context needs a write permission
you grant at launch. Windows packages include Python. Your client supplies the model; Canon
stores and retrieves context without running a model or hosting inference.

- **One envelope, eight kinds.** An authored personality block, a raw or
  extracted memory, a synthesized persona, a decision record, and a reference to
  an external research artifact share one record shape with a provenance receipt
  on every entry. Three workspace-state kinds (a project's focus, its work items,
  and its constraints and quirks) use the same shape under their own schema tag.
- **Two scopes that layer.** A `global` block is your default everywhere; a
  `workspace` block with the same id overrides it where that workspace applies.
  A render resolves the effective set for its target, current entries only.
- **Deterministic by construction.** Ordering uses a clock-free ordinal, so a
  rebuild from the same records is byte-identical. The wall clock is kept only
  as a non-authoritative convenience.

## See it work, step by step

The [animated explainer](https://harperz9.github.io/repo-explainers/canon.html)
walks through a small repository's focus and a decision with its rejected alternative, a secret refused before storage, the size-budgeted brief, a switch that writes it between canon's markers in AGENTS.md, and an edit inside that region turned into a proposal. Every value on it is output from this repository. Its
source is [docs/explainer/index.html](https://github.com/HarperZ9/canon/blob/main/docs/explainer/index.html).

## Moving a project between models

Switching a repository from one agent to another usually means explaining the
project again, and memory tools that key on a user rather than a project show
one repository's history inside another. canon keeps a project's working state
as records bound to that project and writes it into the file the next agent
reads at startup.

```bash
cd your-repo
canon workspace import --from claude-code path/to/session.jsonl   # or --from codex
canon workspace list --proposed
canon workspace accept <proposal-id>                               # an id from the list
canon workspace focus --goal "Ship the JSON export" --area src/export
canon workspace decide --title "Keep the CSV writer" --decision "Add JSON beside CSV" \
    --context "Downstream scripts parse CSV" --reject "Replace CSV" "breaks three scripts"
canon switch --to codex --create
```

- **One project, one store.** The project id comes from the repository's remote,
  from `git config canon.project <name>` when you set one, or from a nonce
  canon keeps in `.git` when there is no remote. Every stored record names its
  project, and a read that finds another project's record fails instead of
  mixing the two. Global scope is reached only by `canon workspace promote`,
  and another project's records only by naming them; both are explicit.
- **The state you would otherwise re-explain.** Focus, open work items,
  decisions with the alternatives dropped and why, and constraints and
  environment quirks are record kinds of their own. A dropped alternative cannot
  be recorded without its reason.
- **Import what the last session knew.** `canon workspace import` reads a Claude
  Code session or a Codex rollout and proposes focus, open plan steps, `TODO`
  markers, decisions and failed approaches by fixed patterns. Each proposal
  names the file and line it came from, and nothing reaches a brief until you
  accept it.
- **Secrets stay out of workspace records.** Keys, tokens, private keys, auth
  headers, cookies, passwords in URLs and config files, and secret-named
  assignments in any case are redacted before a workspace record is stored, the
  workspace store refuses anything that still looks like one, and a brief that
  would carry one is refused. Shared context events are redacted by the same
  rules at every ingest, through the capture hook or `canon.context.ingest`,
  but not refused (see C1 below).
- **Losses are named.** Each importer lists what it drops and counts it. A
  session with content the importer has not seen is refused until you declare
  that drop, so a format change cannot lose data quietly.
- **A brief that fits.** `canon handoff --to <target>` lists focus, open work,
  recent decisions and constraints, in that order, inside the target's size
  budget. What does not fit is left out whole and named at the end, and
  `--receipt` writes digests of the brief and the records behind it.
- **Switch in one command.** `canon switch --to <target>` writes your blocks and
  the brief into the target's own instruction file, between canon's markers
  only. `--create` makes a missing file; an existing file is opted in by adding
  the two marker lines (`<!-- canon:begin scope=workspace -->` and
  `<!-- canon:end -->`). If you or an agent edit inside that region, the next switch turns each
  edit into a proposal and waits for your decision instead of overwriting it.

Targets: `claude-code` (`CLAUDE.md`), `codex` (`AGENTS.md`), `gemini-cli`
(`GEMINI.md`), `copilot` (`.github/copilot-instructions.md`), `cursor`
(`.cursor/rules/canon.mdc`), and `markdown` for a brief to paste into a chat app
or a local model. `canon workspace targets` prints each target's budget and what
its file cannot express: none of these files can load a block for some files
only, so a block scoped with `applies_to` is written for every file with an
`Applies to:` line, and that downgrade is declared rather than silent.

The walkthrough, every command, and the limits are in
[`docs/switching-models.md`](https://github.com/HarperZ9/canon/blob/main/docs/switching-models.md). The short version of
the limits: the importers use fixed patterns rather than a model, the session
formats they read are not stable interfaces, the scrubber recognises secrets by
shape, and the brief knows only what was recorded or imported.

## How one record becomes the file each tool reads

![Eight stages taking one record to the file a tool reads: record, validate, layer, resolve, render, region, allow-list, write. Every entry is one envelope in one of eight kinds: an authored personality block, an episodic memory, a synthesized persona, a decision record, a reference to an external research artifact, and three workspace-state kinds for a project's focus, its work items and its environment constraints. The validator checks every field and refuses a record it cannot vouch for. A workspace block overrides a global block carrying the same id, and the resolve step keeps current entries only, ordered by a clock-free ordinal so a rebuild is byte-identical. The block set is rendered to text and spliced into the span between the canon begin and end markers, and every byte outside that span is preserved. The write allow-list holds seven surfaces: a global and a workspace file for Claude Code, an AGENTS.md for Codex, a workspace SOUL.md for Hermes, a GEMINI.md for Gemini CLI, the repository instructions file for GitHub Copilot, and one canon-owned Cursor rule. A path outside that list is refused, and so is a file with no canon region. Three outcomes: written inside the markers canon owns, a surface that drifted and needs a human, and a file canon declines to write at all.](https://raw.githubusercontent.com/HarperZ9/canon/main/docs/art/surface-lane.svg)

canon writes seven paths and no others, and inside those seven it rewrites only
the span between its own markers. A file with no canon region is left alone.

## How a rendered file is checked back against the record

![Eight stages checking a rendered file back against its record: read, extract, ingest, canonical, compare, drops, legs, verdict. The file is read as it sits on disk and the region between the canon markers is extracted byte exactly. The region text is ingested back into records, each reduced to one canonical form so the comparison is against a single shape rather than a formatting accident. The rendered form and the ingested form are compared field by field. Every field that failed to survive is classified against the losses that storage adapter declared in advance, and a loss nobody declared is a refusal. The aggregate check folds four legs: surface drift, the vault round-trip, the vault read symmetry, and the persona assessment. A leg whose seam is not wired reports nothing and does not affect the result. The verdict is one exit code, zero when every wired leg passed and one otherwise, and all four gate functions in the codebase share that signature so a build keys on them the same way. Three outcomes: the record survives the file, a declared drop that was named in advance, and a refusal that returns a nonzero code.](https://raw.githubusercontent.com/HarperZ9/canon/main/docs/art/verdict-lane.svg)

A round-trip that loses a field passes only when the adapter declared that loss
in advance. Anything else fails the gate rather than logging a warning.

## What canon carries

![A table of twelve rows: what canon carries, how many of it there are, and where each number is read from. Eight record kinds share one envelope: five under the v1 record tag and three workspace-state kinds under their own tag. Two scopes layer, workspace over global. Seven surfaces sit on the write allow-list: a global and a workspace file for Claude Code, an AGENTS.md for Codex, a workspace SOUL.md for Hermes, a GEMINI.md, the Copilot instructions file, and one Cursor rule. Four storage adapters implement the backend protocol, and five capability tokens describe what each one can carry. Twenty-two schema pins name the seams that carry a version. The aggregate check folds four legs, and four gate functions share the same zero or one exit code. 170 source modules hold 28,553 lines, and 110 test files hold 1869 tests. Two surfaces named in the roadmap are absent from the catalog, a global SOUL.md and a global GEMINI.md, so canon does not render them.](https://raw.githubusercontent.com/HarperZ9/canon/main/docs/art/record-table.svg)

Every count is asserted against the module that defines it in
[`tests/test_repo_art.py`](https://github.com/HarperZ9/canon/blob/main/tests/test_repo_art.py).

## What is built

F0 is the record of record: the canonical schema, its validator, and the
per-scope layering. F1 adds the storage seam: a `MemoryBackend` protocol with
capability tokens and four adapters, among them a zero-drop SQLite reference and
injected-handle adapters for a memory fact-engine and an authored-block store.
R0 adds the block round-trip gate: a byte-exact region boundary inside a managed
file, a record-to-text renderer and its inverse, and a go/no-go verdict that
proves a block set round-trips to its canonical form with every dropped field
declared.

R1 renders your files from the record. It resolves the block set for a file's
scope and rewrites only the region canon owns, every byte outside it preserved.
It writes only a fixed allow-list of files, and only a file you have opted in
with a canon region. Where a tool reads both a global and a workspace file, the
workspace file carries just your workspace blocks, so a shared block is never
duplicated; where a tool reads one file, that file carries the full resolved set.

R2 mirrors your whole record set into an Obsidian vault. Each record becomes one
markdown note you can read, search, and link, and a MEMORY.md index lists them
all. The full record rides inside every note, so a rebuild is exact and editing a
note's prose never rewrites the record behind it. canon writes only inside its own
vault, never touches a file it did not write, and when you drop a record it
reports the note left behind rather than deleting it. R2 also adds SOUL.md to the
rendered surfaces.

V2 through V4 add the checks and the decision on top of them. A drift check
re-derives every managed surface and compares only the region canon owns, so
your own prose outside the markers is never flagged. A persona check reports
whether the memories behind a synthesized persona still resolve. V4 separates a
mechanical fast-forward from a conflict, writes the fast-forwards, and raises a
durable gate for anything a human should adjudicate.

A harness reaches all of this over MCP. `canon mcp` serves six read-only tools:
identity, a readiness diagnostic, the authored record set, the render for a
scope, the validator, and the aggregate check. Nothing on that server writes a
file. Reconcile stays a library call, because rewriting your instruction files
and raising a gate is an action with a person behind it.

The CLI can also compile a provider-neutral continuity capsule from two explicit
inputs: `records.jsonl` and `atoms.jsonl`. Preview reports artifact names,
target tier, readiness probe data, and source-state hashes without writing.
Export writes the same capsule as Canon Markdown, capsule JSON, readiness JSON,
or a three-file bundle. The capsule records omitted state as typed atoms or
transform omissions and says what the export does not prove, including host
enforcement. It does not import provider auth, private databases, ChatGPT web
state, or Claude web state.

W1 adds the workspace backend described under "Moving a project between
models": a project identity and a store that refuses to mix projects, the
workspace-state kinds, the handoff brief and `switch`, the two session
importers with their secret scrubber and declared losses, three more surfaces
(`GEMINI.md`, the Copilot instructions file, one Cursor rule) with the
downgrades each declares, and the read-back of edits made inside a rendered
region. It is specified in
[`project-docs/W1-WORKSPACE.md`](https://github.com/HarperZ9/canon/blob/main/project-docs/W1-WORKSPACE.md).

C1 lets you own the shared context store (`docs/shared-context.md`). The
capture hook stores your prompts by default and stores the assistant's answers
only when you run it with `--capture prompts+responses`; it never stores tool
calls or reasoning as records, though an answer's own text can quote files and
tool output (`docs/client-capture.md`). Prompt and answer text pass through
the secret scrubber before they are stored, which catches secret-shaped values
by pattern and misses a secret with no recognisable shape. An answer is stored
only while the prompt it answers is in the store, checked in the same write.
Pairing needs the same prompt id on the prompt and on the `Stop` delivery, and
the answer in `last_assistant_message`; the tests use synthetic hook inputs,
and whether each live client sends those fields is unverified. `canon context
purge` removes captured
events together with the records derived from them and the answer paired with
each prompt. `--dry-run` shows the plan and its digest, and `--confirm-plan`
applies exactly that plan or refuses it as stale; `--yes` applies the plan as
it stands when the command runs. `canon context retention` applies a retention
policy the same way. Canon keeps every captured event until you purge it. The
audit chain still verifies after a purge, each removed record leaves a
tombstone with no content hash, and new records store a salted digest that no
longer opens once the record is gone. A client that sends a purged event again
under the same native id stores it again, and the capture hook says so. The
store stays plaintext on disk, so freed disk clusters can hold purged text until they are reused, and
every purge report says so along with the copies canon cannot reach. What the
hook returns to a later prompt becomes part of the prompt the client sends to
its model provider; with a hosted provider that text leaves your machine under
the provider's terms. The first capture or purge this version writes raises the
context store's identity version to 2, and canon 0.3.0 and older refuse such a
database as identity invalid. These changes shipped in 0.4.0. Version 0.4.2
closes security and privacy gaps that a second review found in 0.4.0 and
0.4.1; `CHANGELOG.md` marks each one, and a store in use with either version
should move to 0.4.2.

Installing a region into an existing file, the first migrator on the version seam,
and the global SOUL.md and the global GEMINI.md surfaces are later phases.
Everything shipped has tests, and all of it aims at the one envelope. The
capture hook's tests run on synthetic hook inputs, not recordings of live
clients.

## Run it

The latest release is on PyPI as `flywheel-canon` (the console script is
`canon`):

```bash
python -m pip install flywheel-canon
```

The workspace commands above (`canon workspace`, `canon handoff`,
`canon switch`) first shipped in 0.3.0. To run the latest `main` instead of a
release, install from a checkout of this repository:

```bash
python -m pip install -e .
```

Serve the record set to a harness:

```bash
canon mcp
```

Ask canon what it believes, with no transport in the way:

```bash
canon check
canon blocks
```

`canon check` exits non-zero when a wired leg fails or the block pool is not the
authored set, so a build can key on it. Point it at your records with
`CANON_BLOCKS_DIR`, and at your files with `CANON_HOME` and `CANON_WORKSPACE`.

Preview and export a continuity capsule from explicit local inputs:

```bash
canon --json preview --workspace . --records records.jsonl --atoms atoms.jsonl --target codex-cli
canon export --workspace . --records records.jsonl --atoms atoms.jsonl --target codex-cli --format canon-md
canon export --workspace . --records records.jsonl --atoms atoms.jsonl --target codex-cli --format capsule-json
canon --json export --workspace . --records records.jsonl --atoms atoms.jsonl --target codex-cli --format bundle --out bundle
```

The `codex-cli` and `claude-code` targets are native-advisory surfaces. App and
web targets remain guided until their hosts provide stronger startup evidence.
Preview and stdout exports work across supported Python platforms. Creating a
new bundle currently requires Windows with the confined native writer. On Linux
and macOS, new bundle creation returns `unsafe_path` without writing; use stdout
export there. The Windows final directory rename is parent-handle-relative and
leaf-only. This bounds publication, not immutability after the command returns.

Run the suite:

```bash
python -m pytest
```

No runtime dependencies. Python 3.11 or newer.

## Layout

```
src/canon/
  schema.py, validator.py, layering.py   the record, its rules, per-scope resolve
  backends/                              the storage seam and four adapters
  region.py, textblock.py, fidelity.py   the byte boundary, the text codec, the gate
  surface.py, registry.py                the render composition, the write allow-list
  frontmatter.py, vault.py               the note frontmatter codec, the one-record note
  vault_mirror.py, vault_fidelity.py     the whole-vault mirror and its round-trip gate
  drift.py, writing_gate.py              the surface drift check, the injected prose gate
  persona_thesis.py, canon_check.py      the persona basis adapter, the aggregate check
  reconcile*.py                          the fast-forward decision and its durable gate
  blocks.py, local_mcp.py, cli.py        the authored-block loader, the MCP door, the CLI
  capsule*.py, atom.py, adapter.py       the continuity capsule, atom and target contract
  cli_compile.py, cli_export.py          preview, stdout export and bundle export
  cli_artifacts.py, cli_publish.py       source hashes and confined artifact publishing
  workspace/                             project identity, the store and its isolation,
                                         authoring, briefs, switch, importers, the
                                         scrubber, target downgrades, edit read-back
  validator_workspace.py, versions_pin.py the workspace kinds' rules, the pin type
  textblock_scope.py                     a block's glob scope in the region grammar
  cli_workspace*.py, cli_handoff.py,     the workspace, handoff, switch, import and
  cli_import.py                          pull commands
tests/                                   round-trip, validator, layering, backend,
                                         fidelity, surface, orchestration, vault,
                                         drift, reconcile, continuity, and artwork proofs
docs/art/                                the drawings above and the spec they render from
project-docs/                            the F0, F1, R0, R1, R2, V2, V3, V4, MCP, W1 decisions
```

See [`project-docs/`](https://github.com/HarperZ9/canon/tree/main/project-docs) for the schema reference, the layering derivation, the
section-ownership contract, the declared drops each storage backend must
announce, and the decisions behind the round-trip, vault, drift and reconcile
gates.

## License

Canon's code is under the GNU Affero General Public License, version 3 only
(AGPL-3.0-only). See [`LICENSE`](https://github.com/HarperZ9/canon/blob/main/LICENSE)
and [`NOTICE`](https://github.com/HarperZ9/canon/blob/main/NOTICE).

Anyone may use, study, change and share Canon. Anyone who distributes a changed
copy, or runs one as a network service, must offer its source under the same
licence. That keeps a portable memory record portable in every fork.

Releases up to and including 0.6.0 were published under FSL-1.1-MIT. Those
releases keep their terms, and each converts to MIT two years after its release.
