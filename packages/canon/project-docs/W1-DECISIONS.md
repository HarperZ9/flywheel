# W1-DECISIONS: the workspace backend

Decisions continue the repository numbering; M4 ended at D-100.

## D-101 The project binding lives in the stored row, not in the record

A record could carry its project in `data`, in `provenance`, or in a new
envelope field. Each of those changes a record that other readers already
parse: a personality block with an extra `data` key is refused by the text
renderer, a new provenance field changes every serialized record and every hash
over one, and a new envelope field is a `canon.record/v2`.

The binding goes one level up instead. The store keeps a `canon.project-row/v1`
row around the unchanged record, and the row names the project. A row copied
into another project's file still names where it came from, which is what lets
the read side refuse it.

## D-102 The identity comes from the remote, and a doubt splits rather than merges

A project with a remote is keyed on the normalized remote URL, so two clones,
two worktrees and a moved checkout are one project. The normalization drops
what does not name the repository (scheme, credentials, port, query, `.git`)
and lowercases the host, which DNS already treats as case-insensitive. It keeps
the path as written. Some hosts treat repository paths as case-sensitive, and a
wrong guess in the merging direction would show one project's records to
another, while a wrong guess in the splitting direction only hides records until
someone adopts them. Credentials are dropped before the key is formed, so no
token in a remote URL can reach a receipt.

A project with no remote is keyed on its resolved root path. A remote that is
itself a local path is digested, so the key never carries a local path.

## D-103 A `.git` in the home directory or a filesystem root claims only itself

The upward search for `.git` matches what git does, and git would place every
directory under a home-directory dotfiles repository inside that repository.
For canon that turns every unversioned project under the home directory into
one project, the exact mixing this band exists to stop. A `.git` found in a
ceiling directory therefore counts only when the workspace is that directory.
The test for it carries its own control: without the ceiling the same two
projects resolve to the dotfiles remote.

## D-104 Isolation is checked on read, and a misfiled row fails the whole file

Directory layout alone does not isolate projects: a copied file, a bad merge or
a bug in a writer can put a row where it does not belong. Reading a row file
therefore checks every row's `project_id` against the file's project and refuses
the file when one does not match. Filtering the stray row out would hide the
corruption and leave the next reader to trip on it, so the read fails and names
the foreign project.

## D-105 Another project is readable only when named, and never merged by id

A brief or a render may include another project's records when the caller names
that project. The pool then tags every record with its project, and the brief
labels them. When a named project carries a personality block with the same
scope and id as one of this project's blocks, the pool refuses, because the
layering rule (a later record with the same id wins) would otherwise let one
project override the other without anyone choosing it.

## D-106 New records are workspace records; global is reached by promotion only

`put` refuses a record in `global` scope. `promote` moves an accepted record
from a project to the global file, sets `promoted_from`, and writes a log entry
with the reason in both the project log and the global log. A record that every
project reads is one somebody chose to make global, and the log says who asked
for it and why.

## D-107 The store lives outside the repository by default

The default root is `~/.canon/store`, overridable with `CANON_STORE` or
`--store`. Inside the repository a store would ride along with a careless
commit, and the global file has no single repository to live in. A developer
who wants the state versioned with the code can point `--store` into the
repository and accept that trade.

## D-108 Adoption is the explicit answer to a rename

Renaming a remote or moving a repository with no remote changes the id, and the
old records stop appearing. Guessing that two ids are one project would be the
merge D-102 refuses to make. `adopt` copies another project's accepted records
into this project when a person names the old id and a reason, refuses before
writing when any record would overwrite one this project holds, and logs each
adopted record with its source project.

## D-109 The workspace-state kinds carry their own schema tag

Adding three kinds to the `canon.record/v1` vocabulary would have changed what
a v1 reader must accept: a 0.2.0 reader would meet `work-item` and report an
unknown kind. Bumping every record to a `canon.record/v2` would have changed
the bytes of every existing record, every vault note that carries one, and
every hash over them.

The new kinds instead share the envelope and carry their own tag,
`canon.workspace-state/v1`, pinned as the `workspace-state` seam.
`schema_tag_for(kind)` chooses the tag and `Record.from_dict` refuses a
mismatch in either direction. A record of the five F0 kinds keeps its tag and
its bytes, which the fixture test checks; an old reader refuses a
workspace-state record by its tag instead of misreading it. `KINDS` stays the v1
vocabulary and `ALL_KINDS` is what the validator admits.

## D-110 Rejected alternatives are an additive field on the decision record

A decision's rejected alternatives are the part a new tool most needs and the
part no session format records as data. They are a list of `{option, reason}`
objects on `adr-decision`, optional and validated only when present. An
alternative without its reason is refused, because an option with no reason
is the thing a later tool retries. The field is additive, so the decision
record keeps `canon.record/v1`: an old decision stays valid and an old reader
ignores the field.

## D-111 The storage adapters keep holding the five v1 kinds

The files, SQLite, mneme and flywheel adapters declare `KINDS` as what they
hold, and their round-trip proofs are written against it. The workspace-state
kinds live in the per-project store (D-101), so the adapters are unchanged and a
workspace-state record offered to one is refused as an unsupported kind rather
than stored under a contract that was never proved for it.

## D-112 The pin type moves to `versions_pin.py`

`versions.py` was already over the 300-line gate before W1 added three pins.
The error classes, the closed `SEAM_PINS` vocabulary and `SchemaPin` moved to
`versions_pin.py`, which imports nothing from canon, and `versions.py`
re-exports every name, so no caller changes an import.

## D-113 The brief is a strict prefix of the priority order, with a report

A brief that fits its budget by dropping whatever is largest would show a
constraint while hiding the current focus. The brief is built in priority order
(focus, open work, recent decisions, constraints) and cut at one point: every
record after the cut is left out whole and named in a `Left out` section and in
the receipt. No record is shortened, because a half decision reads as a whole
one. The receipt pins the budget, the brief's digest and a digest of the pool,
so the same records give the same brief, and a reader can tell what was cut
from what never existed.

## D-114 The brief rides in the instruction region as one reserved block

The point of a handoff is that the next agent reads it without being told to.
Every target already loads its instruction file at startup, so `switch` puts
the brief there, as one personality block with the reserved id
`canon-workspace-brief`, after the project's own blocks. The region grammar
carries it unchanged, so the region still round-trips through the R0 codec, and
a stored block that tries to use the reserved id is refused.

## D-115 Budgets come from the host's documentation, with a margin

Each target's numbers were read from the host's own documentation or source and
labelled with a confidence. Where the host truncates (Codex), `switch` refuses a
file past the limit, because a truncated instruction file loses its tail without
telling anyone. Where the host only advises (Claude Code, Cursor, Copilot), the
write goes ahead with a warning. The brief budgets sit well inside those
figures so the personality blocks that share the file still fit, and every
budget can be overridden on the command line.

## D-116 `--create` makes a missing file, never an existing one

The rule that a file is opted in by its owner adding the markers still holds.
`switch --create` writes a new file only when none exists, holding an empty
canon region; an existing file without a region is refused and left as it is.

## D-117 An importer proposes; a person accepts

A transcript is evidence of what was said, not a record of what was decided. A
pattern that reads "we decided to X" cannot tell a decision from a quoted
option or a joke. Every imported record is therefore a proposed row with an
origin naming the file, its digest, the line and the rule, and nothing renders
it until someone accepts it. A rejection is logged with a hash of the proposed
content, so re-importing the same file does not offer the same proposal again.

## D-118 Declared loss at the import boundary refuses what it cannot name

The R0 gate fails a round-trip on a loss nobody declared. The importers apply
the same rule at the boundary where content enters canon: each names every
category it drops, counts each one, and refuses when it meets content no
category covers. Both session formats change without notice, so the refusal is
the signal that the importer needs updating. `--drop-type` lets a person
declare the drop for one run, and the report says it was the person who
declared it.

## D-119 Scrub before storing, and check again at the store and at the render

A transcript holds whatever passed through the terminal. The scrubber runs on
every string before it becomes a record, and replaces a match with a marker
naming the rule. It stores no value and no digest of one, since a digest of a
short password can be reversed by guessing. The store refuses a record that
still matches, which also covers a secret typed by hand, and the brief and the
instruction region are checked once more, which covers a store file edited by
hand. The scrubber is pattern-based and documented as such: a secret with no
recognisable shape passes.

## D-120 The source must name this project, or the person must say otherwise

An import is the easiest place to mix projects: a rollout from one repository
imported while standing in another. When the source names a repository or a
working directory that is not this project, the import refuses unless
`--accept-foreign-source` is given, and the report records the check.

## D-121 Fixtures follow the public formats and plant canaries at run time

The owner's own session files are not read. The fixtures were written from the
formats as public sources describe them on 2026-09-23 (the openai/codex source
for rollouts, two public parsers for Claude Code sessions), with placeholders
for the project root and for secrets. The tests build each planted value at run
time, so no committed file carries a string a secret scanner would flag.

## D-122 A block's scope rides in the sentinel and is shown as a line

Cursor, Copilot and Continue can scope a rule to matching files; the plain
instruction files cannot. A block's `applies_to` is carried in the region
grammar as an `applies` attribute on the sentinel, which round-trips exactly,
and shown to the model as a generated `Applies to:` line, so the scope is not
lost on a host that loads everything. Ingest checks the line against the
attribute and removes it; a hand-edited line is refused rather than read as
body text. The grammar change is additive but an older reader refuses the new
attribute, so the `textblock-grammar` pin moves to v1. Unscoped blocks render
and hash exactly as before.

## D-123 Each new surface is one exact path, chosen for how its host loads it

The allow-list stays a list of exact paths. `GEMINI.md` at the workspace root
is what Gemini CLI loads for a project; the global `~/.gemini/GEMINI.md` is left
for a later change, like the global `SOUL.md`. For Copilot the surface is the
repository-wide `.github/copilot-instructions.md`; the path-specific
`.github/instructions/*.instructions.md` files are not on the list. For Cursor
canon owns one rule, `.cursor/rules/canon.mdc`, and no other file in that
directory, so a team's own rules are never canon's to write.

## D-124 A target declares what it cannot express, and the verdict holds it to that

The storage adapters declare their drops in advance and the round-trip gate
fails on anything undeclared. The render targets follow the same rule for host
semantics. Each target names the features it handles differently
(`activation.glob` everywhere, `text.at-import` on Claude Code and Gemini CLI)
and what it does instead. `target_roundtrip` classifies every such feature a
block asks for; an undeclared one fails the verdict, and the test that removes
the declaration watches it fail.

## D-125 `write_surfaces` reports a missing file instead of failing

With seven surfaces, most projects will lack some of the files. The batch
writer already skipped a file with no region; it now also reports a file that
does not exist as `missing` and never creates it, the same verdict the drift
check gives. Creating a file is `switch --create`'s job, for one named target.

## D-126 switch records what it wrote, so a stale file and an edit differ

V4 decided drift against what is on disk with no recorded base (D-51), which
suits a region only canon writes. A region an agent is invited to edit needs to
tell canon's own stale render apart from an edit, because only the first is
safe to overwrite. `switch` therefore records the interior it wrote per
surface, with a digest, in the project's render ledger. A ledger entry whose
digest fails is refused rather than trusted.

## D-127 An in-place edit becomes a proposal, and switch waits for the decision

Overwriting an edit loses work; applying it automatically lets any tool that
can write the file change the project's records. Each edit is read back into
the record it most plausibly means, by a fixed rule per line shape, and written
as a proposal; a line that fits no rule is kept verbatim as a memory proposal
instead of being guessed at. `switch` refuses while any proposal from the
region is undecided, and proceeds once each is accepted or rejected. Without a
ledger entry only additions and changes count, so the first switch into a file
never proposes to retire blocks canon did not write.

## D-128 Findings from the branch review, folded in

An independent review of the band found three gaps and one tradeoff:

- A removed brief line labelled `[from <project>]` was mapped by id alone, so
  deleting another project's `task-3` could propose dropping this project's
  `task-3`. Removed lines with a scope label are now skipped, as added ones
  already were; a test pins it.
- The filesystem-root ceiling (D-103) was computed from the home directory, so
  it vanished where the home directory cannot be resolved. It is now taken from
  the workspace's own anchor as well, and a test removes the home directory.
- `switch` wrote the plan's text without looking at the file again, so an edit
  made between planning and writing was lost. The commit now re-reads the file
  and refuses when it changed (or appeared, for a create). The window between
  that read and the write remains and is disclosed.
- The name-based secret rules redacted any value after a secret-named key,
  including `RETRY_TOKEN_COUNT=5`. They now need a value of at least four
  characters. A secret shorter than that after such a key is not redacted; the
  provider-format rules are unaffected.

## D-129 promote refuses a clash, and accept refuses a stale base

Record ids are per-project ordinals, so project A's `constraint-1` and project
B's `constraint-1` are different records with one id. `promote` used to replace
any global row with the same id, and since the promoted record has already left
its project file, the record another project put there survived nowhere. It now
refuses before writing, the same rule `adopt` follows. `next_ord` also counts
the records a project promoted, so the next `workspace task` never reissues a
promoted id and a second promotion cannot meet the first.

A proposal is a snapshot. Accepting it replaced the accepted record whole, so a
`set-status` run between the proposal and the accept was erased with no
warning. Each proposal now records the digest of the accepted record it was
built from (null when there was none), and `accept` refuses with `conflict`
when the current accepted record differs. `--force` accepts anyway, for the
person who compared the two. The store's secret check now covers the whole row,
provenance included, because an importer copies a session id from the source
verbatim.

## D-130 A non-default port splits, a nonce keys a local repository, and a new checkout is announced

D-102 says a doubt splits. Dropping every port merged two servers on one host
(a staging and a production forge) into one project, so a port now stays in
the key unless it is the scheme's default.

Two merges were silent. A repository with no remote was keyed on its path, so
one deleted and re-created at the same path inherited the old records, and two
apps cloned from one starter keep its remote and share an id. canon now writes a
random nonce once into the shared git directory of a repository with no remote
and keys on that; it moves with `.git`, which also removes the old "moving it
changes its id" limit. For the starter case the rules cannot tell a second clone
of the same project from an unrelated repository, so the store records a
path-clean digest of each checkout root and a command from a new root prints a
notice. `git config canon.project <name>` names a project explicitly and wins
over the remote, so a split survives every command without a flag. Writing the
nonce is the one place identity derivation writes a file; a git directory canon
cannot write falls back to the path key.

## D-131 The scrubber covers the everyday forms, runs before extraction, and anchors placeholders

The first rule set named its categories correctly and missed their everyday
spellings: `db_password=`, `password: x` in YAML, a quoted password, a
lower-case `aws_secret_access_key` from `~/.aws/credentials`, `DB_PASS=`, a PGP
key block, a URL password holding `/`, a token as a URL's user, escaped JSON.
Common carriers had no rule at all (basic auth, cookies, URL query tokens,
Azure keys, PyPI tokens, webhooks, `.npmrc`). An end-to-end run found each one
in the store and in all five rendered files. The rules now cover those forms,
and a new test runs every form through import, accept and switch and asserts
on the rendered files.

A broader name rule risks redacting code. The name-based rules therefore skip
a value that reads as code or as a type name, and a name whose only secret
segment is `key` or `auth` needs a value that looks random. A false positive
here is a redaction, which loses a word; a false negative publishes a secret,
so where the two conflict the rule redacts.

Scrubbing ran on the captured fragment, so a 200-character cap or a line break
could cut a token below its rule's minimum and store most of it. Each source
string is now scrubbed whole before extraction, and the prefix rules take short
minimums so a cut token is still caught. A placeholder test that matched a
prefix skipped `$2b$12$...` and a value that joined an earlier redaction to
more text; placeholders are now matched against the whole value.

## D-132 The importers read the host's own text as the host's, and compare projects by identity

Both hosts put text in the user role that the person never typed: Claude Code's
slash commands, local command output, bash-mode output and compaction
summaries, and Codex's shell command output, skills and sub-agent notices. The
importers mined it as typed text, so a `cat NOTES.md` became a decision. Each
now drops that text by its marker under a named category. A rolled-back Codex
turn and a rewound Claude Code branch are dropped the same way, and a Claude
Code summary is used only when it describes this file, since a summary line
routinely describes another session. The Claude Code task tools that replaced
TodoWrite are read as the plan.

The project check compared paths, so a session from a nested repository passed
as this project and a session from a sibling worktree was refused. It now
compares project identities, derived without writing anything into the other
repository. A Codex sub-agent's rollout shares the root's `session_id`, so ids
now key on the thread id, and an accepted record from another file is never
replaced by a new proposal with the same id.

A malformed last line was always read as a truncation. A writer appends a line
and its newline together, so only an unterminated last line is a truncation;
a malformed line that ends in a newline is corruption and refuses.

## D-133 Back-flow reads a checkout against its own render and keeps every edit

The ledger kept one render per project and surface, but worktrees and clones
share a project id and each has its own file, so one checkout read another's
newer render as its base and proposed dropping live work. The last render is
now kept per checkout, and a region equal to any render canon remembers writing
to the surface is stale, whichever checkout wrote it or whichever branch
restored it. An empty region has no base, so opting a file in never proposes a
retirement. A file is written and its ledger entry recorded under one lock, so
a held lock can no longer leave a written file with an old ledger entry.

An edited line was mapped whole, so a title edit also carried the status the
file showed, and reverted a newer status set elsewhere. Each line is now paired
with the line canon rendered for the same id, and only the changed fields are
proposed. A tick written `[x]` or `[Done]`, or a trailing space, used to read as
a removal; a line that still names an id never does now. Removed constraint,
decision, goal and detail lines, a changed brief heading and a changed sentinel
ordinal were silently overwritten; each is now proposed or kept in the note.
A rejection was remembered by content forever, so a later real edit with the
same content was discarded; it is now tied to the render it was made against.

An edit of a block another project or global owns was proposed as this
project's record, and accepting it blocked every later `--include-project`
switch. The ledger records each rendered block's owner, and such an edit is
kept in the note, naming the owner. A retired copy of a block no longer counts
in the collision check.

## D-134 switch checks the host as it is, and the brief is measured as it lands

The allow-list check was lexical, so a `.cursor` junction or a `GEMINI.md`
symlink carried the write outside the repository, and a `CLAUDE.md` linked to
`AGENTS.md` let one target bypass the other's size refusal. Every directory on
the way to a surface is now checked for a link, at plan time and again at write
time, and a created file is opened in exclusive mode. The batch writer gets
the same check where its root exists.

Codex reads `AGENTS.override.md` instead of `AGENTS.md`, so a switch that
writes `AGENTS.md` beside an override is refused rather than reported as a
success Codex never reads. Codex applies one budget to all AGENTS files from
the root down, and a user can raise it; canon reads the budget from the Codex
config and names a nested file the chain would cut.

Claude Code, Gemini CLI and Cursor read `@path` as an import or as context,
bare names included. The brief was never checked, so a work item that
mentioned `@config/prod.yaml` turned into a file import. Brief lines for those
hosts now put every such token in a code span, which the hosts read as text,
and the detector matches the hosts' parsers and skips code spans.

A switched surface always read as drift, and reconcile then erased the brief,
because neither knew the reserved block. Both now carry it through. The brief
was fitted without its sentinel line, so the block that landed overran its
budget; it is now measured as it lands and the receipt names the block's
digest. The footer promised a receipt no switch wrote; switch now writes one
on request and keeps the last one, and the footer names the command that lists
every left-out record. A CRLF host got a mixed file, and a byte-order mark hid
the begin marker; both now read as the host wrote them.

## D-135 The project check resolves a working directory to its checkout first

D-132 compared the identity of each session directory with this project's.
That refused two sessions the containment check had accepted. With `--remote`
on a repository that has no remote of its own, the session directory's
identity was derived without the override, so a session run at the repository
root was another project. In a project folder with no `.git`, a session run in
a subdirectory got the subdirectory's own path key.

A session directory is now resolved to the checkout it sits in before any
comparison: the nearest directory with a `.git` entry, or this project's root
when the directory is inside a project folder with no `.git`. A checkout that
is this project's root, or a sibling worktree sharing its git directory, is
this project. That is the same answer as deriving the checkout's identity with
the override, since the override names the repository and a worktree shares
its config. Any other checkout is compared by identity without the override,
so a nested repository and a submodule stay other projects.

## D-136 A value after a secret-named key is judged by its shape

D-131 widened the name rules and kept "where the two conflict the rule
redacts". The store backstop turned that into a refusal: a hand-typed
`canon workspace task "Set session_token_ttl=3600 in prod"` exited 4 with no
override, and so did `pass_rate=0.95` and `KEY_COUNT=1000`. The name rules
also redacted `KEY_PREFIX=canon`, `token_type: bearer`,
`private_key_path: ~/.ssh/id_ed25519`, `Cookie: consent=yes`, `?key=value123`
and `second pass: 2026-10-01`. A redaction of a setting is not free when the
same rule refuses the record.

The name now says what a value is for and the value's shape says whether it
is a secret (`scrub_shape.py`). A number, a date, a path and a boolean are
settings after any name. After a password word any other value is a secret,
since a person picks a password. After another credential word a word of up
to ten letters is a setting, since an issued token never reads as one. A name
where another word follows the secret word (`token_type`, `KEY_PREFIX`)
describes the secret rather than holding it, so its value must look random.
Cookies, URL query parameters and JSON fields take the same checks. Every
form in the end-to-end secret test is still redacted, and both lists are
tests. A numeric PIN after `password=` now passes through; that is the
declared cost of reading a number as a setting.

## D-137 A markdown brief says on the command line what it left out

The markdown target has no instruction file, so its brief carries no
instruction block (D-124 declares the downgrade). Only the receipt said so.
`canon handoff --to markdown` printed "brief for markdown: 0 records, 0 left
out" with nothing on stderr, so a person pasting the brief lost their blocks
without being told.

The command now says it where the person looks. Beside a printed brief the
count and the reason go to stderr, so the brief on stdout stays clean to
paste or pipe. Beside a written brief they join the result line. `switch
--to markdown` adds the same line to its warnings. In `--json` both commands
carry `omitted_blocks` with the count, the ids and the declared reason, and
a target with an instruction file reports a count of zero.

## D-138 A URL user part is redacted by its shape, not by a length floor

D-131 redacted a URL user part with no password only at sixteen characters or
more. A fifteen-character token as the user (`https://<token>@github.com`)
passed through, and an eighteen-character name such as `github-actions-bot`
was redacted. A length floor got both wrong.

The rule now reads the shape. The password of any `user:password@` is
redacted whatever it holds, unless it is a placeholder. A user part with no
password is a token when it mixes both cases with a digit in eight or more
characters, mixes letters and digits in twelve or more, or runs to sixteen or
more characters without being a lower-case name. `git`, `deploy`,
`first.last` and `x-access-token` stay. `scrub.py` and the walkthrough state
the rule in those terms.

## D-139 The Codex budget is read where Codex reads its config

D-134 read `project_doc_max_bytes` from `~/.codex/config.toml` only. Codex
reads its config from `CODEX_HOME` when that is set, so a user who keeps
Codex there and raised the budget was still refused at 32,768 bytes, and a
budget lowered there was not enforced. The refusal also did not name the
setting.

`switch` now takes `CODEX_HOME` from its environment and reads `config.toml`
there, falling back to `~/.codex` under `--home` only when it is unset, which
is the order Codex uses. The refusal says the limit is
`project_doc_max_bytes`, where the number came from, and where to raise it.

## D-140 The scrubber runs in time linear in its input

D-136 added a path pattern with a nested quantifier, `(?:[\w.~@+-]+[\\/]?)*`.
A value after a secret-named key that started like a path and failed later
(`KEY_FILE=/home/runner/work/repository_name/keys.pem:ro`, a `?query`, a `//`)
took time that doubled with each character. The call is on the import path,
the store write and the store backstop, none of which has a timeout, so
`canon workspace task` with that text never returned. Four rules also ran in
time quadratic in a long name run (`a.a.a...` of 40,000 characters took 32
seconds), and every match re-scanned the text for earlier redactions.

The path pattern now requires a separator after each segment it repeats,
which accepts the same strings and cannot split a segment two ways. A name is
read whole and a lookahead asks whether it holds a secret word, a match
starts only where a name starts, a URL scheme is capped at 256 characters and
a URL password at 512, and a rule pass reads the earlier markers once. A
fuzz run of 160,000 generated texts gave the same output before and after,
except for the exponential cases. `tests/test_workspace_scrub_time.py` runs
the reported inputs and long name runs in a child process under a timeout,
so a regression fails the suite instead of hanging it.

## D-141 A value looks random by its runs, not by its character classes

D-136 read any value of twelve or more characters that mixed letters and a
digit as random, and D-138 read a URL user part as a token at eight
characters with both cases and a digit or twelve with letters and digits.
Those are character-class tests. An identifier that carries a version, a
date or a region (`KEY_VAULT_NAME=kv-prod-eastus2`, `key=feature_flag_v2`,
`Cookie: _ga=GA1.2.1234567890.1234567890`) was redacted, and so was a
service account in a URL (`ssh://deploy-bot-2024@git.example.com`,
`https://GitHubUser42@github.com`). The store refused each such record with
exit 4. The port rule exempted a port only before `/` or the end, so
`http://localhost:8080?next=user@example.com` read `8080?next=user` as a
password.

A value now looks random when a run of eight or more letters and digits in
it is not a word followed by a number and not a number followed by up to two
letters (`scrub_shape.random_run`), or, as before, when it mixes both cases
with `+`, `/` or `=`. A URL user part is a token when, decoded, it holds such
a run. An AWS resource name is a setting like a number, and a port followed
by `?` or `#` is a port. On 20,000 random values per shape, a 20-character
base62 value after a qualified name is missed 3.7% of the time (3.2% under
the old test, which missed any value with no digit) and a 32-character one
0.5% (0.3% before); a hex or base36 value of 20 characters or more is missed
at most 0.3% of the time. A random value whose digits all come at the end reads as a
word followed by a number and passes: a declared limit.

## D-142 The last secret word decides a name, and a password keeps its suffix

D-136 read a name as qualified whenever another word followed the secret
word, and a qualified name redacts only a value that looks random. A
human-chosen password never does, so `DB_PASSWORD_PROD=Summer2024!`,
`PASSWORD_ADMIN=hunter2`, `ADMIN_PASSWORD_2=letmein` and
`{"password_confirmation": "Summer2024!"}` reached the store in plain text,
where the D-131 rules had redacted them. D-136 had also read any value that
started at `/` as a path before it asked the name, so `DB_PASSWORD=/hunter2`
passed, and a base64 key with short or digit-free segments
(`AWS_SECRET_ACCESS_KEY=/wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLE`) read as a
path.

The class now comes from the last secret word in the name. After a password
word, a word that names which password (`prod`, `staging`, `admin`, `2`,
`confirmation`) keeps the name a password name, and only a word that
describes the password (`type`, `path`, `min`, `max`, `policy`, `url`,
`hint`, `ttl` and the rest of `_DESCRIPTORS`) makes it a description. After a
token, secret, credential or key word, any following word still makes the
name a description, since an issued token under `GITHUB_TOKEN_CI` still
looks random and a helper or backend name under `credential.helper` is not
a secret. After a name that holds a password or a token, a path needs two
segments and must not be base64-shaped, and after any name a path segment
of sixteen or more base64 characters that mixes both cases is not a path
segment, so a digit-free stretch of a key does not read as a directory. Of
20,000 random 40-character keys that start with `/`, none passes after
`AWS_SECRET_ACCESS_KEY` and 2 pass after a bare `key`. `enabled` and
`disabled` join the words that are never a secret. The cost: a value under a password name
followed by a word that is not in the list (`first_pass_label` is fine,
`pass_one: complete` is not) is redacted, and the store refuses it; the
list is where that trade is tuned. A path under a password or token name
that uses only letters, digits and slashes and mixes both cases with a digit
(`API_KEY=/Users/dev/Project2`) reads as a base64 key and is redacted too.

## D-143 A URL query parameter ends at the next `&` or `#`

D-136 said a URL query parameter takes the same name and shape rules as an
assignment. Only an exact list of names had a query rule, and the general
assignment rule also matched a name after `?` or `&` with a value class that
admits `&`, `=` and `#`. It judged the rest of the query string as one
value: `?token=bearer&page=2` read `bearer&page=2` as a token, and
`?key=main&v=a8f3k2j9x7m1` redacted `key` for the cache-buster after it.
`canon workspace task "Check https://example.com/search?key=value123&page=2
for the paging bug"` exited 4. A name the list lacked (`?db_password=`,
`?private_token=`) fell to the assignment rule, whose redaction ran to the
end of the query.

The query rule now takes any name with a key, token, secret, pass, password,
credential, auth, sig or code segment, and its value ends at the next `&` or
`#`. The assignment rules skip a `name=` right after `?` or `&`. Shell text
such as `make&&DB_PASSWORD=...` reads as a query parameter, which still
redacts the value up to the next `&`. The general assignment rule also
starts a name after the `-` or `--` of a command-line flag, so
`--api-token=<token>` is redacted; before, a name had to start after a
character that cannot be in a name, and the flag's dash blocked it.

## D-144 A header value is judged by its shape and read on its own line

D-136 moved the name-based rules to shape checks and left three header rules
matching by name alone: `bearer-header`, `auth-header` and `api-key-header`.
The bearer rule's `\s+` also crossed a line break, so `token_type: bearer`
followed by `expires_in: 3600` on the next line, which is how an OAuth token
response prints, redacted `expires_in`. Prose and config were refused with
exit 4: "Use bearer authentication for the admin API", "X-API-Key:
required", `x-auth-token: disabled`, `Authorization: Token placeholder`, and
a date, a number or a path after `X-API-Key:`, which the walkthrough says a
secret-named key leaves alone.

The three rules now take spaces and tabs only between the header name and
its value, and a value is a token unless it is a placeholder, a word that is
never a secret, a setting by its shape (a number, a date, a path of two
segments), or a lower-case or capitalised word of fewer than twenty letters.
A bearer token of twenty identical letters, as the rule test uses, is still
a token. The cost: a real token that is one lower-case word of fewer than
twenty letters passes, and a number of up to 19 digits after `X-API-Key:`
passes, as it does after any secret-named key.

## D-145 A Codex URL that names this checkout's own remote defers to the directory

D-135 says a checkout of this project's own repository is this project under
a `--remote` override too. That held for a Claude Code session, which names
only its working directory, and not for a Codex rollout, which also names
`git.repository_url`. Codex records the checkout's own origin. With a fork
as origin and `--remote` naming the upstream, a rollout at the repository
root was compared by URL first, fork against upstream, and refused with
`isolation_refused`, while a Claude Code session at the same root matched.
The inconsistency predates D-135; D-135's text promised otherwise.

A repository URL that names this checkout's own remote, when the override
names another repository and the rollout names a working directory, now
defers to the working directory check. The root and a sibling worktree
match; another clone of the fork is compared by its own identity and stays
another project; a URL that names neither the override nor this checkout's
remote is refused as before. Without an override the URL and the key agree,
so nothing changes there.
