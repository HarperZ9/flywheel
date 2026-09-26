# Your traces: where they are and what you can do with them

An agent run leaves a record: your prompts, the model's answers, the tool
calls it made and what they returned. Flywheel, its lanes and the agent
clients you run keep copies of that record on your disk. This page says where
those copies are and which of them you control today.

## Where your data goes

- **Stays on your machine:** your provider keys, and every record Flywheel
  keeps: agent traces, receipts, the custody ledger and desktop history.
- **Goes to the model provider you pick:** the whole content of each request.
  That is your prompt, the system text, any files or context attached or
  recalled for the request, and in an agent run every tool result sent back
  for the next step. The provider keeps what its terms allow. Flywheel's
  native agent path to the OpenAI Responses API asks the provider not to
  store the request (`store: false`); what a provider does behind that flag
  is not something Flywheel can check. With a local model, nothing leaves
  your machine.
- **Kept by your agent clients on their own:** Claude Code and Codex write
  their own transcripts of every session to your disk and remove old ones on
  their own schedule. `flywheel traces status` counts them and marks them as
  outside Flywheel's custody.

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

`status` only reads. It creates no file and no folder, and it never opens a
file to read its contents.

The default retention is keep until you delete. Nothing is deleted on a
timer.

## The custody ledger

Custody events are appended to a hash-chained ledger under
`state/custody-ledger/`: losses, capture counts and failures, settings
changes, imports, exports, retention runs and deletions. Each entry holds
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
leaves a receipt: digests of the answer and prompt, not their text. A turn
that cannot be recorded shows an error in the client, in the same turn, and
leaves a metadata record that `flywheel traces doctor` lists until you
acknowledge it. The hook sends nothing until the local gateway has proved it
knows the gateway token, and it never sends the token itself.
`FLYWHEEL_CAPTURE=off` stops capture for a session and says so once in the
client. `docs/WRAPPER-HOOKS.md` has the details and the limits.

## Encryption at rest

Gateway agent traces and their checkpoints are encrypted before they touch
disk. Each trace has its own random key. On Windows the keys sit in a keystore
sealed with your Windows account's data protection (DPAPI), and each file is
also checked with a key-bound digest, so a changed byte is reported as
tampering. On macOS and Linux, installing the `encryption` extra encrypts with
AES-256-GCM under a key kept in the system keychain; that keychain path has no
automated test yet. Without either, traces stay plaintext and
`flywheel traces status` says `plaintext (no OS key store)`.

- A trace started before encryption keeps reading, and its new records are
  encrypted. An encrypted record followed by a plaintext one is refused.
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
apply. Destroying a trace's key makes its ciphertext unreadable; the command
that deletes a trace comes with the deletion change. What it does not
protect: any program running as you, agents included, can ask Windows to
decrypt, just as you can. A backup that includes your Windows profile's
protection keys, plus your password, decrypts everything in it.

## Desktop chat history

The desktop app keeps your conversations in `chats.json` in your Flywheel
home. That file holds the newest conversations that fit: at most 60, and at
most 768 KiB, so a conversation that keeps growing has room. Older
conversations move to archive files in `chats-archive/` before the active
file shrinks. Nothing is dropped. The conversation list shows how many
conversations are archived and opens them read-only.

- If `chats.json` cannot be parsed, it is renamed to
  `chats.unreadable-<time>.json` and never written again. History starts
  empty and the conversation list names the file it set aside. You can delete
  that file from the list once you no longer need it.
- If `chats.json` exists but cannot be read at all, saving pauses, so the
  file is never replaced.
- A single conversation larger than 1 MiB cannot be saved. The latest turn
  stays in your drafts, the list says so, and a record under
  `desktop/loss/v1/` notes the conversation id and the reason. The record
  holds no text.
- Deleting a conversation removes it from `chats.json`, from every archive
  file and from your drafts, so it does not come back on the next start.

The history and its archive are plaintext files that inherit your Flywheel
home's permissions. Moving them into encrypted custody is planned and not
built.

## What is not covered yet

Export, deletion, retention settings and import of existing Claude Code
and Codex transcripts are listed by `status` as gaps,
each with the change that adds it. This page grows as each one lands.
