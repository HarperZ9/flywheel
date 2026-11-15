# W1: the workspace backend

A developer who moves one repository between Claude Code, Codex, Cursor, Gemini
CLI and a local model loses the working state that lived in the old tool: what
they were doing, what is still open, what was decided and what was tried and
dropped, and which quirks of the environment bite. The next tool starts from
nothing, and the developer explains the project again. A second failure sits
next to the first: memory tools that key on a user or an agent rather than a
project show one repository's history inside another.

W1 keeps that state as canon records bound to one project, and renders it for
whichever tool comes next. This document is the specification. The decisions
behind it are in `W1-DECISIONS.md`.

## Project identity

`canon.workspace.identity.derive_identity(workspace)` returns a
`ProjectIdentity`: a `project_id` (`prj_` and 32 hex digits), the `method` that
derived it, a path-clean `key`, a display `label`, and the local `root`.

1. The root is the nearest directory at or above the workspace that holds a
   `.git` entry. A `.git` file (a worktree or a submodule) is followed to its
   git directory, and a worktree's `commondir` is followed to the shared config.
2. A `.git` in the home directory or a filesystem root claims only that
   directory itself. A dotfiles repository in the home directory would
   otherwise give every unversioned project below it one shared identity.
3. A `canon.project` value in the repository's git config (`git config
   canon.project <name>`) names the project explicitly. The method is
   `config`, the key `project:<name>` and the label the name. It wins over the
   remote, so two checkouts that share a remote but are different projects can
   be split for good.
4. With a remote (`origin`, else the first remote by name), the key is the
   normalized remote URL: scheme, credentials, query, fragment and a trailing
   `.git` are dropped, the host is lowercased, and the path is kept as written.
   A port is dropped only when it is the scheme's default (22 for ssh, 80 for
   http, 443 for https, 9418 for git); any other port stays in the key as
   `host:port`, because two servers on one host are two projects.
   `git@github.com:o/r.git`, `https://github.com/o/r` and
   `ssh://git@github.com:22/o/r` all give `github.com/o/r`. An ssh remote on a
   custom port and the https remote of the same repository split; `adopt`
   joins them.
5. A remote that is a local path gives `local-sha256:<digest>`, so the key
   carries no local path.
6. With no remote, canon writes a random nonce once into the repository's
   shared git directory (`canon-project-nonce`, next to the git config) and
   the key is `nonce-sha256:<digest of the nonce>`. The nonce travels with
   `.git`, so moving the repository keeps its id, worktrees share it, and a new
   `git init` at a reused path gets a new one. A directory with no git
   directory, or one canon cannot write, falls back to
   `path-sha256:<digest of the resolved root>`.

The id is `prj_` plus the first 32 hex digits of
`sha256("canon.project-id/v1\n<method>\n<key>")`.

### Collisions

Two checkouts get one id, and so share records, when:

- they have the same normalized remote. Two clones of one repository in two
  directories are one project on purpose. A fork has its own remote URL and so
  its own id.
- they have no remote and share one git directory: a worktree, or a copy made
  with the `.git` directory inside it. A repository deleted and re-created at
  the same path gets a new nonce and so a new id. A directory with no git
  directory still falls back to its path.
- their remote URLs differ only in the parts normalization drops (scheme,
  credentials, a default port, host case, `.git`).
- they are two unrelated repositories started by cloning one starter
  repository, which keep its remote. The rules cannot see this merge, so it is
  announced: `project.json` in the store keeps a path-clean digest of every
  checkout root that has written to the project, and any workspace command run
  from a root the project has not seen prints a one-line notice naming the
  number of other checkouts and the two ways to split
  (`git config canon.project <name>` or a different remote).

Two remotes that differ only by path case get two ids. That is deliberate: a
split hides records until they are adopted, while a merge shows one project's
records to another. A digest collision between unrelated keys needs a 128-bit
prefix collision and is not handled.

### Renames and moves

- Moving or renaming the local directory of a project with a remote keeps its
  id.
- Renaming the remote repository, or transferring it to another owner, changes
  the key and so the id.
- Moving a project with no remote keeps its id, because the nonce moves with
  `.git`. A directory with no git directory is keyed on its path, and moving it
  changes its id.

In the changing cases the old records stay in the store under the old id
and are not shown under the new one. Nothing merges them automatically.
`canon workspace adopt --from <old-id> --reason <text>` copies the old
project's accepted records to the new id, refuses before writing if any
record id would overwrite one the new project already holds, and logs each
adopted record with the project it came from.

## Workspace state

Four kinds of record carry the working state a developer would otherwise
explain again to every new tool. The schema is in `F0-SCHEMA.md` (W1
addendum); the builders are in `canon.workspace.authoring`.

| what | kind | id | written by |
|---|---|---|---|
| current focus: goal, active areas, branch | `workspace-focus` | `focus` (one per project) | `canon workspace focus` |
| open work and its status | `work-item` | `task-<n>` | `canon workspace task`, `set-status` |
| decisions, with the alternatives dropped and why | `adr-decision` | `decision-<n>` | `canon workspace decide --reject OPTION REASON` |
| constraints and environment quirks | `environment-constraint` | `constraint-<n>` | `canon workspace constraint [--quirk]` |

Every builder validates before it returns, stamps a provenance receipt
(`harness: canon-cli`, a content hash of the kind and payload, and the next
clock-free ordinal from the project's store), and writes a workspace record.
`set-status` keeps a work item's id and ordinal, so its place in a brief does
not move when its status changes. `focus` reads the branch from the
repository's `HEAD` file when `--branch` is not given, and runs no git command.

## Handoff

`canon handoff --to <target>` writes a resume brief for the next agent from the
project's pool (`canon.workspace.brief.make_brief`). It has four sections, in
priority order:

1. **Focus**: the goal, the branch, the active areas and any notes.
2. **Open work**: work items that are `in-progress`, `blocked` or `open`, in
   that order.
3. **Decisions**: current decisions, most recent first, each with the reason
   (`Why:`) and every rejected alternative with the reason it was dropped.
4. **Constraints and quirks**, oldest first.

Inside a section this project's records come first, then global records marked
`[global]`, then records of a named project marked `[from <project_id>]`. A
closed work item, a superseded decision, a personality block (it goes in the
instruction region instead) and any other kind are excluded by rule; the
receipt names each one and the rule.

### Budgets

| target | brief budget | host limit it sits inside |
|---|---|---|
| `claude-code` | 12,000 bytes, 120 lines | docs advise a `CLAUDE.md` under 200 lines (high); a 40,000-character warning is user-reported (moderate) |
| `codex` | 16,384 bytes, 400 lines | `AGENTS.md` files share a 32,768-byte budget and are truncated past it (high) |
| `gemini-cli` | 16,384 bytes, 400 lines | no documented limit |
| `cursor` | 16,384 bytes, 250 lines | docs advise a rule under 500 lines (high) |
| `copilot` | 16,384 bytes, 400 lines | about 1,000 lines per instruction file at most (high) |
| `markdown` | 16,384 bytes, 400 lines | none; a brief to paste |

The host figures were read from each tool's public documentation or source on
2026-09-23. The brief budgets are canon's choices inside them, leaving room for
the personality blocks that share the file, and `--budget-bytes` and
`--budget-lines` override them.

### Truncation

The brief is a strict prefix of the priority order. When the budget runs out,
every record after the cut is left out whole, and the brief ends with a
`Left out` section that counts them, names as many as fit, then `and N more`,
and says how to get the full list: for `handoff` with `--receipt`, "The
receipt lists every one."; without it, the command to run; for `switch`, the
`--dry-run --receipt FILE` command that writes the same receipt. A
lower-priority record never appears while a higher-priority one is missing,
and no record is shortened. Inside an instruction region the budget is
measured on the block as it lands, sentinel line included. A budget too small
for the header and the truncation report is refused (`budget_too_small`); a
budget below one byte or one line is a usage error.

### Receipt

`--receipt <file>` writes a `canon.handoff-receipt/v1` object: the path-clean
project identity, the target and its budget with the basis for it, the brief's
sha256, size in bytes and lines, a sha256 over the pool it was built from, the
declared projects, every included and left-out record with its content hash,
every record excluded by rule with the rule, and a `does_not_prove` list. A
switch receipt adds `rendered_block` (the sha256, bytes and lines of the brief
block as written) and `interior` (the sha256 and bytes of the whole region
interior), so it can be checked against the file. `handoff` checks both of its
destinations before writing either and removes the first if the second fails;
`switch --receipt <file>` writes its receipt the same way, and every switch
keeps its last receipt in the render ledger. The receipt passes the same
secret check as the brief, since it carries a label for every left-out record.
No clock is read, so the same pool gives the same brief and the same receipt.

### Switch

`canon switch --to <target>` renders the target's workspace instruction file
region: this project's personality blocks, by the same authored-split rule the
rest of canon uses, followed by one generated block, `canon-workspace-brief`,
holding the brief. The target reads its instruction file at startup, so the
brief reaches it without a paste. The write follows the canon rules:

- only the catalog surface for that target, resolved under the repository root,
  and never through a symlink, junction or other reparse point on the way to it
  (`unsafe_path`); the check runs again at write time, and a created file is
  opened in exclusive mode;
- only between the canon markers, every byte outside them kept; a host whose
  begin marker ends in CRLF gets a CRLF interior, a difference in line endings
  alone is no change, and a byte-order mark an editor adds is kept;
- a file with no canon region is refused with the two marker lines to add, and
  a missing file is created only with `--create`, holding an empty region;
- a file the host would truncate is refused before writing. For Codex the
  limit is `project_doc_max_bytes` from `config.toml` under `CODEX_HOME` when
  that is set, else under `~/.codex` in `--home`, 32,768 by default, and the
  refusal names the setting and where it was read, and a nested `AGENTS.md` the combined chain from the root
  would cut is named in a warning. A file past a host's line guidance writes
  with a warning;
- Codex reads `AGENTS.override.md` instead of `AGENTS.md` in the same folder,
  so a switch to codex with an override present is refused (`shadowed`);
- `--dry-run` plans and prints the region without writing;
- the file is read again just before the write, and the write is refused if it
  changed since the plan read it;
- a file canon cannot read as UTF-8, or a folder that is a file, ends with a
  named failure code (`conflict`, `unsafe_path` or `io_error`), never a
  traceback.

The drift check and the reconcile writer know the brief block: a switched
surface reads as a match, and a reconcile carries the brief through instead of
erasing it.

A target with no instruction surface (`markdown`) prints the brief alone. It
carries no instruction block, and the receipt says so for each one. The
command says it too: `handoff` prints the count and the reason on stderr
beside a printed brief and on its result line beside a written one, `switch`
adds it to its warnings, and both carry `omitted_blocks` (count, ids, reason)
in `--json`.

## Targets and declared downgrades

W1 adds three surfaces to the write allow-list, each by exact path:

| harness | file | why this path |
|---|---|---|
| `gemini-cli` | `GEMINI.md` | Gemini CLI loads a project-root `GEMINI.md` (its global file is not on the list yet) |
| `copilot` | `.github/copilot-instructions.md` | Copilot's repository-wide instructions file; plain Markdown |
| `cursor` | `.cursor/rules/canon.mdc` | one canon-owned rule; canon writes no other file under `.cursor/rules` |

Each is a lone workspace surface, so it renders the full merged block set, the
same rule `AGENTS.md` follows. `canon switch --create` makes the Cursor rule
with YAML frontmatter (`alwaysApply: true`), because Cursor loads a rule on
every request only with that setting.

A personality block may carry `applies_to`, a list of glob patterns naming the
files it is meant for. No surface on the allow-list can load one block for some
files and not others, so each target declares what it does instead:

| feature | targets | what happens |
|---|---|---|
| `activation.glob` | all five | the block is written always-on; the patterns stay in the block's sentinel and reach the model as an `Applies to:` line, which is advice rather than a rule |
| `text.at-import` | `claude-code`, `gemini-cli`, `cursor` | an `@path` token after a space or at a line start, outside a code span, bare names included (`@README`), is read by the host as a file import or as context, so the same text means more there than in `AGENTS.md`; in the brief canon writes for these hosts every such token is put in a code span, which they read as text |
| `instruction.omitted` | `markdown` | the pasted brief has no instruction file to carry blocks, so none is included |

`canon.workspace.target_fidelity.target_roundtrip` renders a block set into a
new host file for a target, runs the R0 round-trip verdict on it, checks the
host's own requirement (the Cursor frontmatter), and classifies every feature a
block asked for that the target handles differently. A difference the target
did not declare fails the verdict. `canon switch` lists each difference as a
warning, and `canon workspace targets` prints the table.

### Region grammar v1

The scope rides in the region grammar as an optional `applies` attribute on
the block sentinel, the authoritative copy, followed by a generated
`Applies to:` line:

```
<!-- canon:block id="react" applies="src/**/*.tsx|src/**/*.ts" -->
## React rules
Applies to: src/**/*.tsx, src/**/*.ts
Use function components and hooks.
```

On ingest the line must match the attribute and is removed; an edited line is a
refusal. A pattern may not contain `"`, `<`, `>` or `|`. A region with no
scoped block is byte-identical to the v0 grammar, and a block's source hash
changes only when it has a scope. The `textblock-grammar` pin moves to
`canon.textblock/v1`.

## Edits made inside a rendered region

Agents and people edit instruction files. When they edit inside canon's region,
the next `switch` must not overwrite that work, and it must not guess what the
edit meant either.

`switch` records the interior it wrote in the project's render ledger
(`projects/<id>/renders.json`, a `canon.render-ledger/v1` object). A project can
have several checkouts, each with its own file, so the last render is kept per
checkout, keyed by a path-clean digest of the checkout root and the surface's
relative path. The ledger also keeps the last 16 interiors canon wrote to each
surface from any checkout, which blocks each render owned (this project, a
declared project, or `global`), and a render number. The file write and the
ledger entry happen under one project lock, so a held lock refuses before
anything is written. Before the next write `switch` compares the region on disk
with what canon wrote:

- equal to any remembered render, or empty: the file is canon's own, possibly
  stale (one render behind another checkout, or restored by a branch switch);
  the switch overwrites it.
- otherwise: the region was edited in place. It is read against the closest of
  this checkout's last render and the remembered renders. Each edit becomes a
  proposed record, and the switch refuses with `edits_pending` until every
  proposal is accepted or rejected. After that the switch writes, carrying the
  accepted edits and dropping the rejected ones.

What an edit becomes:

| edit | proposal |
|---|---|
| a block's title, body or scope changed | the same block with the new content |
| a new block | a new personality block |
| a block removed | the block, retired (`valid_until` set) |
| a block of another project or of global edited or removed | the memory note, naming the owner; never a record under this project |
| a block's sentinel `ord` or `sup` changed | the memory note |
| `Goal:` changed in the brief | the focus with the new goal, other fields kept |
| a work or constraint line changed | that record, with only the fields that differ from the rendered line |
| a new work line, or a new constraint line | a new work item or constraint |
| a work line removed | that work item with status `dropped` |
| a constraint line removed | that constraint, retired |
| the brief heading changed | the memory note |
| any other added line | the memory note, as written |
| any other removed line (a goal, a decision, a detail) | the memory note, as `removed: <line>` |
| an edit that broke the region grammar | one memory record holding the changed lines |

The memory note is one proposed memory record per read. A mark is read
loosely (`[x]` and `[Done]` mean done), trailing spaces are ignored, and a line
that still names an id is never read as removing it. Lines labelled `[global]`
or `[from <project>]` belong to another scope and are kept as text rather than
mapped. With no ledger entry for this checkout the region is compared with the
closest remembered render, or with what canon would write now, and only
additions and changes count, since an absent block says nothing when canon
never put it there. Every proposal is scrubbed like an import, carries an origin
naming the surface, the file digest, the line, the rule, the render number it
was read against and the digest of the accepted record it was built from, and
keeps an existing record's ordinal. It is skipped when the same content was
already accepted, or rejected against the same render; once a later render
stands, the same edit made again is proposed again, and `switch` names the
rejected edits it overwrites. `canon workspace pull --from <target>` runs the
same read without switching.

## Importers

`canon workspace import --from claude-code|codex <file>` reads one session file
another tool wrote and proposes records from it. It never writes an accepted
record: every result is a proposed row that `canon workspace accept <id>` or
`canon workspace reject <id> --reason <text>` settles, and nothing renders
until it is accepted.

### Formats

| source | file | what is read | confirmed against |
|---|---|---|---|
| Claude Code | a session `.jsonl` | `user` and `assistant` entries (`message.content` as text or blocks) on the live branch (`uuid`, `parentUuid`, `logicalParentUuid`), a `summary` whose `leafUuid` names an entry of the file, an `ai-title` with this file's `sessionId`, `sessionId`, `cwd`, `gitBranch`, `TodoWrite` inputs, the `TaskCreate`/`TaskUpdate` task list (numbers bound from "Task #N created successfully"), `Edit`/`Write`/`MultiEdit`/`NotebookEdit` file paths | two public parsers of the format and Anthropic's note that the format is internal and changes between versions |
| Codex CLI | a rollout `.jsonl` (Codex 0.32 or later) | `session_meta` (the thread `id`, which wins over the root `session_id` a sub-agent shares, cwd, `git.repository_url`, `git.branch`), `turn_context` cwd, `response_item` messages (`input_text`, `output_text`), `update_plan` calls, file names in `apply_patch` resolved against the session cwd, `event_msg` `thread_rolled_back` | the openai/codex source |

Both formats were read from public sources on 2026-09-23, and the test fixtures
in `tests/fixtures/transcripts/` follow them. Neither is a stable public
interface. A Codex rollout from before 0.32, where lines are bare items, is
refused as `unsupported_format`.

### Extraction rules

Fixed patterns, not a model, so the same file always gives the same proposals:

| rule | reads | proposes |
|---|---|---|
| `plan-tool` | the last `TodoWrite` call or the task list `TaskCreate`/`TaskUpdate` built (Claude Code), or the last `update_plan` call (Codex) | a work item per pending or in-progress step |
| `todo-marker` | `TODO: ...` or an unchecked `- [ ] ...` in a message | an open work item |
| `decision-phrase` | "we decided to X (because Y)", "we went with X" | a decision with status `proposed` |
| `failed-phrase` | "I tried X but Y", "X did not work (because Y)" | a decision with status `rejected` and X as a rejected alternative with Y as its reason |
| `session-summary` | Claude Code's own summary line, else its own `ai-title` | the focus goal |
| `first-prompt` | the first line of the first user prompt, when there is no summary | the focus goal |

The focus proposal carries the session's branch and up to ten edited files as
areas, as paths inside the project; an edited path outside the project, or
inside a nested repository under it, is dropped and counted.

User-role text the host wrote itself is never mined. For Claude Code that is a
slash command and its local output, bash-mode input and output, a compaction
summary (`isCompactSummary`, or text that opens with "This session is being
continued"), and `system-reminder`, `ide_selection` and `ide_opened_file`
blocks inside a message, which are cut out before the rules run. For Codex it
is every marker in `contextual_user_message.rs` that has a marker string:
environment context, user instructions, `AGENTS.md` instructions, a user shell
command and its output (counted as tool output), a skill, a sub-agent notice,
an aborted-turn notice, and internal or goal context. Codex's hook prompt
fragment has no marker canon knows; it is not dropped (an honest gap).

A Codex `thread_rolled_back {num_turns}` discards every candidate, plan and
edit gathered since the start of the last `num_turns` user turns. A Claude Code
branch the person rewound away from is not mined: the live branch runs from the
last main-thread entry back to the root, and an entry off it is dropped when
its branch starts with a typed prompt. A branch that starts with a tool result
is kept, so a fork the tool machinery makes is never taken for a rewind.

A proposal id digests the importer, the session (the Codex thread id), the
line, the rule and an index. When an accepted record already holds that id
and came from another source file, the id is minted again with the file name
in its key, so two files that share a session id never replace each other.
A session id that is not an id shape, or looks like a secret, is dropped and
counted instead of stored.

### Declared loss

Each importer names every category of content it drops, and the report counts
every one, including the zero counts. Common categories: text that matched no
rule, a repeated candidate, plan calls before the last, completed plan steps,
paths outside the project, a truncated last line, a candidate that failed
validation, images, tool calls and tool output, and a session id that is not
an id. Claude Code adds thinking blocks, sidechain entries, `isMeta` messages,
message metadata, the entry types that carry no conversation (among them
`agent-setting` and `pr-link`), local commands, compaction summaries, injected
blocks, abandoned branches, and summaries that describe another session or
were replaced. Codex adds session state (including a `configuration_update`
item), `event_msg` lines other than a rollback, reasoning, the user-role text
Codex writes itself, developer and system messages, rolled-back candidates, and
the response items it does not read (including `compaction_summary` and
`ghost_snapshot` from older rollouts).

Content no category covers (an entry type, content block or message role the
importer has not seen) is an undeclared loss and refuses the import with
`undeclared_loss`, naming the label and the lines and printing the flag to add.
`--drop-type <label>` declares that drop for one run; the bare type name
(`--drop-type brand-new-entry` for `entry type 'brand-new-entry'`) works too,
and the report lists it under the drops the person declared. A malformed last
line with no newline after it is a declared truncation; a malformed line that
ends in a newline, anywhere in the file, is corruption and refuses the import.

### Secrets

Every source string an importer reads (message text, plan steps, the session
summary) passes through `canon.workspace.scrub` whole, before any extraction
rule sees it, so a 200-character capture cap or a line break cannot cut a
secret below the length its rule needs. Every candidate is scrubbed again after
extraction. The rules (`scrub_rules.py`) redact provider key formats
(Anthropic, OpenAI, GitHub, GitLab, Slack, AWS, Google, Stripe, Hugging Face,
npm, PyPI, DigitalOcean, Shopify, SendGrid, Twilio, Telegram), with short
minimum lengths after the prefix so a cut token is still caught; JSON web
tokens; PEM, PGP and PuTTY private keys; Slack and Discord webhook URLs;
bearer, basic, token and API-key headers whose value, on the header's own
line, is not a setting (a number, a date, a path) or a lower-case or
capitalised word of fewer than twenty letters (`bearer authentication`,
`X-API-Key: required`), and cookies; the password of any
`user:password@` in a URL unless it is a placeholder (a port followed by a
path, a query, a fragment or the end is not a password), and a user part with
no password when, with its percent escapes decoded, it holds a random run (a
run of eight or more letters and digits that is not a word followed by a
number or a number followed by up to two letters); a URL query parameter
whose name has a key, token, secret, pass, password, credential, auth, sig or
code segment, whose value ends at the next `&` or `#`; Azure account
keys and `.npmrc` tokens; JSON fields named like a secret, also inside escaped
JSON; password fields in any case after `=` or `:` (`db_password=`,
`password: x`, `password = "x"`); and assignments whose name has a key, token,
secret, pass, password or credential segment, in any case
(`aws_secret_access_key = ...`, `DB_PASS=`). A name-based value must be at
least four characters, and one that reads as code (a call, an index, an
attribute, a dotted name, a type name such as `string`) or as a placeholder
(`<...>`, `${VAR}`, an all-caps `$VAR`, `%VAR%`, `{{...}}`) is left alone; a
placeholder has to be the whole value, so `$2b$12$...` or a value that joins an
earlier redaction to more text is still redacted. The rest is decided by the
value's shape (`scrub_shape.py`). A number of at most 19 digits, a date or
time, a path, or a boolean is a setting after any name (`KEY_COUNT=1000`,
`second pass: 2026-10-01`, `private_key_path: ~/.ssh/id_ed25519`); a path
segment that holds a random run, or is sixteen or more base64 characters
mixing both cases, is not a path. After a name that holds a
password or a token, a path also needs two segments (`DB_PASSWORD=/hunter2`
is a password) and must not be base64-shaped (only letters, digits, `+`, `/`
and `=`, with upper case, lower case and a digit). The last secret word in
the name decides its class. A name holds a password when that word is a
password word and each word after it names which password (`DB_PASSWORD`,
`DB_PASSWORD_PROD`, `ADMIN_PASSWORD_2`, `password_confirmation`); any value
that is not a setting is a secret there. A word that describes the password
(`type`, `path`, `min`, `policy`, `url`, `hint` and the rest of
`scrub_shape._DESCRIPTORS`) makes the name a description instead. A name
holds a token when it ends in another credential word, or in `key` after a
word such as `api`, `access` or `secret`; a word of up to ten letters is a
setting there (`token: bearer`) and anything else is a secret. After any
other name (`token_type`, `GITHUB_TOKEN_CI`, `PASSWORD_MIN_LENGTH`,
`KEY_PREFIX`, a bare `key` or `auth`, `MONKEY`) the value must look random:
twelve or more characters with no space that hold a random run, or mix both
cases with `+`, `/` or `=`. An AWS resource name (`arn:...`) is a setting
after any name, like a number. A cookie header is a secret when one of its
values is, a command-line flag (`--api-token=...`) is an assignment, and a
URL query parameter and a JSON field take the same name and shape rules. A
one-word name followed by a colon
inside a sentence ("Refresh token: handle expiry") is prose unless its value
has a digit, a symbol or twelve letters. Each match becomes
`[REDACTED:<rule>]`. The report counts the hits by rule; it never stores the
value or a digest of it. Every rule runs in time linear in its input, so a long
or hostile line cannot stall an import or a store write. Two more checks sit
behind the scrubber: the store refuses any record that still matches
(`secret_quarantine`), and a brief or an instruction region that would carry a
match is refused before it is written. The control test plants a canary for
each rule in both fixtures and asserts none reaches the store files, the
reports, the brief or the region; with all three checks removed the same test
finds the canaries.

### Project check

A Codex rollout names its repository in `git.repository_url`; a Claude Code
session names its working directory in `cwd`. A working directory is first
resolved to the checkout it sits in: the nearest directory with a `.git` entry,
or this project's root when it is inside a project folder with no `.git`. A
checkout of this project's own repository (its root, or a sibling worktree
that shares its git directory) is this project, under a `--remote` override
too. A repository URL is compared with this project's key, except that a URL
naming this checkout's own remote, under an override that names another
repository, defers to the working directory check: Codex records the
checkout's own origin, so a rollout at the root of a fork imported with
`--remote <upstream>` matches as a Claude Code session there does. Any other
checkout is compared by project identity, not by path prefix,
so a nested repository or a submodule inside this checkout is another project.
That identity is derived without the override and without writing a nonce
into it; a directory that no longer exists falls back to containment, with a
`.git` entry between it and the root counting as another project. When
the source names a different project than the one being imported into, the
import is refused with `isolation_refused` unless `--accept-foreign-source` is
given, and the report records the check either way. A source that names
neither is recorded as `unverified`.

### Provenance

A proposed record carries `harness` (`claude-code` or `codex`), `source_hash`
(the sha256 of the source line), `native_id` (`<importer>:<file name>:<line>`)
and the session id. Its row's `origin` names the importer, the file name, the
file's sha256, the line, the rule and a hash of the proposed content. Ids are
derived from the session, line and rule, so importing the same file again
proposes the same ids; a proposal already accepted with the same content, or
rejected before, is reported and not proposed again. The report is a
`canon.import-report/v1` object.

## The store

The store root defaults to `~/.canon/store` and can be set with `CANON_STORE`
or `--store`. It sits outside the repository so a commit never carries it by
accident.

```
projects/<project_id>/records.jsonl    accepted rows
projects/<project_id>/proposed.jsonl   proposed rows awaiting a decision
projects/<project_id>/log.jsonl        every write, decision, promotion, adoption
projects/<project_id>/project.json     the path-clean identity
projects/<project_id>/renders.json     what switch last wrote to each surface
global/records.jsonl                   rows promoted to global scope
global/log.jsonl                       every promotion into global
```

Each line of a row file is a `canon.project-row/v1` object:

```
{"schema": "canon.project-row/v1", "project_id": "prj_...", "state": "accepted",
 "record": { ...the record, unchanged... },
 "origin": null, "promoted_from": null}
```

The record inside is the F0 envelope byte for byte, with its own schema tag. The binding to a project
lives in the row, so every existing reader of a record keeps working, and a row
copied into another project's file still names the project it came from.

Rows are written sorted by `(scope, id)` through a temporary file and a rename,
under the run lock for the project, so the same row set always produces the
same bytes and two writers cannot interleave.

## Isolation

- Every new record is a `workspace` record of the store's project. `put`
  refuses a `global` record.
- Reading a row file refuses the whole file when any row names another project.
  A misfiled row is corruption, so it is reported and never filtered away.
- A render or a brief reads the pool from `canon.workspace.pool`: global rows,
  the project's own accepted rows, and the accepted rows of each other project
  the caller names in `include_projects`. Every record in the pool carries the
  project it came from. A proposed row is never in a pool.
- When a named project carries a personality block with the same scope and id
  as this project's block, the pool refuses, because layering would otherwise
  let one silently override the other.
- `canon workspace promote <id> --reason <text>` is the only path into global
  scope. It moves the record out of the project file, writes it to the global
  file with `promoted_from` set, and logs the move in both logs. It refuses,
  writing nothing, when global already holds a record with that id, because
  ids are per-project ordinals and two projects meet on `constraint-1`. The
  ordinal of a promoted record is never issued again in its project.
- `accept` refuses a proposal whose accepted record changed after the proposal
  was made (the proposal's origin carries `base_record_sha256`), so a later
  `set-status` or a second accepted edit is not erased. `--force` accepts it
  anyway.

The contamination controls in `tests/test_workspace_store.py` write a phrase
into project A and assert it never reaches project B's render or pool, that a
row of A copied into B's file makes B's read fail, and that A becomes readable
from B only when named. Each control was checked by removing the rule it
protects and watching the test fail.

## Commands

```bash
canon workspace id                      # this project's identity and record counts
canon workspace list [--proposed]       # this project's records
canon workspace focus --goal "Ship the handoff" --area src/canon/workspace
canon workspace task "Write the Codex importer" [--status in-progress]
canon workspace set-status task-4 done
canon workspace decide --title "Row format" --decision "JSONL rows" \
    --context "Stores must diff in review" --reject SQLite "binary diffs"
canon workspace constraint "CI runs on Windows and Linux" --quirk
canon workspace promote <id> --reason "applies to every project"
canon workspace adopt --from <prj_id> --reason "moved the checkout"
canon workspace import --from codex rollout.jsonl [--dry-run] [--drop-type LABEL]
canon workspace accept <id> [--force] | reject <id> --reason "not a real task"
canon handoff --to codex [--receipt brief.receipt.json] [--out BRIEF.md]
canon switch --to claude-code [--dry-run] [--create]
canon workspace targets                  # files, budgets and declared downgrades
canon workspace pull --from claude-code [--dry-run]   # edits in a region -> proposals
```

Every command takes `--workspace` (default `.`), `--store`, and `--remote` to
override the remote used for the identity. `--json` gives the machine-readable
result.

## Limits

- The git config reader follows `commondir` and `gitdir`, not `include`
  directives or `insteadOf` rewrites.
- The store trusts the local filesystem. A process that can write the store can
  write any project's rows; isolation protects against mixing, not against a
  hostile local user.
- The log records wall-clock time as a convenience. Ordering inside the store
  uses the clock-free `create_ord`, and no render reads the log.
