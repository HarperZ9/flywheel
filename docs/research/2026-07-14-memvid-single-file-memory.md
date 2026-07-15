# memvid: single-file agent memory, read against Flywheel's store

Source: https://github.com/memvid/memvid (operator-shared 2026-07-14).
Snapshot receipt: `artifacts/research/5a792cb2...bin`, sha
5a792cb258822cbc..., 480830 bytes, clean (not a block page). Content
summary below is operator_relayed_secondary from the README until a
maintainer benchmark is re-run here.

## What it is (relayed, moderate confidence)

A serverless memory system for agents: one portable `.mv2` file holding
content, embeddings, search structures, and metadata. Memory is an
append-only sequence of immutable "Smart Frames" (content + timestamp +
checksum + metadata), video-encoded for compression, indexed three ways
(BM25 full-text, HNSW vector, chronological). v1's QR-code encoding is
deprecated. Headline claims: +35% SOTA on LoCoMo, 0.025 ms P50 / 0.075 ms
P99 latency, 1,372x throughput over a baseline.

## Read against the loop (honestly)

The convergence is real and worth naming: memvid's immutable
checksummed frame IS Flywheel's content-addressed store record with a
per-entity hash. Both refuse silent mutation; both make the record the
unit. Where they differ is the packaging (one portable file vs a
hash-chained SQLite store with an audit ledger) and the emphasis (memvid
sells retrieval speed; the store sells a stranger-re-runnable receipt).

The load-bearing caution: every headline number here is a claim with no
interval and no evidence file in the README. "+35% SOTA" against which
baseline, on which LoCoMo split, with what n and what CI? "1,372x
throughput" over what? By our own tenet 4 these are unanchored until a
measured comparison exists. That is not a dismissal: LoCoMo is a real,
runnable long-conversation memory benchmark, so the claim is FALSIFIABLE.
It is a candidate for a preregistered head-to-head: seal a thesis
(memvid retrieval accuracy vs the Flywheel store's bm25+fold_index on the
same LoCoMo split, intervals stated) BEFORE running, then let the bench
decide with no narrative rescue. That is exactly what crucible is for.

What could pour back if it survives its own bench: a portable single-file
export of the store (the receipt travels with the data), and the
three-index-in-one-artifact shape for the memory flagship. Neither is
adopted on the README's say-so; both are gated on a measured comparison.

No claim of ours changes on this source alone.
