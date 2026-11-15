# vLLM CI efficiency evidence receipt

This is a read-only evidence receipt over public GitHub Actions data for
[`vllm-project/vllm`](https://github.com/vllm-project/vllm). It identifies two
measurement experiments. It does **not** claim a defect, billed-time reduction,
or monetary savings. Receipt generation did not change the upstream repository or
contact a maintainer before publication. The declared publication set is designed to exclude private material;
run the verification and inventory checks immediately before any public upload.

The analysis is fully offline after capture. The `data/` directory contains
minimal public API snapshots and immutable workflow sources; `analyzer.py`
rederives the measurements; `build_receipt.py` records the evidence-to-claim
paths in a persisted Forum causal ledger.

## Results at the pinned snapshot

### Pre-commit workflow

The 100-run window was captured at `2026-07-21T21:30:23.5487021Z` from workflow
ID `137737330`.

| Measurement | Result |
|---|---:|
| Completed records | 100 |
| Success | 46 |
| Cancelled | 35 |
| Failure | 17 |
| Action required | 2 |
| Median run elapsed | 350 seconds |
| p90 run elapsed, nearest-rank | 591 seconds |
| Maximum run elapsed | 839 seconds |

`run elapsed` means `updated_at - run_started_at`. It is end-to-end wall-clock
elapsed from the GitHub run record. It is **not** billed runner time.

Two job samples are bound to the same workflow Git blob
`143fc427a49ee1736b00d2b3788f956709b67609`:

- [Run 29857602498](https://github.com/vllm-project/vllm/actions/runs/29857602498)
  concluded `success`. Its self-hosted `pre-commit` job ran for 277 elapsed
  seconds; the main `pre-commit/action` step ran for 259 seconds.
- [Run 29858770343](https://github.com/vllm-project/vllm/actions/runs/29858770343)
  concluded `cancelled`, while its self-hosted `pre-commit` job concluded
  `success` after 263 elapsed seconds; the main action step ran for 245 seconds.

This supports one experiment: record cancellation-request, runner-receipt,
process-exit, and job-completion timestamps on the self-hosted lane. The sample
does not establish that those 263 seconds were avoidable, billed, or caused by a
cancellation defect. The pinned workflow already enables pull-request
`cancel-in-progress`, so a policy change would be premature without runner-side
timing evidence.

### macOS smoke workflow

The 10-run window was captured at `2026-07-21T21:30:58.9941691Z` from workflow
ID `207055592`. All ten records were daily scheduled successes. Their run
elapsed range was 1,340-1,668 seconds, with a 1,499.5-second median.

In [run 29799057515](https://github.com/vllm-project/vllm/actions/runs/29799057515):

| Lane | Job elapsed | Build step | Smoke step | Workflow role |
|---|---:|---:|---:|---|
| `macos-15` | 1,326 s | 297 s | 1,007 s | required |
| `macos-26` | 1,329 s | 299 s | 1,008 s | non-blocking preview |

The jobs overlap for 1,323 seconds. Adding their elapsed values would not produce workflow
latency, runner billing, or savings. This supports a second experiment: compare
the preview lane's unique defect detection and runner occupancy under daily and
lower-cadence schedules while retaining the required daily `macos-15` lane.
No cadence change was executed here.

## Evidence and pins

| Input | Public source or immutable pin |
|---|---|
| Pre-commit run window | [`workflows/137737330/runs?per_page=100`](https://api.github.com/repos/vllm-project/vllm/actions/workflows/137737330/runs?per_page=100) |
| Successful sample jobs | [`runs/29857602498/jobs`](https://api.github.com/repos/vllm-project/vllm/actions/runs/29857602498/jobs?per_page=100) |
| Cancelled sample jobs | [`runs/29858770343/jobs`](https://api.github.com/repos/vllm-project/vllm/actions/runs/29858770343/jobs?per_page=100) |
| Pre-commit workflow | [`fca252d.../pre-commit.yml`](https://raw.githubusercontent.com/vllm-project/vllm/fca252d59efdb627549e5677263c69709590c982/.github/workflows/pre-commit.yml) |
| macOS run window | [`workflows/207055592/runs?per_page=10`](https://api.github.com/repos/vllm-project/vllm/actions/workflows/207055592/runs?per_page=10) |
| macOS sample jobs | [`runs/29799057515/jobs`](https://api.github.com/repos/vllm-project/vllm/actions/runs/29799057515/jobs?per_page=100) |
| macOS workflow | [`6bcda97.../macos-smoke-test.yml`](https://raw.githubusercontent.com/vllm-project/vllm/6bcda970fde272b06cff0d8f397224dbac96d7ad/.github/workflows/macos-smoke-test.yml) |
| Representative run metadata | `data/representative-runs.json`, sourced from each immutable run API URL |

The JSON files retain only the public fields used by the analyzer. They are
minimal snapshots, not full GitHub API responses. A later fetch of a
`latest-N` endpoint will naturally return a different window; reproducibility
comes from the included bytes and their SHA-256 digests in
`artifacts/manifest.json`.

`data/workflow-manifest.json` records Git blob IDs, while
`data/representative-runs.json` retains each representative run's workflow ID,
path, and head SHA. The analyzer enforces the complete run ID -> workflow ID and
path -> head SHA -> manifest ref -> computed workflow Git blob relationship and
fails closed on a mismatch.

## Why Forum is part of the evidence path

Forum is used as the local causal ledger, not as a label on the report. The
ledger has 12 entries:

1. audit question;
2. pinned pre-commit source;
3. offline pre-commit measurement;
4. representative cancelled-run evidence;
5. explicitly inferred cancellation experiment;
6. pinned macOS source;
7. offline macOS measurement;
8. representative dual-lane evidence;
9. explicitly inferred cadence experiment;
10. limitations;
11. a synthesis entry that binds both branches and the limitations by event ID,
    sequence, payload hash, and entry hash; and
12. conclusion, causally parented to that synthesis.

Each entry's payload is content-addressed, entries are hash-chained, and causal
parents connect a claim to the evidence or limitation that precedes it. The
current Merkle root is:

```text
fb317553850755f029505402a44fbe1019fc803f174f11367498183bb4f13642
```

That root makes edits to the Forum ledger entries and payloads detectable. It
does not cover README, source, tests, raw snapshots, license files, or the
manifest itself; those require the separate file digests. It also does not prove
that the GitHub API was truthful, that the sample is representative, or that an
inferred experiment will produce a benefit.

## Offline replay and verification

Tested with Python `3.12.10`, Forum `1.13.0`, and Forum source commit
[`542dda4`](https://github.com/HarperZ9/forum/commit/542dda464174802aa3dc0d99e686f3edc88017cf).

One-time dependency installation requires network access:

```powershell
python -m pip install -r requirements.txt
```

The commands below are offline once Forum is installed and the captured files
are present:

```powershell
python build_receipt.py
python -m unittest discover -s tests -v
python -B verify_publication.py
python -m forum ledger verify --ledger forum-ledger
python -m forum ledger show --ledger forum-ledger --limit 20
python -m forum ledger replay 11 --ledger forum-ledger
python -m forum import-trace artifacts/forum-trace.json --format generic
```

Expected verification signals:

- 26 tests pass;
- Forum reports `"chain": true` and `"deep": true`;
- the persisted ledger and re-imported trace produce the Merkle root above;
- `dangling_parents` is `0`.

The build command itself has no network path. It refuses to overwrite unknown files in
`artifacts/` or `forum-ledger/`, replaces only its declared outputs, and records
`null` for billed time and estimated savings.

## Publication packaging

Use a dedicated repository for this receipt. It depends on nested `data/`,
`artifacts/`, `forum-ledger/`, and `tests/` paths, so it is not designed for a
flat Gist. `PUBLICATION.txt` is the exact release inventory. `SHA256SUMS.txt`
binds every listed file except itself; its own hash should be recorded in the
release message or signed out of band. Do not package ignored cache directories.

## Limitations

- The latest-N windows are convenience samples, not randomized samples.
- The workflow Git blob is bound to the representative runs, not every head in
  the 100-run aggregate window.
- Run elapsed includes more than runner execution.
- Public timestamps have one-second granularity in these captures.
- A cancelled workflow with a successful job does not prove a cancellation bug.
- Parallel macOS job elapsed values cannot be added as workflow latency.
- No experimental workflow change was executed, so coverage impact, regression
  rate, resource savings, billing savings, and monetary savings are unknown.

See `artifacts/analysis.json` for the machine-readable claim states and
`NOTICE.md` for upstream attribution.
