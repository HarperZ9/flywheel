# Your traces: where they are and what you can do with them

An agent run leaves a record: your prompts, the model's answers, the tool
calls it made and what they returned. Flywheel, its lanes and the agent
clients you run keep copies of that record on your disk. This page says where
those copies are and which of them you control today.

## Where your data goes

- **Stored only on your machine:** every record Flywheel keeps: agent
  traces, receipts, the custody ledger and desktop history. Your provider keys
  are stored only on your machine too, and each one is sent to its own
  provider with every request to that provider.
- **Goes to the model provider you pick:** the whole content of each request.
  That is your prompt, the system text, any files or context attached or
  recalled for the request, and in an agent run every tool result sent back
  for the next step. The provider keeps what its terms allow. Flywheel's
  native agent path to the OpenAI Responses API asks the provider not to
  store the request (`store: false`); what a provider does behind that flag
  is not something Flywheel can check. With a local model, the request
  content stays on your machine. URL freezing and bench replays, when you
  turn them on, still reach the network.
- **Kept by your agent clients on their own:** Claude Code and Codex write
  their own transcripts of every session to your disk. Claude Code removes
  old ones after `cleanupPeriodDays`; whether Codex removes old rollouts is
  not known. `flywheel traces status` counts them and marks them as outside
  Flywheel's custody.
- **Through a tunnel, from your phone:** when the app on your phone reaches
  your gateway through a tunnel (`desktop/docs/MOBILE-SETUP.md`), requests
  and the records you open pass through the tunnel provider. A Cloudflare
  tunnel ends TLS at Cloudflare's edge. The app on the phone keeps its own
  conversation history on the phone.

## See every store

```
flywheel traces status
flywheel traces status --json
```

`status` lists every place Flywheel and its lanes keep trace-derived data.
For each one it shows:

- where it is, relative to your Flywheel home (`FLYWHEEL_HOME`, by default
  `~/.flywheel`) or to the run root;
- which kinds of data it holds: content (C1), tool input and output (C2),
  reasoning (C3), metadata (C4), hashes and ids derived from content (C5),
  credentials (C6), personal data (C7) and derived forms such as memories and
  indexes (C8);
- how it is protected on disk, and for each plaintext store why it is
  plaintext and which change closes that;
- how long it is kept, and every cap the store applies with what happens at
  that cap;
- what is on disk now: files, bytes and the date range;
- whether it can be exported and deleted, and if not, which change adds that.

It also lists every entry under your Flywheel home, its `state` folder, the
run root and the `lanes` folder that no store claims, marked `UNREGISTERED`,
and every store whose contents could not be classified yet, marked
`UNCLASSIFIED` with the reason. Copies kept by Claude Code and Codex are
listed as outside Flywheel's custody, with their counts.

`status` only reads. It creates no file and no folder. Besides counting
files it reads custody metadata only (the ledger, the tombstones, the
presence method and the retention policy), and it never opens a trace, a
turn or an import to read its content.

## Retention

```
flywheel traces retention show
flywheel traces retention set --store S1 --max-age-days 30
flywheel traces retention plan
flywheel traces retention apply --plan-digest <digest>
```

The default retention is keep until you delete. Nothing is deleted on a
timer until you adopt a rule. A rule names a store (`S1` gateway traces, `CT`
captured turns, `IM` imported transcripts) or a data class, with a maximum
age in days, a maximum item count or a maximum size. `set` writes
`trace-retention.json` in your Flywheel home and adopts it after your
confirmation. A file edited by hand does nothing until `flywheel traces
retention adopt`; until then `status` and the next prompt say a change is
waiting.

The gateway runs an adopted rule at gateway start and every 24 hours after,
so a rule adopted while the gateway runs takes effect from its next start;
`retention show` says whether the running gateway has picked the rule up.
The first run after an adoption that finds something due only plans, and
that preview is read from the custody ledger, not from a file an agent could
edit. A later run hands its plan to the deletion
engine, so the closure, the checks and the tombstone are the same as for
`flywheel traces delete`. A run that would delete more than
`max_share_per_run` of a store's items (10 percent by default) stops at its
plan and waits for `retention apply` with your confirmation. Each run writes
one custody ledger entry and one witness event, and a failed run keeps its
plan pending and shows in `status`.

An item's age is the time Flywheel stored it, read from the file's
modification time. Encrypting a legacy trace keeps its times. Restoring
custody from a backup resets that time, so restored items count as new.

The adopted policy file counts only when it matches the latest adoption in
the custody ledger. A policy file written straight to disk, without your
confirmation, reads as `SETTINGS_TAMPERED`: keep runs instead, and `status`
and the next prompt say so. The same check guards the capture settings and
the presence method. Retention covers the three stores above; the
other stores keep until you delete, and their inventory entries say so.

## The custody ledger

Custody events are appended to a hash-chained ledger under
`state/custody-ledger/`: losses, capture-off counts, settings changes,
imports, exports, retention runs and deletions. Capture failures stay in the
capture spool that `flywheel traces doctor` reads; they are not ledger
entries. Each entry holds
counts, codes and digests only, never content, and the ledger refuses an
entry that carries free text. A head file beside the ledger records how many
entries it holds and the last digest, so a ledger cut short is reported.
`status` shows the entry count, whether the chain verifies, and how many loss
records it holds.

What this does not prove: a ledger you control can be rewritten whole, and a
rewrite that keeps the head file consistent is not detected here.

## Capture from Claude Code and Codex

Mount the Flywheel hook module in Claude Code or Codex
(`flywheel traces hooks print-mount` prints the lines) and each finished turn
leaves a receipt paired with its prompt: salted commitments to the answer and
prompt, not their text, and nothing that confirms a guess of either without
the salts. `flywheel traces capture content on` also keeps the text once you
confirm it, encrypted where an OS key store is available and in plaintext
otherwise, and the confirmation says which. A turn
that cannot be recorded shows an error in the client, in the same turn, and
leaves a metadata record that `flywheel traces doctor` lists until you
acknowledge it. The hook sends nothing until the local gateway has proved it
knows the gateway token, and it never sends the token itself.
`FLYWHEEL_CAPTURE=off` stops capture for a session and says so once in the
client; the gateway counts those events in the custody ledger and the
witness the next time a hook reaches it. `docs/WRAPPER-HOOKS.md` has the details and the limits.

## Import your Claude Code history

Claude Code deletes transcripts older than `cleanupPeriodDays` (30 days by
default). Copy them into custody (encrypted where an OS key store is
available) before that:

```
flywheel traces import claude-code
flywheel traces import claude-code --apply
```

The first command only plans. It lists what it would import and what it
would not, counts transcripts within seven days of Claude Code's cleanup,
and checks free space. `--apply` imports.

- Imported: session transcripts, subagent transcripts, spilled tool results
  (binary files too), variants beside a transcript, and other files in a
  session folder, each kept byte for byte (encrypted where an OS key store
  is available). Record types the
  importer does not know are kept and counted.
- Not imported, and named in a plan when they exist: `history.jsonl` (every
  prompt you typed), `file-history/`, `paste-cache/`, `plans/`, `tasks/` and
  `shell-snapshots/`.
- A junction or symbolic link inside the Claude Code folder is refused and
  never followed, so a link to your SSH keys cannot pull them in.
- Sources are opened read-only and never renamed, rewritten or re-timed. A
  file that changes during the read is skipped (`SOURCE_CHANGED`) and nothing
  of it is stored; a file written in the last minute waits for the next run.
- Running it again stores nothing new. A transcript that grew, because the
  session was resumed, is stored as a new version linked to the earlier one.
- The importer skips every source on its exclusion list, including a resumed
  session that extends a listed transcript. Deleting an import adds it to
  that list, and deleting a captured session or any of its turns adds the
  whole session. A deleted prefix counts only for the same file or the same
  session, so a short deleted file never blocks an unrelated one.
- The file an import reads is checked on the open handle: a folder swapped
  for a junction between the check and the read is refused (`OUTSIDE_ROOT`).

`flywheel traces import codex` does the same for Codex rollouts under
`sessions/` and `archived_sessions/`. Compressed `.jsonl.zst` rollouts need a
zstd module (Python 3.14, or the `backports.zstd` package); without one they
are named with their size and not imported. A decompression that grows past
200 times its input, or past 2 GiB, stops and stores nothing. A session whose
writer lock is held waits for the next run. Codex's SQLite databases, such as
`thread_history_1.sqlite`, are named with their size and never read, so a
session Codex moved into one may be missing. Reasoning Codex received
encrypted stays encrypted inside the stored line and is labeled unreadable.

What an import does not prove: the stored copy matches the file as it was
read. Claude Code's transcript can lag the live conversation, and its format
changes between versions.

## Encryption at rest

Gateway agent traces and their checkpoints are encrypted before they touch
disk. Each trace has its own random key. On Windows the keys sit in a keystore
sealed with your Windows account's data protection (DPAPI), and each file is
also checked with a key-bound digest, so a changed byte is reported as
tampering. On macOS and Linux, installing the `encryption` extra encrypts with
AES-256-GCM under a key kept in the system keychain; that keychain path has no
automated test yet. Without either, traces stay plaintext and
`flywheel traces status` says `plaintext (unavailable: <reason>)`, for
example `plaintext (unavailable: NO_OS_KEY_STORE)`. A keychain lookup that
fails or times out never creates a new key, since a new key would orphan
every shard the old one sealed.

- A trace started before encryption keeps reading, and its new records are
  encrypted. An encrypted record followed by a plaintext one is refused, and
  so is a one-file item (a captured turn, a frozen page, a bench task, an
  import's manifest) whose file was swapped for plaintext.
- A key shard written in plaintext, because no key store worked when it was
  written, is resealed the next time it is used with one; until then status
  says `KEYSTORE_PLAINTEXT` with the count. Once any store holds an encrypted
  item, a plaintext shard is refused (`ENC_DOWNGRADE`) instead, since a key
  store worked by then and the shard may have been planted with a known key.
  Code running as you can delete the markers this check reads.
- `flywheel traces encrypt --legacy` encrypts traces written before this
  release, newest file first, so a trace reads at every step. A trace whose
  run is still writing is skipped, and so is one that cannot be read
  (`UNREADABLE`); the others still convert, and each file keeps its times.
  The old plaintext stays in freed disk
  space until something overwrites it, and the command says so; only volume
  encryption (BitLocker or Device Encryption) covers that.
- Once a store holds an encrypted record, a plaintext write to it is refused
  (`ENC_REQUIRED`), for example after a reinstall without the key store.
- The route that shows a trace returns the same bytes it returned before
  encryption, so the desktop and any client reading traces see no change.
- If the operating system can no longer decrypt the keystore (a forced
  password reset, another machine), reads fail with `OS_KEY_UNAVAILABLE` and
  a loss record names the trace. Encrypted data cannot be read on another
  machine or after a password reset. Export is the backup.
- Your Flywheel home carries a Windows integrity label that keeps
  low-integrity sandboxed commands from opening anything inside it, and the
  home and its `state` folder are excluded from Windows Search indexing.

What this protects: files copied off the machine without your Windows
password, and disks read by another account where file permissions do not
apply. Destroying a trace's key makes its ciphertext unreadable to anyone
who lacks both raw-disk or snapshot access and your Windows logon secret,
which is what `flywheel traces delete` does first. Older versions of a key
shard stay sealed in freed disk space until something overwrites them, and a
key that a program running as you read before the deletion still opens the
ciphertext. What it does not
protect: any program running as you, agents included, can ask Windows to
decrypt, just as you can. A backup that includes your Windows profile's
protection keys, plus your password, decrypts everything in it.

## Delete

```
flywheel traces delete --trace-ref agt_...
flywheel traces delete --turn-ref turn_...
flywheel traces delete --session claude-code:<session id>
flywheel traces delete --apply --plan-digest <digest>
```

The first form only plans. The plan lists everything that goes together:
an agent trace with its checkpoints, a captured turn with its pending prompt
and any pages frozen for it, and the key of each. It names the copies
Flywheel cannot reach (the model provider for an agent run or a captured
turn, Claude Code's or Codex's own transcript, with the remedy there, and
your backups) and prints a plan digest. `--apply` runs exactly that plan
after your confirmation, and the confirmation shows the item counts per
store, the session and clients, and says so when the plan is every item you
hold in a store; a plan whose items changed since is refused. For encrypted
items each key is destroyed first; then the files are removed without
following any link, then Flywheel checks that files and keys are gone and
records a tombstone: when, why, which stores and how many items, and no
content, digest of content, path or session id. The residue forecast counts
ciphertext and plaintext files apart, so a plaintext item is never called
ciphertext. A trace whose agent run is still writing is left alone
(`ITEM_BUSY`), and a deletion that could not take the custody lock in time
says `CUSTODY_BUSY`; either way it stays pending until you apply the plan
again with a fresh confirmation. A crash after the tombstone is written
leaves nothing stuck: applying the plan again reports it done.

A plan digest mixes in a random value kept only with the saved plan, which
the deletion removes, so the digest left in the tombstone, the ledger and the
event log cannot be recomputed from a guess of the deleted content. A trace
that can no longer be read (damaged, or its OS key gone) is still planned and
deleted from its folder and header; the plan notes that the profile folders
named inside it could not be found. Deleting one segment of a captured turn
deletes every segment that shares its prompt.

Lane databases are not reached. The mneme database and the canon context
database can hold the same content as your traces, and `flywheel traces
delete` does not touch them; each lane deletes through its own tools. In the
release Flywheel pins, mneme's forget erases a memory with its source turns
and the rows derived from them. It returns a plan first and erases on a
second call that confirms that plan, and Flywheel asks for your approval at
T2 for each call. Earlier audit entries still name the memory by an id
derived from its content. In the pinned release, canon purges context
records from its own command line. Flywheel never calls purge, and the
engine starts canon's context server with purge turned off.

`flywheel traces verify-gone` asks for a phrase without showing it and
reports how many times it still appears in the plaintext files of the
stores a deletion covers, per file, never the text. Encrypted custody files are ciphertext,
so the phrase can never be found in them; they are counted as not searched,
and a zero count says nothing about them. Freed disk space, backups and
copies outside Flywheel are not searched.

Imported transcripts are deleted the same way: `--import-ref imp_...` selects
one item, and `--session` covers the imported files of that session as well
as its captured turns. Before any key is destroyed, each item joins the
exclusion list as a keyed digest of its bytes, so a later import skips it,
and a resumed session whose transcript extends the deleted one is skipped as
`PREVIOUSLY_DELETED_SESSION` with nothing of it stored. Selecting one
version of a transcript that grew selects every earlier and later version
too, since each is a prefix of the same file. The client's own transcript
stays, and the report names the file the client keeps. Claude Code has no
command that removes one session: `claude project purge` removes every
session of the project, so the report tells you to delete the one file.
Codex has no such command either.

Plaintext stores are covered too: `--receipt-eid`, `--note-ref` and
`--legacy-run` select store.db receipts, memory notes and runs from before
private traces, and a deleted trace also takes its operation's sealed
results and the CLI profile folder it names. Rows leave store.db through a
checked scrub (secure delete, an emptied write-ahead log, VACUUM), and an
audit entry records each removal (and each relation that named it), so the
store's own verification still passes; only turn receipts can be selected.
If another program has store.db open, the deletion stops (`DB_BUSY`) and
stays pending until you apply the plan again. Plaintext leaves its old bytes in
freed disk space until something overwrites them, and every report says so.
Receipts written before this release kept content-derived ids and digests in
the audit log; those rows stay and are counted. Pages frozen by old receipts
stay until every store that cites them can be searched. Every report lists
the stores no deletion covers yet.

## Export

```
flywheel traces export --out <new folder>
python <folder>/verify.py <folder>
flywheel traces verify-export <folder or zip>
```

An export is your portable, plaintext copy of the gateway traces, captured
turns, pages frozen for them, imported transcripts and deletion tombstones.
It carries `manifest.json` (every file with its sha256, the stores left out
and why, the omissions, and what verification does not prove), a
`README.txt`, and `verify.py`, a copy of the verifier that needs nothing but
Python. The verifier prints `MATCH` when every file matches the manifest,
the manifest root re-derives and every gateway trace chain re-derives record
by record; `DRIFT` naming each changed file; or `UNVERIFIABLE` with the
reason, such as a missing file. It refuses unsafe paths in a manifest
(absolute, `..`, drive letters, UNC and device prefixes, alternate data
streams, control characters, reserved device names) before opening
anything, refuses a folder that holds a link or junction instead of
following it, prints every reason with control characters escaped, and reads
a zip in memory under caps on member count, size and compression ratio
without extracting it. Anyone can rewrite the files and the manifest
together, so `MATCH` shows only that the files match this manifest; to tie a
copy to your custody, compare its `root_sha256` with the export entry in
your custody ledger.

Credentials are redacted by default, and `--no-redact` keeps them as stored.
`--redact-personal` also redacts personal data. In a redacted export, paths
under your home folder read `~` (Claude Code's dash-named project folders
too), and placeholder tags come from a key made
for that export alone, so two exports cannot be linked through their tags
(`--stable-tags` makes them match). Gateway traces are exported unredacted,
because redaction would break their chain, and the manifest lists each one
that holds a catalog hit with its counts. An imported file that is not a
JSON-lines transcript is left out of a redacted export and listed as an
omission. A compressed Codex rollout is decompressed under the zstd bounds
and redacted line by line; without a zstd module it is listed as an
omission, and `--no-redact` exports its exact `.jsonl.zst` bytes.

The destination must not exist yet (an empty folder is refused too) and
must lie outside your Flywheel home, with no link or junction anywhere on
its path. `--zip` writes one `.zip` file instead of a folder; the zip is
created with the same owner-only ACL and not-indexed attribute before it is
filled, and it is kept only when its verifier returns `MATCH`. A
folder under OneDrive, Dropbox, Google Drive or iCloud Drive is refused
unless you pass `--allow-sync-root` and confirm it. A network share, as a
`\\server\share` path or a drive letter mapped to one, is refused outright,
before anything opens the path; export to a local folder and copy it from
there. The folder gets an
owner-only ACL and is excluded from search indexing before anything is
written, and it keeps an `.incomplete` name until its own verifier returns
`MATCH`. `export` shows what would leave custody and asks you to type yes,
then asks your presence for that exact destination and those options; the
prompt names the resolved destination and whether credentials are redacted. The
gateway's export route never takes a path: `--grant` writes a one-use grant
naming the destination, and the route runs it once presence confirms (with
the default method `none`, nothing is asked). Each export writes one ledger
entry and one witness event with the root digest and a keyed digest of the
destination; the ledger and the presence records are the only custody files
an export changes. Once written, an export is outside custody, and deleting
a trace later does not reach it. An export that stops part way leaves its
`.incomplete` folder, and the ledger records that a partial plaintext copy
exists.

## Bench tasks

When the bench route is called, each gateway trace of a run with a test
command becomes one bench task, kept beside your other traces (encrypted
where an OS key store is available): the goal as the run saw it, the test
command, the verdict the run recorded, the endpoint and model, and the git
identity of the workspace. That identity is recorded at run start when the
workspace is a git work tree: the commit, a digest of the tracked files and
a digest of `git status`. The calls that read it turn off a repository's
fsmonitor command and hooks and leave `.git/index` untouched. A task is
reproducible when its commit is known and still present and nothing tracked
or untracked had changed at start; ignored files such as `.venv` do not
count. Otherwise it is marked unreproducible with the reason, and runs from
before this change have no git identity. A replay runs the agent loop with
file tools only, so a run that used lane tools, a native CLI session or the
native tool protocol is marked unreproducible too, rather than replayed with
less and counted as a regression. A goal built from selected source
context is marked untrusted. A run without a test command is counted and
skipped. Deleting a trace deletes its tasks and their replay results.

A reproducible task replays in a shared clone of its workspace at the
recorded commit. The clone reads your repository and writes nothing into it,
and git runs there without your global or system configuration, hooks or
fsmonitor. A clone whose git identity differs from the recorded one marks
the task unreproducible. The goal runs through the agent loop in the clone,
then the test command runs in the low-integrity sandbox with a short
allowlisted environment (`PATH`, `SYSTEMROOT`, `COMSPEC`, `PATHEXT`, and
`HOME`, `TEMP` and `TMP` inside the run's scratch folder), so provider keys
in the gateway's environment never reach code from an old commit. On a host
with no sandbox the test command is not run and the verdict says so. Each
verdict is kept (encrypted where an OS key store is available) with a link
to its task, the clone is removed with
junctions and symbolic links deleted as links, and a clone left by a crash
is removed when the gateway starts. The regression report compares each
task and endpoint with the verdict the original run recorded.

The gateway's bench route, `POST /api/traces/bench`, needs the endpoints to
replay on and has no default, because each task's goal text goes to each
named endpoint. Its first answer is a grant listing every reproducible task
with its goal, the endpoints, and the capabilities the original run had,
which a replay never exceeds. A goal that holds a credential refuses the
whole grant before anything is sent. The replay runs only once presence
confirms that grant (with the default method `none`, nothing is asked), and a grant whose tasks changed since it was
planned is refused. Replays run in the gateway process through the agent
loop with each endpoint's own proposer. The older bench route that read
legacy run files and wrote task text to the run root is removed.

## Owner presence and the witness

An agent you run works as you: it can call every command you can. So each
custody operation that destroys or sends out data (deletion, export,
retention adoption and runs over the share limit, capture-setting changes,
bench replays and a change of the presence method) needs a confirmation
bound to that one operation's plan, valid once and for five minutes. With
`windows-hello` that confirmation comes from a channel an agent's shell
should not reach. With the default `none`, any process holding the gateway
token or running the CLI as you confirms. The prompt text is built from the
plan itself, never taken from the request. A confirmation counts only inside
the process that asked for it (the CLI command, or the gateway for a route):
a file on disk that says "confirmed" confirms nothing.

```
flywheel traces presence show
flywheel traces presence set windows-hello
```

- `windows-hello` asks Windows for your PIN, fingerprint or face. Whether the
  prompt works from the gateway and resists automated input has not been
  checked on real hardware yet; until it is, treat it as untested.
- `none` is the default. Status, every report and every custody ledger entry
  then say that any process running as you, agents included, can perform
  these operations.

A desktop-dialog method is planned and not built: an approval any process
holding the gateway token could send would approve for an agent too.

The method changes only after the method already in effect confirms the
change. A deleted method file is refused rather than read as `none`, and a
method file that does not match the latest adoption in the custody ledger
reads as `SETTINGS_TAMPERED`, which refuses every gated operation until you
set the method again. Presence gates the CLI commands and the gateway's
routes. It does not stop code running as you that calls Flywheel's library
directly; the custody ledger and the witness are how such a change shows.

Deletions, exports, retention runs, settings changes and capture-off events
are also written to the Windows Application event log, source `Flywheel`, as
one line with the operation kind, a sequence number, a digest prefix and the
presence method: no content and no path. A standard program can add to that
log and cannot clear it without elevation. `flywheel traces doctor` reports
how many custody ledger entries have no matching event. A missing event is a sign of
tampering or loss, not proof; the log keeps about 20 MiB and drops its
oldest events first. Other systems have no witness yet, and status says so.

## Desktop chat history

The desktop app keeps your conversations in `chats.json` in your Flywheel
home. That file holds the newest conversations that fit: at most 60, and at
most 768 KiB, so a conversation that keeps growing has room. Older
conversations move to archive files in `chats-archive/` before the active
file shrinks, so no conversation is dropped for lack of room. The conversation list shows how many
conversations are archived and opens them read-only.

- If `chats.json` cannot be parsed, it is renamed to
  `chats.unreadable-<time>.json` and never written again. History starts
  empty and the conversation list names the file it set aside. You can delete
  that file from the list once you no longer need it.
- If `chats.json` exists but cannot be read at all, saving pauses, so the
  file is never replaced.
- A single conversation larger than 1 MiB or 4096 JSON nodes cannot be
  saved. Its last saved copy is kept, every other conversation still saves,
  the latest turn stays in your drafts, the list says so, and one record per
  conversation under `desktop/loss/v1/` notes its id and the reason. The
  record holds no text.
- Deleting a conversation removes it from `chats.json`, from every archive
  file and from your drafts, so it does not come back on the next start, and
  there is no undo. It does not reach old bytes in freed disk space, the
  gateway traces of those turns or the model provider's copy. Every delete,
  from the conversation list or the archive reader, asks first and says so.

The history and its archive are plaintext files that inherit your Flywheel
home's permissions. Moving them into encrypted custody is planned and not
built.

## What is not covered yet

Stores outside the export are listed by `status` and in every export's
manifest, each with its reason. Signing an export's root is not built yet. This page grows as each one lands.
