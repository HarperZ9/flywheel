# The corpus timeline, and what it bounds

**Date:** 2026-07-26 | **Register:** internal.

The assessment ruled that no number from `hard_v2` or HumanEval may be published
for the 32B until an enumerated corpus manifest exists, on the grounds that
contamination was unbounded and unauditable. It granted the 14B a weaker bound by
ordering alone. Surveying the run drive changes that: **the ordering argument
covers both models**, because there is only one pack and it predates both
evaluation sets.

## The facts, each read directly

| When | What | Source |
|---|---|---|
| 2026-07-03 01:16 | tokenize and pack starts | `logs/chain-phase01.log` |
| 2026-07-03 02:07 to 02:10 | all 8 shards written | shard mtimes |
| 2026-07-03 02:10 | `PACK_COMPLETE.json` sealed: 17,997 files, 0 skipped, 66.16M tokens, `seq_len` 4096 | the file |
| 2026-07-04 20:24 / 22:51 | two 14B CPT invocations start | log START markers |
| 2026-07-06 21:45 | 14B CPT completes, rc=0 | log DONE marker |
| **2026-07-06 23:08:51** | **`hard_v2.jsonl` first admitted to git** | `git log --diff-filter=A` |
| **2026-07-09 23:01** | **`HumanEval.jsonl.gz` appears in the data tree** | file mtime |
| 2026-07-12 12:54 | 32B CPT completes | supervisor log |
| 2026-07-14 11:45 | `hard_v3.jsonl` admitted | git |

**The decisive check.** `find /e -name "shard_*.npy"` returns exactly one
directory and `find /e -name PACK_COMPLETE.json` returns exactly one file. There
is one pack on the drive, written once, in a four-minute window on 2026-07-03.
Both CPT runs necessarily read it, because there is nothing else to read.

## What this bounds

Neither evaluation set existed as a file in the packed tree when the pack was
sealed. `hard_v2` was admitted 3 days 21 hours later; HumanEval arrived 6 days 21
hours later. **This holds for the 32B as well as the 14B**, which the assessment
did not establish, because it treated the 32B's later training date as the
relevant ordering when the binding date is the pack's.

## What it does not bound, and this is the part that keeps the manifest on the list

- **mtimes are evidence, not proof.** They can be altered, and nothing here is
  signed. This is an argument from the filesystem's own record, at the strength
  that record carries.
- **File absence is not content absence.** The bound rules out the eval FILES
  being packed. It does not rule out the same content sitting inside the 17,997
  source files under other paths. The pack log records progress counts and never
  a path, so the file list is unrecoverable from the log and only a re-pack can
  enumerate it.
- **`hard_v2` is about the packed ecosystem.** Its tasks were authored after the
  pack, but they were authored from and about the same codebase that was packed,
  so prompt-level overlap with packed content is possible and unmeasured. Ordering
  cannot answer that; only the manifest plus a matching pass can.

## Ruling, revised

The blanket prohibition on any 32B number is stronger than the evidence requires.
The accurate statement is:

> Both models trained from a single corpus sealed on 2026-07-03, before either
> evaluation set existed as a file. Contamination by direct inclusion of the
> evaluation files is bounded by that ordering, at the strength of filesystem
> timestamps. Contamination by overlapping content inside the 17,997 packed
> source files is unmeasured, and stays unmeasured until the corpus is
> re-enumerated with per-file hashes.

The enumerated manifest stays on the list. It is now the answer to a narrower and
better-specified question.
