# Your traces: where they are and what you can do with them

An agent run leaves a record: your prompts, the model's answers, the tool
calls it made and what they returned. Flywheel, its lanes and the agent
clients you run keep copies of that record on your disk. This page says where
those copies are and which of them you control today.

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

## What is not covered yet

Export, deletion, retention settings, encryption at rest and import of
existing Claude Code and Codex transcripts are listed by `status` as gaps,
each with the change that adds it. This page grows as each one lands.
