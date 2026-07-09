# Forum Ledger Deep-Verify Scaling Benchmark Plan

Date: 2026-07-09

Source trigger: external feedback asking whether `verify(deep=True)` has been benchmarked once content-addressed ledgers become large.

Status type: benchmark plan, not benchmark results.

## Evidence from current forum implementation

Observed implementation surfaces:

- `C:\dev\public\forum\src\forum\ledger.py`
- `C:\dev\public\forum\src\forum\storage.py`
- `C:\dev\public\forum\src\forum\report.py`
- `C:\dev\public\forum\src\forum\cli.py`

Current behavior observed from source inspection:

- `Ledger.verify()` walks every ledger entry, checks sequence continuity, checks `prev_hash`, recomputes each entry hash, and returns false at the first mismatch.
- `Ledger.verify(deep=True)` runs the chain verification, then calls `verify_payloads()`.
- `verify_payloads()` walks every ledger entry, attempts to load the content-addressed payload body by hash, skips absent bodies, and re-hashes present bodies to compare against the stored payload hash.
- `FileStorage` loads `entries.jsonl` and `payloads.jsonl` into memory on construction, then serves reads from memory.
- `forum bench A B` compares summarized ledger metrics, but it does not currently measure shallow/deep verify wall time, throughput, cold-load cost, or scaling curves.

## Answer to the feedback

Short answer: functional deep verification exists and is used throughout the test/demo/report surfaces, but a dedicated scaling benchmark for `verify(deep=True)` is not yet evidenced here.

The likely first bottleneck is present-payload byte volume, not just entry count. Shallow verification is entry-count bound. Deep verification is entry-count plus content-addressed payload re-hashing for every present body. Redacted/hash-only payloads preserve the chain and reduce deep verification byte work because absent bodies are skipped.

## Benchmark objective

Measure the cost curve of:

- shallow chain verification
- deep payload verification
- checkpoint generation
- cold FileStorage reload plus deep verification
- warm FileStorage deep verification
- in-memory deep verification

## Required dimensions

| Dimension | Values |
| --- | --- |
| Entry count | `100`, `1_000`, `10_000`, `100_000`, `1_000_000` if practical |
| Payload size | `512 B`, `4 KiB`, `32 KiB`, `256 KiB`, `1 MiB` |
| Payload presence | `100% present`, `50% redacted/hash-only`, `90% redacted/hash-only` |
| Storage | `InMemoryStorage`, `FileStorage(fsync_each=True)`, `FileStorage(fsync_each=False)` |
| Read state | warm in-process, cold reload from disk |
| Payload entropy | repeated low-entropy payloads, unique deterministic pseudo-random payloads |

## Required metrics

- total entries
- distinct payload count
- total present payload bytes
- ledger file bytes
- payload file bytes
- append/build time
- cold reload time
- `verify()` wall time
- `verify(deep=True)` wall time
- `checkpoint()` wall time
- payload hash throughput in MB/s
- entries verified per second
- process peak RSS if available
- Python version and platform
- storage mode
- redaction ratio

## Acceptance criteria

A valid benchmark result must:

- produce JSON and Markdown artifacts;
- include raw per-run samples, not only aggregate means;
- run at least three repetitions per scenario;
- separate cold reload cost from warm verify cost;
- separate entry-count cost from payload-byte cost;
- include redacted/hash-only scenarios;
- include at least one tampered payload negative-control scenario;
- avoid reading or printing sensitive payload bodies;
- include the exact forum commit or working-tree identifier when available;
- record whether the result was produced from `C:\dev\public\forum`.

## Expected interpretation

The expected complexity is:

- `verify()`: approximately `O(entries)`.
- `verify(deep=True)`: approximately `O(entries + present_payload_bytes)`.
- `checkpoint()`: approximately `O(entries)` over entry hashes.
- cold `FileStorage` verification: `O(entries + payload_log_bytes)` to load, plus the verify cost.

This is an expected model, not a measured result.

## Next implementation step

Add a zero-dependency forum benchmark command or script that generates synthetic ledgers, runs the matrix above, and writes:

- `forum-ledger-deep-verify-benchmark.json`
- `forum-ledger-deep-verify-benchmark.md`

Then include the artifact in the Codex/Flywheel benchmark coverage and experimental outcome pipeline.

